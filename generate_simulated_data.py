"""Generate the checked-in sensor-disagreement demonstration dataset."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path

from simulator.engine import generate_outputs
from simulator.models import Scenario


ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "examples" / "sensor_disagreement"
BASE_SCENARIO = ROOT / "examples" / "sensor_coordinated_100" / "Coordinated-Demo_scenario.json"


def build_disagreement_scenario() -> Scenario:
    # Start with the same 16-sensor/6-contact Coordinated Demo used by the
    # checked-in coordinated datasets, rather than the small unit-test demo.
    scenario = Scenario.model_validate(json.loads(BASE_SCENARIO.read_text(encoding="utf-8")))
    sensors = []
    for sensor in scenario.sensors:
        updates = {}
        if sensor.sensor_id == "RADAR_3D_01":
            updates = {"detection_probability": 0.72, "classification_probability": 0.55}
        elif sensor.sensor_id == "RADAR_3D_02":
            updates = {"detection_probability": 0.98, "classification_probability": 0.92}
        elif sensor.sensor_id == "RADAR_2D_01":
            updates = {"detection_probability": 0.78, "classification_probability": 0.58, "refresh_rate_s": 2}
        elif sensor.sensor_id == "RADAR_2D_02":
            updates = {"detection_probability": 0.94, "classification_probability": 0.82}
        elif sensor.sensor_id == "EOIR_01":
            updates = {"detection_probability": 0.62, "classification_probability": 0.38, "refresh_rate_s": 2}
        elif sensor.sensor_id in {"CCTV_01", "CCTV_02", "CCTV_03"}:
            updates = {"detection_probability": 0.74, "classification_probability": 0.48, "refresh_rate_s": 3}
        elif sensor.sensor_id in {"CCTV_04", "CCTV_05", "CCTV_06"}:
            updates = {"detection_probability": 0.96, "classification_probability": 0.86}
        elif sensor.sensor_id == "SAR_01":
            updates = {"detection_probability": 0.9, "classification_probability": 0.78}
        sensors.append(sensor.model_copy(update=updates) if updates else sensor)

    contacts = []
    for contact in scenario.contacts:
        limits = dict(contact.detectable_range_km)
        if contact.contact_id == "HOSTILE_AIR_01":
            limits.update(radar_3d=18, eoir=14)
        elif contact.contact_id == "HOSTILE_SURFACE_01":
            limits.update(cctv=10)
        contacts.append(contact.model_copy(update={"detectable_range_km": limits}))

    return scenario.model_copy(update={
        "name": "Coordinated Demo - Sensor Disagreement",
        "scenario_id": "coordinated-demo-sensor-disagreement",
        "random_seed": 4242,
        "sensors": sensors,
        "contacts": contacts,
    })


def _unit_interval(seed: str) -> float:
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def apply_measurement_noise(outputs: dict[str, list[dict]], scenario: Scenario) -> None:
    """Add small errors to random sensor/track/timestamp reports from this scenario."""
    for sensor_id, messages in outputs.items():
        for message in messages:
            if not any(field in message for field in ("azimuth_deg", "bearing_deg", "elevation_deg")):
                continue
            track = message.get("track_id", message.get("emitter_id", "no-track"))
            event_key = f"{scenario.random_seed}|{sensor_id}|{track}|{message['timestamp']}"
            # A random subset of sensors is assigned occasional angular glitches;
            # the digest ties timing to the actual generated track and timestamp.
            sensor_selected = _unit_interval(f"{scenario.random_seed}|sensor|{sensor_id}") < 0.7
            event_selected = _unit_interval(event_key) < 0.18
            if not sensor_selected or not event_selected:
                continue
            azimuth_delta = (-1.2 if _unit_interval(event_key + "|az") < 0.5 else 1.2)
            elevation_delta = (-0.6 if _unit_interval(event_key + "|el") < 0.5 else 0.6)
            if "azimuth_deg" in message:
                message["azimuth_deg"] = round((message["azimuth_deg"] + azimuth_delta) % 360, 1)
            if "bearing_deg" in message:
                message["bearing_deg"] = round((message["bearing_deg"] + azimuth_delta) % 360, 1)
            if "elevation_deg" in message:
                message["elevation_deg"] = round(message["elevation_deg"] + elevation_delta, 1)


def main() -> None:
    scenario = build_disagreement_scenario()
    outputs = generate_outputs(scenario)
    apply_measurement_noise(outputs, scenario)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for old_file in OUTPUT_DIR.glob("*.json"):
        old_file.unlink()
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
