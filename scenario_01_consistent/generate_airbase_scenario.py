"""Generate a reproducible synthetic asynchronous C2 sensor dataset."""

from __future__ import annotations

import json
import math
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


random.seed(42)

OUTPUT_DIR = Path(__file__).resolve().parent / "synthetic_airbase_data"
AIRBASE = {
    "site_id": "AIRBASE_01",
    "latitude": 1.3500,
    "longitude": 104.0000,
    "coordinate_system": "WGS84",
    "scenario_start": "14:30:00",
    "scenario_end": "15:00:00",
}
OBJECT_IDS = [f"UAS-{index:02d}" for index in range(1, 6)]
START_TIME = datetime(2026, 9, 25, 14, 30)
END_TIME = datetime(2026, 9, 25, 15, 0)

# Synthetic local east/north offsets in kilometres. They are converted to WGS84.
START_OFFSETS = [(19.3, -2.0), (20.1, 0.8), (21.0, 2.3), (20.7, 3.7), (22.0, -0.6)]
END_OFFSETS = [(1.6, -1.5), (2.4, 0.7), (3.2, 2.0), (2.0, 3.0), (3.8, -0.3)]

MPSTAR_FIELDS = {
    "sensor_id", "timestamp", "track_id", "azimuth_deg", "range_km",
    "classification", "subtype",
}
EOIR_FIELDS = {
    "sensor_id", "timestamp", "track_id", "azimuth_deg", "elevation_deg",
    "classification", "subtype", "confidence", "image",
}
EW_FIELDS = {
    "sensor_id", "timestamp", "emitter_id", "detected", "bearing_deg",
    "classification", "confidence",
}


def save_json(filename: str, data: Any) -> None:
    """Save one JSON file in the generated-data directory."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    (OUTPUT_DIR / filename).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def scheduled_times(step_minutes: int, second: int) -> list[datetime]:
    """Create scan times from 14:30 through 15:00 inclusive."""
    times = []
    current = START_TIME.replace(second=second)
    while current <= END_TIME.replace(second=second):
        times.append(current)
        current += timedelta(minutes=step_minutes)
    return times


def timestamp(value: datetime) -> str:
    return value.strftime("%H:%M:%S")


def offset_to_wgs84(east_km: float, north_km: float) -> tuple[float, float]:
    """Convert a small local offset into a synthetic WGS84 coordinate."""
    earth_radius_km = 6371.0088
    latitude = AIRBASE["latitude"] + math.degrees(north_km / earth_radius_km)
    longitude = AIRBASE["longitude"] + math.degrees(
        east_km / (earth_radius_km * math.cos(math.radians(AIRBASE["latitude"])))
    )
    return round(latitude, 6), round(longitude, 6)


def position_for(object_index: int, moment: datetime) -> tuple[float, float, float, float]:
    """Return latitude, longitude, range and bearing for one UAS at a time."""
    fraction = (moment - START_TIME).total_seconds() / (END_TIME - START_TIME).total_seconds()
    start_east, start_north = START_OFFSETS[object_index]
    end_east, end_north = END_OFFSETS[object_index]
    east = start_east + (end_east - start_east) * fraction
    north = start_north + (end_north - start_north) * fraction
    latitude, longitude = offset_to_wgs84(east, north)
    range_km = math.hypot(east, north)
    bearing_deg = (math.degrees(math.atan2(east, north)) + 360) % 360
    return latitude, longitude, range_km, bearing_deg


def generate_ground_truth() -> list[dict[str, Any]]:
    """Generate one geographic position per UAS for every simulation minute."""
    positions = []
    moment = START_TIME
    while moment <= END_TIME:
        for object_index, object_id in enumerate(OBJECT_IDS):
            latitude, longitude, _, _ = position_for(object_index, moment)
            positions.append({
                "object_id": object_id,
                "timestamp": timestamp(moment),
                "latitude": latitude,
                "longitude": longitude,
            })
        moment += timedelta(minutes=1)
    return positions


def generate_mpstar_data() -> list[dict[str, Any]]:
    """Generate five persistent MPSTAR tracks every two minutes."""
    records = []
    for moment in scheduled_times(2, 0):
        for object_index in range(5):
            _, _, range_km, bearing = position_for(object_index, moment)
            records.append({
                "sensor_id": "MPSTAR_AIRBASE_01",
                "timestamp": timestamp(moment),
                "track_id": f"RDR-{object_index + 1:03d}",
                "azimuth_deg": round((bearing + random.uniform(-0.25, 0.25)) % 360, 1),
                "range_km": round(max(0.1, range_km + random.uniform(-0.04, 0.04)), 2),
                "classification": "UAS",
                "subtype": "fixed-wing",
            })
    return records


def generate_eoir_data() -> list[dict[str, Any]]:
    """Generate EO/IR observations every three minutes with gradual detection growth."""
    records = []
    visible_objects = [3, 3, 4] + [5] * 8
    for scan_index, moment in enumerate(scheduled_times(3, 1)):
        confidence_base = 0.68 + scan_index * 0.025
        for object_index in range(visible_objects[scan_index]):
            _, _, _, bearing = position_for(object_index, moment)
            records.append({
                "sensor_id": "EOIR_AIRBASE_01",
                "timestamp": timestamp(moment),
                "track_id": f"EO-{object_index + 1:03d}",
                "azimuth_deg": round((bearing + random.uniform(-0.4, 0.4)) % 360, 1),
                "elevation_deg": round(6.0 + object_index * 0.6 + random.uniform(-0.15, 0.15), 1),
                "classification": "UAS",
                "subtype": "fixed-wing",
                "confidence": round(min(0.98, confidence_base + random.uniform(-0.02, 0.02)), 2),
                "image": f"EO{object_index + 1:03d}_{moment.strftime('%H%M%S')}.jpg",
            })
    return records


def generate_ew_data() -> list[dict[str, Any]]:
    """Generate general-sector RF evidence every five minutes."""
    records = []
    for scan_index, moment in enumerate(scheduled_times(5, 2)):
        _, _, _, bearing = position_for(2, moment)
        records.append({
            "sensor_id": "AIRBASE_EW_01",
            "timestamp": timestamp(moment),
            "emitter_id": "RF-001",
            "detected": True,
            "bearing_deg": round((bearing + random.uniform(-1.2, 1.2)) % 360, 1),
            "classification": "suspected_uas_link",
            "confidence": round(min(0.95, 0.70 + scan_index * 0.035 + random.uniform(-0.02, 0.02)), 2),
        })
    return records


def generate_associations() -> dict[str, dict[str, str]]:
    """Generate development-only object-to-track relationships."""
    return {
        object_id: {
            "mpstar_track": f"RDR-{index:03d}",
            "eoir_track": f"EO-{index:03d}",
        }
        for index, object_id in enumerate(OBJECT_IDS, start=1)
    }


def combine_sensor_events(sensor_data: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Combine raw records without adding fields and sort chronologically."""
    return sorted(
        [record for records in sensor_data for record in records],
        key=lambda record: record["timestamp"],
    )


def validate_schemas(data: dict[str, list[dict[str, Any]]]) -> None:
    """Validate exact schemas and the basic consistency rules in the specification."""
    expected = {"mpstar": MPSTAR_FIELDS, "eoir": EOIR_FIELDS, "ew": EW_FIELDS}
    for name, fields in expected.items():
        for record_number, record in enumerate(data[name], start=1):
            if set(record) != fields:
                raise ValueError(f"{name}.json record {record_number} does not match its exact schema")
            if {"latitude", "longitude"} & set(record):
                raise ValueError(f"{name}.json contains geographic ground truth")
            if any(object_id in json.dumps(record) for object_id in OBJECT_IDS):
                raise ValueError(f"{name}.json exposes a ground-truth object ID")
            if name in {"eoir", "ew"} and not 0 <= record["confidence"] <= 1:
                raise ValueError(f"{name}.json confidence is outside 0..1")

    sensor_ids = {
        "mpstar": "MPSTAR_AIRBASE_01",
        "eoir": "EOIR_AIRBASE_01",
        "ew": "AIRBASE_EW_01",
    }
    for name, sensor_id in sensor_ids.items():
        if any(record["sensor_id"] != sensor_id for record in data[name]):
            raise ValueError(f"Unexpected {name} sensor ID")

    start_seconds = START_TIME.hour * 3600 + START_TIME.minute * 60
    end_seconds = END_TIME.hour * 3600 + END_TIME.minute * 60 + 2
    for records in data.values():
        for record in records:
            parsed = datetime.strptime(record["timestamp"], "%H:%M:%S")
            seconds = parsed.hour * 3600 + parsed.minute * 60 + parsed.second
            if not start_seconds <= seconds <= end_seconds:
                raise ValueError("A raw sensor timestamp is outside the scenario window")

    tracks = {record["track_id"] for record in data["mpstar"]}
    if tracks != {f"RDR-{index:03d}" for index in range(1, 6)}:
        raise ValueError("MPSTAR tracks are not persistent or complete")
    for track_id in tracks:
        ranges = [record["range_km"] for record in data["mpstar"] if record["track_id"] == track_id]
        if any(later >= earlier for earlier, later in zip(ranges, ranges[1:])):
            raise ValueError(f"MPSTAR range did not decrease for {track_id}")

    eoir_tracks = {record["track_id"] for record in data["eoir"]}
    if not eoir_tracks <= {f"EO-{index:03d}" for index in range(1, 6)}:
        raise ValueError("EO/IR track IDs are invalid")
    events = combine_sensor_events(list(data.values()))
    if [event["timestamp"] for event in events] != sorted(event["timestamp"] for event in events):
        raise ValueError("all_sensor_events.json is not chronologically sorted")


def validate_ground_truth(positions: list[dict[str, Any]]) -> None:
    """Validate WGS84 bounds and movement toward the fixed airbase."""
    if len(positions) != 155:
        raise ValueError("Expected 31 ground-truth timestamps for five objects")
    for position in positions:
        if not -90 <= position["latitude"] <= 90 or not -180 <= position["longitude"] <= 180:
            raise ValueError("Invalid WGS84 coordinate")
    for object_index in range(5):
        start = positions[object_index]
        end = positions[-5 + object_index]
        start_distance = math.hypot(
            (start["longitude"] - AIRBASE["longitude"]) * 111.32,
            (start["latitude"] - AIRBASE["latitude"]) * 111.32,
        )
        end_distance = math.hypot(
            (end["longitude"] - AIRBASE["longitude"]) * 111.32,
            (end["latitude"] - AIRBASE["latitude"]) * 111.32,
        )
        if end_distance >= start_distance:
            raise ValueError(f"{start['object_id']} did not move toward AIRBASE_01")


def main() -> None:
    """Generate, validate and save the complete dataset."""
    data = {
        "mpstar": generate_mpstar_data(),
        "eoir": generate_eoir_data(),
        "ew": generate_ew_data(),
    }
    ground_truth = generate_ground_truth()
    validate_schemas(data)
    validate_ground_truth(ground_truth)
    save_json("scenario_config.json", AIRBASE)
    save_json("mpstar.json", data["mpstar"])
    save_json("eoir.json", data["eoir"])
    save_json("ew.json", data["ew"])
    save_json("ground_truth_positions.json", ground_truth)
    save_json("ground_truth_associations.json", generate_associations())
    save_json("all_sensor_events.json", combine_sensor_events(list(data.values())))
    print(f"Generated data in {OUTPUT_DIR}")
    print(f"MPSTAR: {len(data['mpstar'])} observations")
    print(f"EO/IR: {len(data['eoir'])} observations")
    print(f"EW: {len(data['ew'])} observations")


if __name__ == "__main__":
    main()
