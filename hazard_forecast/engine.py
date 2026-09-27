from __future__ import annotations

import hashlib
import math
import weakref
from dataclasses import dataclass, field
from datetime import timezone
from typing import Any, Literal

import numpy as np
from pyproj import CRS, Geod, Transformer
from shapely import STRtree
from shapely import transform as transform_coords
from shapely.geometry import GeometryCollection, LineString, Point, mapping, shape
from shapely.ops import transform

from .models import DomainResult, ForecastConfig, InfrastructureSnapshot, Observation, infer_domain
from .profiles import PROFILE_CATALOG_VERSION, resolve_profile


GEOD = Geod(ellps="WGS84")
_PARSED_SITES: dict[int, tuple[weakref.ReferenceType, list]] = {}


def _timestamp(value) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _projection(lat: float, lon: float) -> tuple[Transformer, Transformer]:
    local = CRS.from_proj4(f"+proj=aeqd +lat_0={lat:.12f} +lon_0={lon:.12f} +datum=WGS84 +units=m +no_defs")
    return (Transformer.from_crs("EPSG:4326", local, always_xy=True),
            Transformer.from_crs(local, "EPSG:4326", always_xy=True))


def _geojson(geometry, inverse: Transformer) -> dict[str, Any]:
    if geometry.is_empty:
        return {"type": "GeometryCollection", "geometries": []}
    return mapping(transform(inverse.transform, geometry))


def _clamp(value: float, low: float, high: float, label: str, clamps: list[dict[str, float]]) -> float:
    clamped = min(max(value, low), high)
    if not math.isclose(value, clamped, rel_tol=1e-12, abs_tol=1e-12):
        clamps.append({"field": label, "original": round(value, 9), "clamped": round(clamped, 9)})
    return clamped


def _weighted_fit(times: np.ndarray, values: np.ndarray) -> tuple[float, float, np.ndarray]:
    weights = np.arange(1, len(times) + 1, dtype=float)
    matrix = np.column_stack((times, np.ones_like(times)))
    weighted = matrix * np.sqrt(weights)[:, None]
    target = values * np.sqrt(weights)
    slope, intercept = np.linalg.lstsq(weighted, target, rcond=None)[0]
    fitted = slope * times + intercept
    return float(slope), float(intercept), fitted


def _propagate(start: Point, heading_deg: float, speed_mps: float, turn_deg_s: float,
               offsets: list[int]) -> list[Point]:
    points = [start]
    x, y = start.x, start.y
    heading = heading_deg
    previous = 0
    for offset in offsets[1:]:
        duration = offset - previous
        mid_heading = heading + turn_deg_s * duration / 2
        x += math.sin(math.radians(mid_heading)) * speed_mps * duration
        y += math.cos(math.radians(mid_heading)) * speed_mps * duration
        heading += turn_deg_s * duration
        points.append(Point(x, y))
        previous = offset
    return points


def _fit_motion(observations: list[Observation], forward: Transformer, profile, config: ForecastConfig):
    window = observations[-config.fit_window_observations:]
    latest = window[-1]
    times = np.array([(item.timestamp - latest.timestamp).total_seconds() for item in window], dtype=float)
    coords = np.array([forward.transform(item.longitude, item.lat) for item in window], dtype=float)
    clamps: list[dict[str, Any]] = []
    derived_speed = None
    heading = None
    turn_rate = 0.0
    climb_rate = 0.0
    residual = 0.0
    if len(window) >= 2:
        dt = (window[-1].timestamp - window[-2].timestamp).total_seconds()
        _, _, distance = GEOD.inv(window[-2].longitude, window[-2].lat, latest.longitude, latest.lat)
        derived_speed = distance / dt
        vx, _, fitted_x = _weighted_fit(times, coords[:, 0])
        vy, _, fitted_y = _weighted_fit(times, coords[:, 1])
        _, _, fitted_alt = _weighted_fit(times, np.array([item.altitude for item in window], dtype=float))
        climb_rate, _, _ = _weighted_fit(times, np.array([item.altitude for item in window], dtype=float))
        heading = math.degrees(math.atan2(vx, vy)) % 360 if math.hypot(vx, vy) > 1e-9 else None
        residual = float(np.sqrt(np.mean((coords[:, 0] - fitted_x) ** 2 + (coords[:, 1] - fitted_y) ** 2)))
        if len(window) >= 3:
            bearings = []
            mid_times = []
            for first, second in zip(window, window[1:]):
                bearing, _, _ = GEOD.inv(first.longitude, first.lat, second.longitude, second.lat)
                bearings.append(math.radians(bearing % 360))
                mid_times.append(((first.timestamp - latest.timestamp).total_seconds()
                                  + (second.timestamp - latest.timestamp).total_seconds()) / 2)
            unwrapped = np.unwrap(np.array(bearings))
            turn_rad_s, _, _ = _weighted_fit(np.array(mid_times), unwrapped)
            turn_rate = math.degrees(turn_rad_s)
    reported_speed = latest.speed
    raw_prediction_speed = reported_speed if reported_speed is not None else (derived_speed or 0.0)
    prediction_speed = _clamp(raw_prediction_speed, profile.min_speed_mps, profile.max_speed_mps,
                              "prediction_speed_mps", clamps)
    turn_rate = _clamp(turn_rate, -profile.max_turn_rate_deg_s, profile.max_turn_rate_deg_s,
                       "turn_rate_deg_s", clamps)
    climb_rate = _clamp(climb_rate, -profile.max_descent_rate_mps, profile.max_climb_rate_mps,
                        "climb_rate_mps", clamps)
    return {
        "window": window, "heading": heading, "reported_speed": reported_speed,
        "derived_speed": derived_speed, "prediction_speed": prediction_speed,
        "turn_rate": turn_rate, "climb_rate": climb_rate, "residual": residual, "clamps": clamps,
    }

def _build_forecast(latest: Observation, motion: dict[str, Any], profile, config: ForecastConfig,
                    forward: Transformer, inverse: Transformer):
    start = Point(forward.transform(latest.longitude, latest.lat))
    offsets = list(range(0, config.horizon_s + 1, config.step_s))
    if offsets[-1] != config.horizon_s:
        offsets.append(config.horizon_s)
    likely_radius = config.likely_corridor_width_multiplier * (
        config.base_horizontal_uncertainty_m + config.likely_residual_multiplier * motion["residual"]
    )
    distances = [motion["prediction_speed"] * offset for offset in offsets]
    possible_step_geometries = [start.buffer(likely_radius + distance)
                                for distance in distances]
    possible = possible_step_geometries[-1]
    if motion["heading"] is None:
        center_points = [start]
        centerline = start
        likely = start.buffer(likely_radius)
    else:
        center_points = _propagate(start, motion["heading"], motion["prediction_speed"], 0.0, offsets)
        centerline = LineString(center_points) if len(center_points) > 1 else start
        likely = centerline.buffer(likely_radius)
    checkpoints = []
    for offset, point in zip(offsets, center_points if len(center_points) == len(offsets) else [start] * len(offsets)):
        lon, lat = inverse.transform(point.x, point.y)
        checkpoints.append({"offset_s": offset, "lat": round(lat, 9), "long": round(lon, 9),
                            "altitude": round(latest.altitude + motion["climb_rate"] * offset, 3)})
    return {
        "offsets": offsets, "center_points": center_points, "centerline_shape": centerline,
        "likely_shape": likely, "possible_shape": possible, "possible_steps": possible_step_geometries,
        "likely_radius": likely_radius,
        "centerline": _geojson(centerline, inverse), "likely_corridor": _geojson(likely, inverse),
        "possible_corridor": _geojson(possible, inverse), "checkpoints": checkpoints,
    }


def _urgency(offset: int) -> str:
    if offset <= 120:
        return "immediate"
    if offset <= 300:
        return "near_term"
    return "monitor"


def _parsed_sites(snapshot: InfrastructureSnapshot) -> list[tuple[Any, Any]]:
    """GeoJSON parse is pure in the snapshot, so later targets reuse it."""
    key = id(snapshot)
    found = _PARSED_SITES.get(key)
    if found is not None and found[0]() is snapshot:
        return found[1]
    cached = []
    for feature in snapshot.features:
        original = shape(feature.geometry)
        if not original.is_empty:
            cached.append((feature, original))

    def _forget(dead: weakref.ReferenceType, key: int = key) -> None:
        current = _PARSED_SITES.get(key)
        if current is not None and current[0] is dead:
            _PARSED_SITES.pop(key, None)

    _PARSED_SITES[key] = (weakref.ref(snapshot, _forget), cached)
    return cached


def _project_features(snapshot: InfrastructureSnapshot, forward: Transformer) -> list[tuple[Any, Any]]:
    """Project each non-empty site once, in snapshot order."""
    parsed = _parsed_sites(snapshot)
    if not parsed:
        return []

    def _xy(coords: np.ndarray) -> np.ndarray:
        longitude, latitude = coords[:, 0], coords[:, 1]
        x, y = forward.transform(longitude, latitude)
        return np.column_stack((x, y))

    projected = transform_coords(GeometryCollection([geom for _, geom in parsed]), _xy)
    return [
        (feature, local)
        for (feature, _), local in zip(parsed, projected.geoms, strict=True)
        if not local.is_empty
    ]


def _exposures(snapshot: InfrastructureSnapshot, forecast: dict[str, Any], config: ForecastConfig,
               forward: Transformer, inverse: Transformer, altitude_m: float) -> list[dict[str, Any]]:
    results = []
    offsets = forecast["offsets"]
    likely_steps = [point.buffer(forecast["likely_radius"]) for point in forecast["center_points"]]
    if len(likely_steps) != len(offsets):
        likely_steps = [forecast["likely_shape"] for _ in offsets]
    bands = [("likely", forecast["likely_shape"], likely_steps)]
    if config.include_possible_band:
        bands.append(("possible", forecast["possible_shape"], forecast["possible_steps"]))
    projected = _project_features(snapshot, forward)
    if not projected:
        return []
    # Civil warning footprint: a fixed safety margin plus altitude-dependent
    # horizontal uncertainty. This is not an explosive-effects model.
    altitude_uncertainty = max(0.0, altitude_m) * config.altitude_uncertainty_m_per_m
    warning_buffer_m = config.danger_area_buffer_m + altitude_uncertainty
    # The query pad is the largest buffer any site can receive, so the index
    # cannot drop a site the exact buffer test would keep.
    pad = max(warning_buffer_m, config.infrastructure_point_buffer_m, config.infrastructure_line_buffer_m)
    tree = STRtree([local for _, local in projected])
    for band, corridor, steps in bands:
        if corridor.is_empty:
            continue
        candidates = set(map(int, tree.query(corridor.buffer(pad), predicate="intersects")))
        for index, (feature, local) in enumerate(projected):
            if index not in candidates:
                continue
            buffer_m = (config.infrastructure_point_buffer_m
                        if local.geom_type in {"Point", "MultiPoint"}
                        else config.infrastructure_line_buffer_m)
            protected = local.buffer(max(buffer_m, warning_buffer_m))
            if not corridor.intersects(protected):
                continue
            hits = [offset for offset, step_geometry in zip(offsets, steps) if step_geometry.intersects(protected)]
            if not hits:
                hits = [offsets[-1]]
            danger = corridor.intersection(protected)
            first, last = min(hits), max(hits)
            raw_id = f"{feature.osm_type}|{feature.osm_id}|{feature.version}|{band}|{first}|{last}"
            exposure_id = hashlib.sha256(raw_id.encode()).hexdigest()[:20]
            minimum_separation = forecast["centerline_shape"].distance(protected)
            results.append({
                "exposure_id": exposure_id,
                "osm": {"type": feature.osm_type, "id": feature.osm_id, "version": feature.version},
                "category": feature.category, "display_name": feature.display_name,
                "band": band, "urgency": _urgency(first), "first_entry_offset_s": first,
                "last_exit_offset_s": last, "minimum_separation_m": round(minimum_separation, 3),
                "danger_geometry": _geojson(danger, inverse),
                "reason": [f"{band} corridor intersects the protected feature geometry",
                           f"first predicted entry is {first} seconds after the current observation"],
                "source_tags": feature.tags,
                "infrastructure_geometry": feature.geometry,
            })
    band_order = {"likely": 0, "possible": 1}
    return sorted(results, key=lambda item: (item["first_entry_offset_s"], band_order[item["band"]],
                                              item["minimum_separation_m"], item["category"],
                                              item["osm"]["type"], str(item["osm"]["id"])))


@dataclass
class ReplayState:
    snapshot: InfrastructureSnapshot
    config: ForecastConfig
    domain: DomainResult
    track_id: str
    type_mapping: dict[str, str] = field(default_factory=dict)
    observations: list[Observation] = field(default_factory=list)
    current_type: str | None = None


def advance(state: ReplayState, observation: Observation) -> dict[str, Any]:
    index = len(state.observations)
    state.observations.append(observation)
    if observation.vehicle_type is not None:
        state.current_type = observation.vehicle_type
    profile, mapping_status = resolve_profile(state.current_type, state.domain.value, state.type_mapping)
    warnings = []
    conflict = ((state.domain.value == "surface" and observation.altitude > state.config.domain_altitude_threshold_m)
                or (state.domain.value == "air" and observation.altitude <= state.config.domain_altitude_threshold_m))
    if conflict:
        warnings.append({"code": "domain_conflict", "message": "observation altitude conflicts with inferred domain"})
    if mapping_status in {"unknown", "domain_mismatch"}:
        warnings.append({"code": "unmapped_type", "message": "reported type uses the conservative unknown-domain profile"})
    forward, inverse = _projection(observation.lat, observation.longitude)
    motion = _fit_motion(state.observations, forward, profile, state.config)
    if motion["heading"] is None:
        warnings.append({"code": "insufficient_heading_data", "message": "a directional centerline requires two distinct positions"})
    if motion["reported_speed"] is not None and motion["derived_speed"] is not None:
        denominator = max(motion["derived_speed"], 1e-9)
        ratio = abs(motion["reported_speed"] - motion["derived_speed"]) / denominator
        if ratio > state.config.speed_disagreement_ratio:
            warnings.append({"code": "speed_disagreement", "message": "reported and displacement-derived speeds differ beyond tolerance",
                             "ratio": round(ratio, 6)})
    forecast = _build_forecast(observation, motion, profile, state.config, forward, inverse)
    coverage = transform(forward.transform, shape(state.snapshot.manifest.coverage))
    required_coverage = (forecast["possible_shape"] if state.config.include_possible_band
                         else forecast["likely_shape"])
    if not coverage.buffer(1).covers(required_coverage):
        raise ValueError(f"forecast at observation {index} leaves OSM snapshot coverage")
    exposures = _exposures(state.snapshot, forecast, state.config, forward, inverse, observation.altitude)
    model = "stationary_uncertainty" if len(state.observations) == 1 else (
        "constant_velocity" if len(state.observations) == 2 else "weighted_constant_heading")
    snapshot = {
        "schema": "hazard-forecast-snapshot/v1", "track_id": state.track_id,
        "observation_index": index, "as_of": _timestamp(observation.timestamp),
        "domain": state.domain.model_dump(),
        "classification": {"reported_type": state.current_type, "mobility_profile": profile.name,
                           "mapping_status": mapping_status, "catalog_version": PROFILE_CATALOG_VERSION},
        "motion": {
            "heading_deg": None if motion["heading"] is None else round(motion["heading"], 6),
            "reported_speed_mps": motion["reported_speed"],
            "derived_speed_mps": None if motion["derived_speed"] is None else round(motion["derived_speed"], 6),
            "prediction_speed_mps": round(motion["prediction_speed"], 6),
            "turn_rate_deg_s": 0.0,
            "climb_rate_mps": round(motion["climb_rate"], 6),
            "fit_residual_m": round(motion["residual"], 6), "model": model,
            "observations_used": list(range(max(0, index + 1 - len(motion["window"])), index + 1)),
            "clamps": motion["clamps"],
        },
        "forecast": {"horizon_s": state.config.horizon_s, "step_s": state.config.step_s,
                     "centerline": forecast["centerline"], "likely_corridor": forecast["likely_corridor"],
                     "possible_corridor": forecast["possible_corridor"], "checkpoints": forecast["checkpoints"]},
        "exposures": exposures,
        "warnings": warnings,
        "explanation": {
            "position_model": "WGS84 geodesics with a latest-observation azimuthal-equidistant working projection",
            "speed_precedence": "reported speed when present; otherwise displacement-derived speed",
            "likely_band": {"base_uncertainty_m": state.config.base_horizontal_uncertainty_m,
                            "fit_residual_m": round(motion["residual"], 6),
                            "residual_multiplier": state.config.likely_residual_multiplier,
                            "corridor_width_multiplier": state.config.likely_corridor_width_multiplier},
            "possible_band": "compact radial area using fitted speed plus the likely-corridor radius; no acceleration or turn hypotheses",
            "alert_order": "entry time, likely before possible, minimum separation, category, OSM identity",
        },
    }
    return snapshot


def run_replay(observations: list[Observation], snapshot: InfrastructureSnapshot,
               config: ForecastConfig | None = None, domain_override: Literal["air", "surface"] | None = None,
               track_id: str = "track-001", type_mapping: dict[str, str] | None = None) -> dict[str, Any]:
    config = config or ForecastConfig()
    domain = infer_domain(observations, domain_override, config.domain_altitude_threshold_m)
    state = ReplayState(snapshot=snapshot, config=config, domain=domain, track_id=track_id,
                        type_mapping=type_mapping or {})
    snapshots = [advance(state, observation) for observation in observations]
    return {
        "schema": "hazard-replay-result/v1", "track_id": track_id,
        "snapshot": {"snapshot_id": snapshot.manifest.snapshot_id,
                     "features_sha256": snapshot.manifest.features_sha256,
                     "catalog_version": snapshot.manifest.catalog_version,
                     "attribution": snapshot.manifest.attribution},
        "profile_catalog_version": PROFILE_CATALOG_VERSION, "config": config.model_dump(),
        "domain": domain.model_dump(),
        "observations": [item.model_dump(mode="json", by_alias=True) for item in observations],
        "snapshots": snapshots,
    }


def assess_latest(observations: list[Observation], snapshot: InfrastructureSnapshot,
                  config: ForecastConfig | None = None,
                  domain_override: Literal["air", "surface"] | None = None,
                  track_id: str = "track-001",
                  type_mapping: dict[str, str] | None = None) -> dict[str, Any]:
    """Assess only the newest observation in a caller-supplied cumulative history."""
    if not observations:
        raise ValueError("cannot assess an empty observation history")
    config = config or ForecastConfig()
    domain = infer_domain(observations, domain_override, config.domain_altitude_threshold_m)
    state = ReplayState(
        snapshot=snapshot,
        config=config,
        domain=domain,
        track_id=track_id,
        type_mapping=type_mapping or {},
        observations=list(observations[:-1]),
    )
    for observation in observations[:-1]:
        if observation.vehicle_type is not None:
            state.current_type = observation.vehicle_type
    assessment = advance(state, observations[-1])
    return {
        "schema": "hazard-live-assessment/v1",
        "track_id": track_id,
        "as_of": assessment["as_of"],
        "observation_count": len(observations),
        "snapshot": {
            "snapshot_id": snapshot.manifest.snapshot_id,
            "features_sha256": snapshot.manifest.features_sha256,
            "catalog_version": snapshot.manifest.catalog_version,
            "attribution": snapshot.manifest.attribution,
        },
        "profile_catalog_version": PROFILE_CATALOG_VERSION,
        "config": config.model_dump(),
        "domain": domain.model_dump(),
        "assessment": assessment,
    }
