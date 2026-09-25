from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from shapely.geometry import GeometryCollection, LineString, MultiLineString, Point, Polygon, mapping, shape
from shapely.ops import polygonize, unary_union

from .models import InfrastructureFeature, InfrastructureSnapshot, SnapshotManifest


CATALOG_VERSION = "osm-civil-essential-v1"
DEFAULT_ENDPOINT = "https://overpass-api.de/api/interpreter"
DEFAULT_USER_AGENT = "CivilHazardForecast/1.0 (local defensive planning tool)"


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _selector(spec: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    if "bbox" in spec:
        bbox = spec["bbox"]
        if not isinstance(bbox, list) or len(bbox) != 4:
            raise ValueError("snapshot bbox must be [south, west, north, east]")
        south, west, north, east = (float(value) for value in bbox)
        if not (-90 <= south < north <= 90 and -180 <= west < east <= 180):
            raise ValueError("snapshot bbox is invalid")
        selector = f"({south},{west},{north},{east})"
        coverage = mapping(Polygon([(west, south), (east, south), (east, north), (west, north), (west, south)]))
        return selector, coverage
    if "polygon" in spec:
        geometry = shape(spec["polygon"])
        if not isinstance(geometry, Polygon) or geometry.is_empty or not geometry.is_valid:
            raise ValueError("snapshot polygon must be one valid GeoJSON Polygon")
        coords = list(geometry.exterior.coords)
        selector = '(poly:"' + " ".join(f"{lat} {lon}" for lon, lat in coords[:-1]) + '")'
        return selector, mapping(geometry)
    raise ValueError("snapshot spec must contain bbox or polygon")


def build_overpass_query(selector: str) -> str:
    filters = [
        '[power~"^(plant|substation)$"]',
        '[man_made~"^(water_works|pumping_station|water_tower|reservoir_covered|wastewater_plant|storage_tank|communications_tower)$"]',
        '[industrial~"^(refinery|oil|gas)$"]',
        '[telecom~"^(data_center|data_centre|exchange)$"]',
        '[amenity~"^(hospital|fire_station)$"]',
        '[emergency="ambulance_station"]',
        '[aeroway="aerodrome"]',
        '[harbour]',
        '[public_transport~"^(station|stop_area)$"]',
    ]
    clauses = "\n".join(f"nwr{item}{selector};" for item in filters)
    return f"[out:json][timeout:90];\n(\n{clauses}\n);\nout geom;"


def _element_geometry(element: dict[str, Any]):
    element_type = element.get("type")
    if element_type == "node" and "lat" in element and "lon" in element:
        return Point(float(element["lon"]), float(element["lat"]))
    if element_type == "way":
        coords = [(float(item["lon"]), float(item["lat"])) for item in element.get("geometry", [])
                  if "lon" in item and "lat" in item]
        if len(coords) >= 4 and coords[0] == coords[-1]:
            polygon = Polygon(coords)
            return polygon if polygon.is_valid else polygon.buffer(0)
        if len(coords) >= 2:
            return LineString(coords)
    if element_type == "relation":
        lines = []
        points = []
        for member in element.get("members", []):
            coords = [(float(item["lon"]), float(item["lat"])) for item in member.get("geometry", [])
                      if "lon" in item and "lat" in item]
            if len(coords) >= 2:
                lines.append(LineString(coords))
            elif len(coords) == 1:
                points.append(Point(coords[0]))
        polygons = list(polygonize(MultiLineString(lines))) if lines else []
        if polygons:
            return unary_union(polygons)
        if lines:
            return unary_union(lines)
        if points:
            return unary_union(points)
        center = element.get("center")
        if center and "lat" in center and "lon" in center:
            return Point(float(center["lon"]), float(center["lat"]))
    return GeometryCollection()

def _category(tags: dict[str, str]) -> str | None:
    if tags.get("landuse") == "military" or "military" in tags or "military_service" in tags:
        return None
    if tags.get("power") == "plant":
        return "power_plant"
    if tags.get("power") == "substation":
        return "power_substation"
    man_made = tags.get("man_made")
    substance = tags.get("substance") or tags.get("content") or tags.get("pumping_station")
    if man_made == "water_works":
        return "water_works"
    if man_made in {"water_tower", "reservoir_covered"}:
        return "water_storage"
    if man_made == "wastewater_plant":
        return "wastewater_plant"
    if man_made == "pumping_station":
        if substance in {"oil", "gas", "fuel", "petroleum"}:
            return "fuel_pumping_station"
        if substance in {"sewage", "wastewater"}:
            return "wastewater_pumping_station"
        return "water_pumping_station"
    if man_made == "storage_tank" and substance in {"oil", "gas", "fuel", "petroleum", "diesel", "gasoline"}:
        return "fuel_storage"
    if tags.get("industrial") in {"refinery", "oil", "gas"}:
        return "fuel_industrial"
    if tags.get("telecom") in {"data_center", "data_centre", "exchange"} or man_made == "communications_tower":
        return "telecommunications"
    if tags.get("amenity") == "hospital":
        return "hospital"
    if tags.get("amenity") == "fire_station":
        return "fire_station"
    if tags.get("emergency") == "ambulance_station":
        return "ambulance_station"
    if tags.get("aeroway") == "aerodrome":
        return "civil_aerodrome"
    if "harbour" in tags:
        return "civil_port"
    if tags.get("public_transport") in {"station", "stop_area"}:
        return "public_transport_hub"
    return None


def normalize_osm(raw: dict[str, Any]) -> list[InfrastructureFeature]:
    candidates: list[tuple[dict[str, Any], Any, str]] = []
    for element in raw.get("elements", []):
        tags = {str(key): str(value) for key, value in element.get("tags", {}).items()}
        geometry = _element_geometry(element)
        if geometry.is_empty:
            continue
        category = _category(tags)
        if category:
            candidates.append((element, geometry, category))
    seen: set[tuple[str, str, str]] = set()
    features = []
    for element, geometry, category in candidates:
        signature = (category, element.get("tags", {}).get("name", ""), geometry.wkb_hex)
        if signature in seen:
            continue
        seen.add(signature)
        tags = {str(key): str(value) for key, value in element.get("tags", {}).items()}
        features.append(InfrastructureFeature(
            osm_type=element["type"], osm_id=element["id"], version=int(element.get("version", 0)),
            category=category, display_name=tags.get("name"), tags=tags, geometry=mapping(geometry),
        ))
    return sorted(features, key=lambda item: (item.category, item.osm_type, str(item.osm_id)))


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def refresh_snapshot(spec: dict[str, Any], output: str | Path) -> InfrastructureSnapshot:
    selector, coverage = _selector(spec)
    endpoint = str(spec.get("endpoint", DEFAULT_ENDPOINT))
    query = build_overpass_query(selector)
    response = requests.post(endpoint, data={"data": query}, timeout=120,
                             headers={"User-Agent": str(spec.get("user_agent", DEFAULT_USER_AGENT))})
    response.raise_for_status()
    raw = response.json()
    features = normalize_osm(raw)
    raw_hash = sha256_json(raw)
    feature_collection = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": item.geometry, "properties": item.model_dump(exclude={"geometry"})}
        for item in features
    ]}
    features_hash = sha256_json(feature_collection)
    snapshot_id = str(spec.get("snapshot_id") or f"osm-{raw_hash[:12]}")
    osm_timestamp = raw.get("osm3s", {}).get("timestamp_osm_base")
    manifest = SnapshotManifest(
        snapshot_id=snapshot_id, created_at=datetime.now(timezone.utc), osm_data_timestamp=osm_timestamp,
        endpoint=endpoint, query=query, catalog_version=CATALOG_VERSION, coverage=coverage,
        raw_sha256=raw_hash, features_sha256=features_hash,
    )
    output_path = Path(output)
    _atomic_write(output_path / "raw-overpass.json", canonical_json(raw) + b"\n")
    _atomic_write(output_path / "features.geojson", canonical_json(feature_collection) + b"\n")
    _atomic_write(output_path / "manifest.json", canonical_json(manifest.model_dump(mode="json")) + b"\n")
    return InfrastructureSnapshot(path=str(output_path.resolve()), manifest=manifest, features=features)


def load_snapshot(path: str | Path) -> InfrastructureSnapshot:
    snapshot_path = Path(path)
    manifest_data = json.loads((snapshot_path / "manifest.json").read_text(encoding="utf-8"))
    manifest = SnapshotManifest.model_validate(manifest_data)
    raw = json.loads((snapshot_path / "raw-overpass.json").read_text(encoding="utf-8"))
    feature_collection = json.loads((snapshot_path / "features.geojson").read_text(encoding="utf-8"))
    if sha256_json(raw) != manifest.raw_sha256:
        raise ValueError("snapshot raw Overpass hash does not match manifest")
    if sha256_json(feature_collection) != manifest.features_sha256:
        raise ValueError("snapshot feature hash does not match manifest")
    features = []
    for feature in feature_collection.get("features", []):
        props = feature.get("properties", {})
        features.append(InfrastructureFeature(**props, geometry=feature.get("geometry")))
    return InfrastructureSnapshot(path=str(snapshot_path.resolve()), manifest=manifest, features=features)
