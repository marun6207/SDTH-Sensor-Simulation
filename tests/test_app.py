from __future__ import annotations

import json

from app import app, safe_filename, scenario_dict
from simulator.models import Scenario


def test_default_scenario_round_trip() -> None:
    raw = scenario_dict()
    scenario = Scenario.model_validate(raw)
    assert Scenario.model_validate_json(scenario.model_dump_json()) == scenario
    assert raw["schema_version"] == 1


def test_safe_filename() -> None:
    assert safe_filename("Joint Sensor / Demo") == "Joint-Sensor-Demo"
    assert safe_filename("***") == "scenario"


def test_dash_index_and_layout_endpoints() -> None:
    client = app.server.test_client()
    index = client.get("/")
    layout = client.get("/_dash-layout")
    dependencies = client.get("/_dash-dependencies")
    assert index.status_code == 200
    assert b"Joint Sensor Simulator" in index.data
    assert layout.status_code == 200
    assert json.loads(layout.data)["type"] == "Div"
    assert dependencies.status_code == 200

