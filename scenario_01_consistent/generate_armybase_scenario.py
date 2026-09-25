"""Generate Army Base sensors for the shared Scenario 1 event.

This script reads the existing AIRBASE_01 configuration and ground truth. It
never regenerates or writes the Airbase dataset.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


random.seed(42)
ROOT = Path(__file__).resolve().parent
AIRBASE_DIR = ROOT / "synthetic_airbase_data"
OUTPUT_DIR = ROOT / "synthetic_armybase_data"
OBJECT_IDS = [f"UAS-{index:02d}" for index in range(1, 6)]
START_TIME = datetime.strptime("14:30:00", "%H:%M:%S")
END_TIME = datetime.strptime("15:00:00", "%H:%M:%S")

EOIR_FIELDS = {
    "sensor_id", "timestamp", "track_id", "azimuth_deg", "elevation_deg",
    "classification", "subtype", "confidence", "image",
}
CCTV_FIELDS = {
    "sensor_id", "timestamp", "camera_id", "detected", "classification",
    "confidence", "image",
}
EW_FIELDS = {
    "sensor_id", "timestamp", "emitter_id", "detected", "bearing_deg",
    "classification", "confidence",
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(filename: str, data: Any) -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    (OUTPUT_DIR / filename).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def timestamp(moment: datetime) -> str:
    return moment.strftime("%H:%M:%S")


def scheduled_times(step_minutes: int, second: int) -> list[datetime]:
    """Create an asynchronous scan schedule through 15:00 inclusive."""
    times = []
    moment = START_TIME.replace(second=second)
    while moment <= END_TIME.replace(second=second):
        times.append(moment)
        moment += timedelta(minutes=step_minutes)
    return times


def calculate_army_site(airbase_config: dict[str, Any]) -> dict[str, Any]:
    """Place Army Base 2 km southwest of AIRBASE_01 using WGS84 math."""
    earth_radius_km = 6371.0088
    distance_km = 2.0
    southwest_radians = math.radians(225)
    north_km = distance_km * math.cos(southwest_radians)
    east_km = distance_km * math.sin(southwest_radians)
    airbase_latitude = airbase_config["latitude"]
    airbase_longitude = airbase_config["longitude"]
    latitude = airbase_latitude + math.degrees(north_km / earth_radius_km)
    longitude = airbase_longitude + math.degrees(
        east_km / (earth_radius_km * math.cos(math.radians(airbase_latitude)))
    )
    return {
        "site_id": "ARMY_BASE_01",
        "latitude": round(latitude, 6),
        "longitude": round(longitude, 6),
        "coordinate_system": "WGS84",
        "relative_to": "AIRBASE_01",
        "approx_distance_km": 2.0,
        "relative_direction": "southwest",
        "scenario_start": airbase_config["scenario_start"],
        "scenario_end": airbase_config["scenario_end"],
    }


def load_shared_ground_truth() -> dict[str, list[dict[str, Any]]]:
    """Load the existing Airbase positions grouped by physical UAS ID."""
    grouped = {object_id: [] for object_id in OBJECT_IDS}
    for position in read_json(AIRBASE_DIR / "ground_truth_positions.json"):
        grouped[position["object_id"]].append(position)
    if any(len(positions) != 31 for positions in grouped.values()):
        raise ValueError("Airbase ground truth must contain 31 positions per UAS")
    return grouped


def interpolate_position(positions: list[dict[str, Any]], moment: datetime) -> tuple[float, float]:
    """Interpolate the shared minute-resolution trajectory at a scan time."""
    minute = (moment - START_TIME).total_seconds() / 60
    lower_index = min(30, max(0, int(minute)))
    upper_index = min(30, lower_index + 1)
    fraction = minute - lower_index
    lower = positions[lower_index]
    upper = positions[upper_index]
    latitude = lower["latitude"] + (upper["latitude"] - lower["latitude"]) * fraction
    longitude = lower["longitude"] + (upper["longitude"] - lower["longitude"]) * fraction
    return latitude, longitude


def bearing_and_elevation(site: dict[str, Any], latitude: float, longitude: float) -> tuple[float, float]:
    """Calculate a local bearing and simple synthetic elevation from a site."""
    north_km = (latitude - site["latitude"]) * 111.32
    east_km = (longitude - site["longitude"]) * 111.32 * math.cos(math.radians(site["latitude"]))
    bearing = (math.degrees(math.atan2(east_km, north_km)) + 360) % 360
    distance_km = math.hypot(east_km, north_km)
    elevation = math.degrees(math.atan2(1.0, max(distance_km, 0.1)))
    return bearing, elevation


def generate_eoir_data(site: dict[str, Any], ground_truth: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Generate Army EO/IR observations from the shared UAS positions."""
    records = []
    visible_objects = [3, 3, 4] + [5] * 8
    for scan_index, moment in enumerate(scheduled_times(3, 1)):
        for object_index in range(visible_objects[scan_index]):
            latitude, longitude = interpolate_position(ground_truth[OBJECT_IDS[object_index]], moment)
            bearing, elevation = bearing_and_elevation(site, latitude, longitude)
            records.append({
                "sensor_id": "EOIR_ARMYBASE_01",
                "timestamp": timestamp(moment),
                "track_id": f"ARMY-EO-{object_index + 1:03d}",
                "azimuth_deg": round((bearing + random.uniform(-0.4, 0.4)) % 360, 1),
                "elevation_deg": round(elevation + random.uniform(-0.15, 0.15), 1),
                "classification": "UAS",
                "subtype": "fixed-wing",
                "confidence": round(min(0.98, 0.68 + scan_index * 0.025 + random.uniform(-0.02, 0.02)), 2),
                "image": f"ARMY_EO{object_index + 1:03d}_{moment.strftime('%H%M%S')}.jpg",
            })
    return records


def generate_cctv_data() -> list[dict[str, Any]]:
    """Generate simple visual detections without one-to-one UAS mapping."""
    records = []
    cameras = ["CAM-001", "CAM-002", "CAM-003"]
    for scan_index, moment in enumerate(scheduled_times(4, 5)):
        camera_id = cameras[scan_index % len(cameras)]
        records.append({
            "sensor_id": "CCTV_ARMYBASE_01",
            "timestamp": timestamp(moment),
            "camera_id": camera_id,
            "detected": True,
            "classification": "UAS",
            "confidence": round(min(0.96, 0.76 + scan_index * 0.025 + random.uniform(-0.02, 0.02)), 2),
            "image": f"{camera_id.replace('-', '')}_{moment.strftime('%H%M%S')}.jpg",
        })
    return records


def generate_ew_data(site: dict[str, Any], ground_truth: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Generate one persistent general-event RF signature from Army Base."""
    records = []
    for scan_index, moment in enumerate(scheduled_times(5, 2)):
        latitude, longitude = interpolate_position(ground_truth["UAS-03"], moment)
        bearing, _ = bearing_and_elevation(site, latitude, longitude)
        records.append({
            "sensor_id": "ARMYBASE_EW_01",
            "timestamp": timestamp(moment),
            "emitter_id": "RF-001",
            "detected": True,
            "bearing_deg": round((bearing + random.uniform(-1.2, 1.2)) % 360, 1),
            "classification": "suspected_uas_link",
            "confidence": round(min(0.95, 0.70 + scan_index * 0.035 + random.uniform(-0.02, 0.02)), 2),
        })
    return records


def generate_associations() -> dict[str, dict[str, str]]:
    """Create Army EO/IR associations without mapping CCTV or RF activity."""
    return {
        object_id: {"army_eoir_track": f"ARMY-EO-{index:03d}"}
        for index, object_id in enumerate(OBJECT_IDS, start=1)
    }


def combine_sensor_events(sensor_data: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Combine Army raw records without adding fields."""
    return sorted(
        [copy.deepcopy(record) for records in sensor_data for record in records],
        key=lambda record: record["timestamp"],
    )


def validate_records(name: str, records: list[dict[str, Any]], fields: set[str], sensor_id: str) -> None:
    """Require exact fields, expected source ID, valid confidence, and no leakage."""
    for record in records:
        if set(record) != fields:
            raise ValueError(f"{name} record does not match its exact schema")
        if record["sensor_id"] != sensor_id:
            raise ValueError(f"Unexpected {name} sensor ID")
        if not 0 <= record["confidence"] <= 1:
            raise ValueError(f"{name} confidence is outside 0..1")
        serialized = json.dumps(record)
        if any(object_id in serialized for object_id in OBJECT_IDS):
            raise ValueError(f"{name} exposes a ground-truth UAS ID")
        if {"latitude", "longitude"} & set(record):
            raise ValueError(f"{name} exposes geographic ground truth")


def validate_dataset(
    site: dict[str, Any],
    ground_truth: dict[str, list[dict[str, Any]]],
    data: dict[str, list[dict[str, Any]]],
) -> None:
    """Run Army schema, timing, geometry, persistence, and ordering checks."""
    validate_records("EO/IR", data["eoir"], EOIR_FIELDS, "EOIR_ARMYBASE_01")
    validate_records("CCTV", data["cctv"], CCTV_FIELDS, "CCTV_ARMYBASE_01")
    validate_records("EW", data["ew"], EW_FIELDS, "ARMYBASE_EW_01")
    if {record["emitter_id"] for record in data["ew"]} != {"RF-001"}:
        raise ValueError("Army EW must use one persistent RF-001 emitter")
    if {record["track_id"] for record in data["eoir"]} - {f"ARMY-EO-{index:03d}" for index in range(1, 6)}:
        raise ValueError("Unexpected Army EO/IR track ID")
    start_seconds = START_TIME.hour * 3600 + START_TIME.minute * 60
    end_seconds = END_TIME.hour * 3600 + END_TIME.minute * 60 + 5
    for records in data.values():
        for record in records:
            parsed = datetime.strptime(record["timestamp"], "%H:%M:%S")
            seconds = parsed.hour * 3600 + parsed.minute * 60 + parsed.second
            if not start_seconds <= seconds <= end_seconds:
                raise ValueError("Army sensor timestamp is outside the scenario window")
    distance_km = math.hypot(
        (site["longitude"] - read_json(AIRBASE_DIR / "scenario_config.json")["longitude"]) * 111.32,
        (site["latitude"] - read_json(AIRBASE_DIR / "scenario_config.json")["latitude"]) * 111.32,
    )
    if not 1.8 <= distance_km <= 2.2 or not site["latitude"] < read_json(AIRBASE_DIR / "scenario_config.json")["latitude"] or not site["longitude"] < read_json(AIRBASE_DIR / "scenario_config.json")["longitude"]:
        raise ValueError("Army Base is not approximately 2 km southwest of AIRBASE_01")
    events = combine_sensor_events(list(data.values()))
    if [event["timestamp"] for event in events] != sorted(event["timestamp"] for event in events):
        raise ValueError("Army all_sensor_events.json is not chronologically sorted")
    if len(ground_truth) != 5 or any(len(positions) != 31 for positions in ground_truth.values()):
        raise ValueError("Shared ground truth is incomplete")


def file_hashes(paths: list[Path]) -> dict[Path, str]:
    """Capture existing Airbase files so accidental overwrites can be detected."""
    return {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def main() -> None:
    """Read Airbase inputs, generate Army outputs, validate, and save."""
    config_path = AIRBASE_DIR / "scenario_config.json"
    ground_truth_path = AIRBASE_DIR / "ground_truth_positions.json"
    airbase_files = list(AIRBASE_DIR.glob("*.json"))
    before_hashes = file_hashes(airbase_files)
    airbase_config = read_json(config_path)
    ground_truth = load_shared_ground_truth()
    army_site = calculate_army_site(airbase_config)
    data = {
        "eoir": generate_eoir_data(army_site, ground_truth),
        "cctv": generate_cctv_data(),
        "ew": generate_ew_data(army_site, ground_truth),
    }
    validate_dataset(army_site, ground_truth, data)
    save_json("scenario_config.json", army_site)
    save_json("eoir.json", data["eoir"])
    save_json("cctv.json", data["cctv"])
    save_json("ew.json", data["ew"])
    save_json("ground_truth_associations.json", generate_associations())
    save_json("all_sensor_events.json", combine_sensor_events(list(data.values())))
    after_hashes = file_hashes(airbase_files)
    if before_hashes != after_hashes:
        raise RuntimeError("Existing AIRBASE_01 files were modified")
    print(f"Generated data in {OUTPUT_DIR}")
    print(f"Army EO/IR: {len(data['eoir'])} observations")
    print(f"Army CCTV: {len(data['cctv'])} observations")
    print(f"Army EW: {len(data['ew'])} observations")
    print(f"ARMY_BASE_01: {army_site['latitude']}, {army_site['longitude']}")


if __name__ == "__main__":
    main()
