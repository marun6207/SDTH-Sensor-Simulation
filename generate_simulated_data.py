"""Generate the checked-in sensor-disagreement demonstration dataset."""

from __future__ import annotations

import json
from pathlib import Path

from simulator.demo import build_demo_scenario
from simulator.engine import generate_outputs
from simulator.models import Scenario


ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "examples" / "sensor_disagreement"


def build_disagreement_scenario() -> Scenario:
    scenario = build_demo_scenario()
    sensors = []
    for sensor in scenario.sensors:
        updates = {}
        if sensor.sensor_id == "EOIR_AIRBASE_01":
            # The camera still detects the UAS, but cannot classify it.
            updates = {"detection_probability": 1.0, "classification_probability": 0.0}
        elif sensor.sensor_id == "CCTV_COASTAL_01":
            # CCTV detections remain available while visual classification fails.
            updates = {"detection_probability": 1.0, "classification_probability": 0.0}
        elif sensor.sensor_id == "GLINT_SAR_01":
            # Keep SAR reliable while the vessel's AIS transmitter is offline.
            updates = {"detection_probability": 1.0, "classification_probability": 1.0}
        sensors.append(sensor.model_copy(update=updates) if updates else sensor)

    return scenario.model_copy(update={
        "name": "Sensor Disagreement Demonstration",
        "scenario_id": "sensor-disagreement-demo",
        "random_seed": 17,
    }).model_copy(update={"sensors": sensors})


def main() -> None:
    scenario = build_disagreement_scenario()
    outputs = generate_outputs(scenario)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "scenario.json").write_text(
        json.dumps(scenario.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8"
    )
    for sensor in scenario.sensors:
        path = OUTPUT_DIR / f"{sensor.sensor_id}_{sensor.sensor_type}.json"
        path.write_text(json.dumps(outputs.get(sensor.sensor_id, []), indent=2) + "\n", encoding="utf-8")
    counts = {sensor_id: len(messages) for sensor_id, messages in outputs.items()}
    print(f"Wrote {len(outputs)} sensor files to {OUTPUT_DIR}")
    print(json.dumps(counts, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
