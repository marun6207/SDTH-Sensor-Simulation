from __future__ import annotations

import json
from datetime import datetime, timezone

from hazard_forecast.artifacts import write_artifacts
from hazard_forecast.engine import run_replay
from hazard_forecast.models import (
    ForecastConfig,
    InfrastructureFeature,
    InfrastructureSnapshot,
    SnapshotManifest,
    parse_track,
)
from hazard_forecast.snapshot import canonical_json, normalize_osm


def snapshot(features=None) -> InfrastructureSnapshot:
    manifest = SnapshotManifest(
        snapshot_id="fixture", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc), endpoint="fixture",
        query="fixture", catalog_version="fixture-v1", raw_sha256="0" * 64, features_sha256="1" * 64,
        coverage={"type": "Polygon", "coordinates": [[[-5, -5], [5, -5], [5, 5], [-5, 5], [-5, -5]]]},
    )
    return InfrastructureSnapshot(path="fixture", manifest=manifest, features=features or [])


def track():
    return parse_track([
        {"timestamp": "2026-09-25T12:00:00Z", "lat": 0, "long": 0, "altitude": 1000, "speed": None, "type": None},
        {"timestamp": "2026-09-25T12:00:10Z", "lat": 0, "long": .009, "altitude": 1010, "speed": 100, "type": "civil-jet"},
        {"timestamp": "2026-09-25T12:00:20Z", "lat": 0, "long": .018, "altitude": 1020, "speed": 100, "type": None},
    ])


def test_replay_is_deterministic_and_type_persists() -> None:
    config = ForecastConfig(horizon_s=60, step_s=10)
    first = run_replay(track(), snapshot(), config, type_mapping={"civil-jet": "air_fixed_wing"})
    second = run_replay(track(), snapshot(), config, type_mapping={"civil-jet": "air_fixed_wing"})
    assert canonical_json(first) == canonical_json(second)
    assert first["snapshots"][0]["classification"]["mobility_profile"] == "unknown_air"
    assert first["snapshots"][1]["classification"]["mobility_profile"] == "air_fixed_wing"
    assert first["snapshots"][2]["classification"]["reported_type"] == "civil-jet"
    assert first["snapshots"][0]["motion"]["heading_deg"] is None
    assert first["snapshots"][1]["motion"]["model"] == "constant_velocity"
    assert first["snapshots"][2]["motion"]["model"] == "weighted_constant_turn"


def test_exposure_and_artifacts(tmp_path) -> None:
    feature = InfrastructureFeature(osm_type="node", osm_id=42, category="hospital", display_name="Clinic",
                                    tags={"amenity": "hospital"},
                                    geometry={"type": "Point", "coordinates": [.025, 0]})
    result = run_replay(track(), snapshot([feature]), ForecastConfig(horizon_s=60, step_s=10),
                        type_mapping={"civil-jet": "air_fixed_wing"})
    exposures = result["snapshots"][-1]["exposures"]
    assert exposures
    assert exposures[0]["category"] == "hospital"
    assert exposures[0]["urgency"] == "immediate"
    manifest = write_artifacts(result, tmp_path)
    expected = {"snapshots.jsonl", "result.json", "observations.geojson", "centerlines.geojson",
                "corridors.geojson", "exposed_infrastructure.geojson", "danger_areas.geojson", "map.html"}
    assert expected == set(manifest["files"])
    assert (tmp_path / "manifest.json").exists()
    assert "© OpenStreetMap contributors" in (tmp_path / "map.html").read_text(encoding="utf-8")
    assert len((tmp_path / "snapshots.jsonl").read_text().splitlines()) == 3
    assert json.loads((tmp_path / "result.json").read_text())["schema"] == "hazard-replay-result/v1"


def test_domain_conflict_and_speed_disagreement_warnings() -> None:
    observations = parse_track([
        {"timestamp": "2026-09-25T12:00:00Z", "lat": 0, "long": 0, "altitude": 0},
        {"timestamp": "2026-09-25T12:00:10Z", "lat": 0, "long": .001, "altitude": 100, "speed": 30},
    ])
    result = run_replay(observations, snapshot(), ForecastConfig(horizon_s=30, step_s=10))
    codes = {item["code"] for item in result["snapshots"][1]["warnings"]}
    assert {"domain_conflict", "speed_disagreement"} <= codes


def test_normalize_osm_excludes_military_sites_and_contents() -> None:
    raw = {"elements": [
        {"type": "way", "id": 1, "tags": {"landuse": "military"}, "geometry": [
            {"lat": -1, "lon": -1}, {"lat": -1, "lon": 1}, {"lat": 1, "lon": 1},
            {"lat": 1, "lon": -1}, {"lat": -1, "lon": -1}]},
        {"type": "node", "id": 2, "lat": 0, "lon": 0, "tags": {"amenity": "hospital", "name": "Inside"}},
        {"type": "node", "id": 3, "lat": 2, "lon": 2, "tags": {"amenity": "hospital", "name": "Outside"}},
        {"type": "node", "id": 4, "lat": 3, "lon": 3, "tags": {"power": "substation", "military": "yes"}},
    ]}
    features = normalize_osm(raw)
    assert [(item.osm_id, item.display_name) for item in features] == [(3, "Outside")]
