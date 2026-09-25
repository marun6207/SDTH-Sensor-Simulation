from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from simulator.demo import build_demo_scenario
from simulator.engine import angular_difference, contact_state_at, extrapolate_waypoint, generate_outputs, geodesic_metrics, relative_timestamp
from simulator.models import AisEvent, AisSensor, Contact, EmitterEvent, EwSensor, Radar3DSensor, Scenario, Waypoint


def test_geodesic_metrics_are_reasonable() -> None:
    distance, bearing = geodesic_metrics(0, 0, 0, 1)
    assert distance == pytest.approx(111.319, rel=1e-3)
    assert bearing == pytest.approx(90, abs=.01)


def test_angular_difference_wraps_north() -> None:
    assert angular_difference(355, 5) == 10
    assert angular_difference(5, 355) == 10


def test_contact_interpolation_and_hold() -> None:
    contact = Contact(contact_id="A", name="A", domain="air", subtype="fixed-wing", waypoints=[
        Waypoint(latitude=0, longitude=0, altitude_m=1000, time_s=0, speed_kts=100, hold_s=10),
        Waypoint(latitude=0, longitude=1, altitude_m=2000, time_s=110, speed_kts=200),
    ])
    held = contact_state_at(contact, 5)
    halfway = contact_state_at(contact, 60)
    assert held["longitude"] == 0
    assert held["speed_kts"] == 0
    assert halfway["longitude"] == pytest.approx(.5, abs=.001)
    assert halfway["altitude_m"] == pytest.approx(1500)
    assert halfway["course_deg"] == pytest.approx(90, abs=.01)


def test_waypoint_time_is_extrapolated_from_previous_speed() -> None:
    contact = Contact(contact_id="A", name="A", domain="air", waypoints=[
        Waypoint(latitude=0, longitude=0, altitude_m=1250, time_s=100, speed_kts=60, hold_s=30)
    ])
    waypoint = extrapolate_waypoint(contact, 0, 1)
    distance_km, _ = geodesic_metrics(0, 0, 0, 1)
    expected = 100 + 30 + distance_km * 0.539956803 / 60 * 3600
    assert waypoint.time_s == pytest.approx(expected)
    assert waypoint.altitude_m == 1250
    assert waypoint.speed_kts == 60


def test_waypoint_requires_positive_previous_speed() -> None:
    contact = Contact(contact_id="A", name="A", domain="air", waypoints=[
        Waypoint(latitude=0, longitude=0, altitude_m=1000, time_s=0, speed_kts=0)
    ])
    with pytest.raises(ValueError, match="speed must be greater than zero"):
        extrapolate_waypoint(contact, 0, 1)


def test_surface_altitude_is_rejected() -> None:
    with pytest.raises(ValidationError, match="surface waypoint altitude"):
        Contact(contact_id="S", name="S", domain="surface", waypoints=[
            Waypoint(latitude=0, longitude=0, altitude_m=1, time_s=0)
        ])


def test_invalid_range_and_duplicate_ids_are_rejected() -> None:
    with pytest.raises(ValidationError, match="classification range"):
        Radar3DSensor(sensor_id="R", name="R", latitude=0, longitude=0,
                      detection_range_km=5, classification_range_km=6)
    sensor = Radar3DSensor(sensor_id="R", name="R", latitude=0, longitude=0)
    with pytest.raises(ValidationError, match="sensor IDs must be unique"):
        Scenario(name="bad", start_time=datetime.now(timezone.utc), sensors=[sensor, sensor])


def test_relative_timestamp_wraps_midnight() -> None:
    assert relative_timestamp(0) == "00:00:00"
    assert relative_timestamp(86399) == "23:59:59"
    assert relative_timestamp(86401) == "00:00:01"


def test_generation_is_deterministic_and_serializable() -> None:
    scenario = build_demo_scenario()
    first = generate_outputs(scenario)
    second = generate_outputs(scenario)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert sum(len(messages) for messages in first.values()) > 0


@pytest.mark.parametrize(
    ("sensor_id", "expected", "forbidden"),
    [
        ("GIRAFFE_AIRBASE_01", {"sensor_id", "timestamp", "track_id", "azimuth_deg", "elevation_deg", "range_km", "classification", "subtype"}, set()),
        ("MPSTAR_AIRBASE_01", {"sensor_id", "timestamp", "track_id", "azimuth_deg", "range_km", "classification", "subtype"}, {"elevation_deg"}),
        ("EOIR_AIRBASE_01", {"sensor_id", "timestamp", "track_id", "azimuth_deg", "elevation_deg", "classification", "subtype", "confidence", "image"}, set()),
        ("ARMY_EW_01", {"sensor_id", "timestamp", "emitter_id", "detected", "bearing_deg", "classification", "confidence"}, set()),
        ("CCTV_COASTAL_01", {"sensor_id", "timestamp", "track_id", "azimuth_deg", "range_km", "classification", "subtype", "confidence", "image"}, {"bearing_deg"}),
        ("AIS_OCEANS_X", {"sensor_id", "timestamp", "mmsi", "vessel_name", "latitude", "longitude", "course_deg", "speed_kts", "navigation_status"}, set()),
        ("GLINT_SAR_01", {"sensor_id", "timestamp", "track_id", "latitude", "longitude", "confidence", "classification", "subtype"}, set()),
        ("AIS_SAR_FUSION_01", {"sensor_id", "timestamp", "correlation_id", "ais_identity", "sar_track_id", "contact_id", "status", "confidence"}, set()),
    ],
)
def test_type_specific_output_schemas(sensor_id: str, expected: set[str], forbidden: set[str]) -> None:
    messages = generate_outputs(build_demo_scenario())[sensor_id]
    assert messages
    assert expected <= set(messages[0])
    assert not (forbidden & set(messages[0]))
    assert "_contact_id" not in messages[0]


def test_ais_and_emitter_outages_suppress_messages() -> None:
    outputs = generate_outputs(build_demo_scenario())
    ais_times = {message["timestamp"] for message in outputs["AIS_OCEANS_X"]}
    ew_times = {message["timestamp"] for message in outputs["ARMY_EW_01"]}
    assert "00:02:30" not in ais_times
    assert all(_seconds(value) < 210 for value in ew_times)


def test_manual_fusion_mapping_generates_correlations() -> None:
    scenario = build_demo_scenario()
    outputs = generate_outputs(scenario)
    fusion = outputs["AIS_SAR_FUSION_01"]
    assert fusion
    assert all(item["status"] == "correlated" for item in fusion)
    scenario.fusion_mappings = []
    assert generate_outputs(scenario)["AIS_SAR_FUSION_01"] == []


def test_fov_and_altitude_exclude_contact() -> None:
    scenario = Scenario(
        name="fov", start_time=datetime.now(timezone.utc), duration_s=10, random_seed=1,
        sensors=[Radar3DSensor(sensor_id="R", name="R", latitude=0, longitude=0, orientation_deg=0,
                              field_of_view_deg=20, detection_range_km=200, classification_range_km=100,
                              min_altitude_m=500, max_altitude_m=1500)],
        contacts=[Contact(contact_id="A", name="A", domain="air", waypoints=[
            Waypoint(latitude=0, longitude=1, altitude_m=2000, time_s=0)
        ])],
    )
    assert generate_outputs(scenario)["R"] == []


def test_ew_requires_enabled_emitter() -> None:
    scenario = Scenario(
        name="ew", start_time=datetime.now(timezone.utc), duration_s=5,
        sensors=[EwSensor(sensor_id="E", name="E", latitude=0, longitude=0, detection_range_km=100,
                          classification_range_km=100)],
        contacts=[Contact(contact_id="A", name="A", domain="air", emitter_events=[EmitterEvent(time_s=0, enabled=False)],
                          waypoints=[Waypoint(latitude=.1, longitude=0, altitude_m=1000, time_s=0)])],
    )
    assert generate_outputs(scenario)["E"] == []


def test_target_detectability_caps_sensor_range() -> None:
    scenario = Scenario(
        name="signature", start_time=datetime.now(timezone.utc), duration_s=1,
        sensors=[Radar3DSensor(sensor_id="R", name="R", latitude=0, longitude=0, detection_range_km=100,
                              classification_range_km=50)],
        contacts=[Contact(contact_id="A", name="A", domain="air", detectable_range_km={"radar_3d": 5},
                          waypoints=[Waypoint(latitude=.1, longitude=0, altitude_m=1000, time_s=0)])],
    )
    assert generate_outputs(scenario)["R"] == []
    scenario.contacts[0].detectable_range_km["radar_3d"] = 20
    assert generate_outputs(scenario)["R"]


def test_emcon_controls_active_sensor_emissions() -> None:
    scenario = Scenario(
        name="emcon", start_time=datetime.now(timezone.utc), duration_s=1,
        sensors=[
            EwSensor(sensor_id="E", name="E", latitude=0, longitude=0, detection_range_km=100, classification_range_km=100),
            AisSensor(sensor_id="I", name="I", latitude=0, longitude=0, detection_range_km=100, classification_range_km=100),
        ],
        contacts=[
            Contact(contact_id="A", name="A", domain="air", emcon_mode="passive",
                    waypoints=[Waypoint(latitude=.1, longitude=0, altitude_m=1000, time_s=0)]),
            Contact(contact_id="S", name="S", domain="surface", emcon_mode="silent",
                    ais_events=[AisEvent(time_s=0, enabled=True, mmsi="123", vessel_name="S")],
                    waypoints=[Waypoint(latitude=.1, longitude=0, time_s=0)]),
        ],
    )
    outputs = generate_outputs(scenario)
    assert outputs["E"] == []
    assert outputs["I"] == []


def _seconds(value: str) -> int:
    h, m, s = map(int, value.split(":"))
    return h * 3600 + m * 60 + s
