from __future__ import annotations

import json
from datetime import datetime, timezone

from hazard_forecast.artifacts import write_artifacts
from hazard_forecast.engine import assess_latest, run_replay
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
    assert first["snapshots"][2]["motion"]["model"] == "weighted_constant_heading"
    assert first["snapshots"][2]["motion"]["turn_rate_deg_s"] == 0
    assert "no acceleration or turn hypotheses" in first["snapshots"][2]["explanation"]["possible_band"]


def test_live_assessment_returns_only_the_latest_history_state() -> None:
    result = assess_latest(track(), snapshot(), ForecastConfig(horizon_s=60, step_s=10),
                           type_mapping={"civil-jet": "air_fixed_wing"})
    assert result["schema"] == "hazard-live-assessment/v1"
    assert result["observation_count"] == 3
    assert result["assessment"]["observation_index"] == 2
    assert result["assessment"]["as_of"] == "2026-09-25T12:00:20.000Z"
    assert "snapshots" not in result


def test_live_likely_only_assessment_excludes_possible_harms() -> None:
    feature = InfrastructureFeature(osm_type="node", osm_id=42, category="hospital", display_name="Clinic",
                                    tags={"amenity": "hospital"},
                                    geometry={"type": "Point", "coordinates": [.025, 0]})
    config = ForecastConfig(horizon_s=60, step_s=10, include_possible_band=False)
    result = assess_latest(track(), snapshot([feature]), config,
                           type_mapping={"civil-jet": "air_fixed_wing"})
    assert result["config"]["include_possible_band"] is False
    assert all(item["band"] == "likely" for item in result["assessment"]["exposures"])


def test_danger_area_buffer_is_configurable() -> None:
    assert ForecastConfig().danger_area_buffer_m == 500
    assert ForecastConfig().altitude_uncertainty_m_per_m == 0.1
    assert ForecastConfig().likely_corridor_width_multiplier == 4


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
    map_html = (tmp_path / "map.html").read_text(encoding="utf-8")
    assert "© OpenStreetMap contributors" in map_html
    assert "describeInfrastructure" in map_html
    assert "bindHover('observations',describeObservation)" in map_html
    assert "possible-fill" in map_html
    assert "affected infrastructure" in map_html
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
