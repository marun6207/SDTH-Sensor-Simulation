"""Create Scenario 2 shared truth and Airbase observations; shared validation helpers."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import random

OUTPUT = Path(__file__).resolve().parent
ROOT = OUTPUT.parent
SEED = 20260925
RADIUS = 6371.0088
IDS = [f"UAS-{i:02d}" for i in range(1, 6)]
SITES = {
    "AIRBASE_02": {"latitude": 1.275000, "longitude": 103.820000},
    "ARMY_BASE_02": {"latitude": 1.263000, "longitude": 103.829000},
}
AIR = "synthetic_airbase_02_data"
ARMY = "synthetic_armybase_02_data"
# site, filename, sensor ID, interval in minutes, second offset
SENSORS = [
    (AIR, "mpstar", "MPSTAR_AIRBASE_02", 2, 0),
    (AIR, "eoir", "EOIR_AIRBASE_02", 3, 1),
    (AIR, "ew", "AIRBASE_EW_02", 5, 2),
    (ARMY, "eoir", "EOIR_ARMYBASE_02", 3, 1),
    (ARMY, "cctv", "CCTV_ARMYBASE_02", 4, 5),
    (ARMY, "ew", "ARMYBASE_EW_02", 5, 2),
]
FIELDS = {
    "mpstar": set("sensor_id timestamp track_id azimuth_deg range_km classification subtype".split()),
    "eoir": set("sensor_id timestamp track_id azimuth_deg elevation_deg classification subtype confidence image".split()),
    "ew": set("sensor_id timestamp emitter_id detected bearing_deg classification confidence".split()),
    "cctv": set("sensor_id timestamp camera_id detected classification confidence image".split()),
}
COUNTS = {AIR: [2, 3, 3, 4, 4, 5, 5, 5, 5, 5], ARMY: [3, 3, 4, 4, 5, 5, 5, 5, 5, 5]}
# Different acquisition order models the two viewpoints, independently of local IDs.
ORDERS = {AIR: [0, 2, 4, 1, 3], ARMY: [1, 3, 0, 4, 2]}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def stamp(seconds):
    total = 14 * 3600 + 30 * 60 + seconds
    return f"{total // 3600:02d}:{total // 60 % 60:02d}:{total % 60:02d}"


def schedule(minutes, second):
    return list(range(second, 1801, minutes * 60))


def geometry(site, position):
    """Spherical surface range/bearing, flat local elevation; site altitude = 0 m."""
    lat1, lat2 = map(math.radians, (site["latitude"], position["latitude"]))
    delta = math.radians(position["longitude"] - site["longitude"])
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta / 2) ** 2
    distance = 2 * RADIUS * math.asin(math.sqrt(min(1, a)))
    bearing = math.degrees(math.atan2(math.sin(delta) * math.cos(lat2),
        math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(delta))) % 360
    elevation = math.degrees(math.atan2(position.get("altitude_m", 0) / 1000, distance))
    return round(bearing, 3), round(distance, 4), round(elevation, 3)


def trajectories():
    """Continuous curved paths, sampled each second including every observation time."""
    rng = random.Random(SEED)
    parameters = []
    for i in range(5):
        parameters.append((-24 + i * .55 + rng.uniform(-.15, .15),
                           -23 + (i % 3) * .7 + rng.uniform(-.15, .15),
                           -1.5 + i * .3, -1.7 + (i % 3) * .4,
                           rng.uniform(-.65, .65), rng.uniform(-.65, .65),
                           650 + i * 65, rng.uniform(0, math.pi)))
    positions = []
    for second in range(1801):
        f = second / 1800
        for object_id, (sx, sy, ex, ey, cx, cy, altitude, phase) in zip(IDS, parameters):
            east = sx + (ex - sx) * f + cx * math.sin(math.pi * f)
            north = sy + (ey - sy) * f + cy * math.sin(math.pi * f)
            positions.append({"timestamp": stamp(second), "uas_id": object_id,
                "latitude": round(1.269 + math.degrees(north / RADIUS), 9),
                "longitude": round(103.8245 + math.degrees(east / (RADIUS * math.cos(math.radians(1.269)))), 9),
                "altitude_m": round(altitude + 35 * math.sin(2 * math.pi * f + phase), 3)})
    return positions


def associations():
    rng = random.Random(SEED + 1)
    result = {uid: {} for uid in IDS}
    for key, prefix in [("mpstar", "RDR"), ("airbase_eoir", "EO"), ("armybase_eoir", "ARMY-EO")]:
        numbers = list(range(1, 6))
        rng.shuffle(numbers)
        for uid, number in zip(IDS, numbers):
            result[uid][key] = f"{prefix}-{number:03d}"
    return result


def confidence(rng, scan, distance, modality):
    base = {"eoir": .61, "ew": .66, "cctv": .70}[modality]
    # Alternating small quality changes ensure confidence is not perfectly monotonic.
    quality = .035 if scan % 2 == 0 else -.035
    return round(max(.1, min(.97, base + .22 * (1 - min(distance / 34, 1))
                             + quality + rng.uniform(-.012, .012))), 3)


def combine(streams):
    return sorted([r for stream in streams for r in stream], key=lambda r: (r["timestamp"], r["sensor_id"], r.get("track_id", "")))


# Fingerprint of the original deterministic physical scenario. Validation can verify
# the exact trajectories without regenerating them in the Army process.
TRAJECTORY_SHA256 = "75304c6f9eeb9ceaba67617a91b8beda32f6e4252d62eba3277b67487dd9585a"


def build(positions, mapping, folders=(AIR, ARMY)):
    """Derive requested site outputs from supplied truth; never create trajectories."""
    truth = {(p["timestamp"], p["uas_id"]): p for p in positions}
    files = {"shared_ground_truth/ground_truth_positions.json": positions,
             "shared_ground_truth/ground_truth_associations.json": mapping}
    for sensor_index, (folder, kind, sensor_id, minutes, offset) in enumerate(SENSORS):
        if folder not in folders:
            continue
        site = SITES["AIRBASE_02" if folder == AIR else "ARMY_BASE_02"]
        rng = random.Random(SEED + 100 + sensor_index)
        records = []
        for scan, second in enumerate(schedule(minutes, offset)):
            time = stamp(second)
            group = [truth[time, uid] for uid in IDS]
            centroid = {field: sum(p[field] for p in group) / 5 for field in ("latitude", "longitude", "altitude_m")}
            bearing, distance, _ = geometry(site, centroid)
            if kind in ("ew", "cctv"):
                event = {"sensor_id": sensor_id, "timestamp": time, "detected": True,
                         "classification": "suspected_uas_link" if kind == "ew" else "UAS",
                         "confidence": confidence(rng, scan, distance, kind)}
                if kind == "ew":
                    event.update(emitter_id="RF-001", bearing_deg=bearing)
                else:
                    camera = f"CAM-{scan % 3 + 1:03d}"
                    event.update(camera_id=camera, image=f"{camera.replace('-', '')}_{time.replace(':', '')}.jpg")
                records.append(event)
                continue
            selected = range(5) if kind == "mpstar" else ORDERS[folder][:COUNTS[folder][scan]]
            key = "mpstar" if kind == "mpstar" else "airbase_eoir" if folder == AIR else "armybase_eoir"
            for i in selected:
                track = mapping[IDS[i]][key]
                bearing, distance, elevation = geometry(site, group[i])
                event = {"sensor_id": sensor_id, "timestamp": time, "track_id": track,
                         "azimuth_deg": bearing, "classification": "UAS", "subtype": "fixed-wing"}
                if kind == "mpstar":
                    event["range_km"] = distance
                else:
                    event.update(elevation_deg=elevation, confidence=confidence(rng, scan, distance, kind),
                                 image=f"{track.replace('-', '')}_{time.replace(':', '')}.jpg")
                    if folder == AIR and scan == 4 and i == 2:
                        event.update(classification="UNKNOWN", subtype="unknown", confidence=.38)
                records.append(event)
        files[f"{folder}/{kind}.json"] = records
    config = {"scenario_id": "SCENARIO_02", "scenario_name": "Southwest UAS Approach with Multi-Sensor Disagreement",
              "start_time": "14:30:00", "end_time": "15:00:00", "hidden_physical_uas_count": 5,
              "general_approach_direction": "southwest to northeast", "fixed_random_seed": SEED,
              "sites": SITES, "coordinate_system": "WGS84", "site_altitude_m": 0,
              "timing_policy": "Strict inclusive end at 15:00:00; later second-offset updates are outside the window.",
              "geometry_model": "Spherical Earth radius 6371.0088 km; surface radar range; local flat elevation from altitude.",
              "trajectory_model": "Linear east/north approach with smooth sinusoidal lateral and altitude variation; one-second truth samples.",
              "resolution_model": "Scripted acquisition by viewpoint: Airbase object order 1,3,5,2,4; Army 2,4,1,5,3. Unresolved objects still exist.",
              "sensor_schedules": {sid: {"interval_minutes": m, "second": s} for _, _, sid, m, s in SENSORS}}
    files["scenario_config.json"] = config
    for folder, site_id in [(AIR, "AIRBASE_02"), (ARMY, "ARMY_BASE_02")]:
        if folder not in folders:
            continue
        files[f"{folder}/scenario_config.json"] = {"scenario_id": "SCENARIO_02", "site_id": site_id,
            **SITES[site_id], "start_time": config["start_time"], "end_time": config["end_time"],
            "sensor_schedules": {sid: config["sensor_schedules"][sid] for f, _, sid, _, _ in SENSORS if f == folder}}
        files[f"{folder}/all_sensor_events.json"] = combine([files[f"{f}/{k}.json"] for f, k, *_ in SENSORS if f == folder])
    if AIR in folders and ARMY in folders:
        files["scenario_02_all_sensor_events.json"] = combine([files[f"{f}/{k}.json"] for f, k, *_ in SENSORS])
    if AIR not in folders:
        return files
    unknown = next(r for r in files[f"{AIR}/eoir.json"] if r["classification"] == "UNKNOWN")
    files["shared_ground_truth/scenario_02_expected_behavior.json"] = {
        "development_only": True, "hidden_physical_uas_count": 5, "expected_mpstar_count_per_scan": 5,
        "eoir_counts": [{"timestamp": stamp(t), "airbase": COUNTS[AIR][i], "armybase": COUNTS[ARMY][i]}
                        for i, t in enumerate(schedule(3, 1))],
        "classification_uncertainty": {"sensor_id": unknown["sensor_id"], "track_id": unknown["track_id"],
            "timestamp": unknown["timestamp"], "classification": "UNKNOWN", "subtype": "unknown", "confidence": .38,
            "restored_timestamp": "14:45:01", "restored_classification": "UAS", "restored_subtype": "fixed-wing"},
        "ew_support": "Every scheduled update detected=true; RF-001 is group-sector evidence from the centroid, never a one-to-one UAS ID.",
        "cctv_support": "Every scheduled update detected=true; three rotating cameras provide event-level evidence, not object counts.",
        "strong_disagreement_period": "14:30:00 through 14:42:01: count/subset differences and temporary visual uncertainty.",
        "increasing_corroboration_period": "14:45:01 through 15:00:00: both EO sensors resolve five; confidence still varies.",
        "early_snapshot": {"window": "14:30:00 through 14:30:05", "mpstar": 5, "airbase_eoir": 2,
                           "armybase_eoir": 3, "airbase_ew_detected": True, "armybase_ew_detected": True, "cctv_detected": True}}
    return files


def validate_scenario_01():
    folder = ROOT / "scenario_01_consistent"
    manifest = read(folder / "original_sha256.json")
    actual_paths = {p.relative_to(folder).as_posix() for name in ("synthetic_airbase_data", "synthetic_armybase_data") for p in (folder / name).rglob("*") if p.is_file()}
    require(actual_paths == set(manifest), "Scenario 1 file inventory changed")
    for name, digest in manifest.items():
        require(hashlib.sha256((folder / name).read_bytes()).hexdigest() == digest,
                f"Scenario 1 bytes changed: {name}")


def validate(files, folders=(AIR, ARMY)):
    validate_scenario_01()
    config = files["scenario_config.json"]
    require(config["sites"] == SITES, "Incorrect synthetic site coordinates")
    require(1 <= geometry(SITES["AIRBASE_02"], SITES["ARMY_BASE_02"])[1] <= 2, "Sites must be 1–2 km apart")
    positions = files["shared_ground_truth/ground_truth_positions.json"]
    require(hashlib.sha256(json.dumps(positions, sort_keys=True).encode()).hexdigest() == TRAJECTORY_SHA256,
            "Shared trajectories differ from the original seeded Scenario 2")
    truth = {(p["timestamp"], p["uas_id"]): p for p in positions}
    require(len(positions) == len(truth) == 1801 * 5 and {p["uas_id"] for p in positions} == set(IDS), "Expected exactly five complete physical trajectories")
    for uid in IDS:
        path = [truth[stamp(t), uid] for t in range(1801)]
        for site in SITES.values():
            require(path[0]["latitude"] < site["latitude"] and path[0]["longitude"] < site["longitude"], f"{uid} must start southwest")
            require(geometry(site, path[-1])[1] < geometry(site, path[0])[1], f"{uid} must approach defended sites")
        require(all(b["latitude"] > a["latitude"] and b["longitude"] > a["longitude"] and geometry(a, b)[1] < .05 for a, b in zip(path, path[1:])), f"{uid} trajectory discontinuity or wrong direction")
    mapping = files["shared_ground_truth/ground_truth_associations.json"]
    require(set(mapping) == set(IDS), "Association object inventory mismatch")
    for key, prefix in [("mpstar", "RDR"), ("airbase_eoir", "EO"), ("armybase_eoir", "ARMY-EO")]:
        require({mapping[u][key] for u in IDS} == {f"{prefix}-{i:03d}" for i in range(1, 6)}, f"Invalid {key} ID mapping")
        require(any(mapping[u][key] != f"{prefix}-{i:03d}" for i, u in enumerate(IDS, 1)), f"Unshuffled {key} IDs")
    require(all(set(m) == {"mpstar", "airbase_eoir", "armybase_eoir"} for m in mapping.values()), "Associations must exclude RF and CCTV")
    for folder, kind, sid, minutes, offset in SENSORS:
        if folder not in folders:
            continue
        records = files[f"{folder}/{kind}.json"]
        legacy_folder = "synthetic_airbase_data" if folder == AIR else "synthetic_armybase_data"
        legacy = read(ROOT / "scenario_01_consistent" / legacy_folder / f"{kind}.json")
        require(all(set(r) == FIELDS[kind] for r in legacy), f"Scenario 1 {kind} schema mismatch")
        expected_times = [stamp(t) for t in schedule(minutes, offset)]
        counts = Counter(r["timestamp"] for r in records)
        expected_counts = COUNTS[folder] if kind == "eoir" else [5 if kind == "mpstar" else 1] * len(expected_times)
        require(counts == dict(zip(expected_times, expected_counts)), f"{sid}: missing/extra scheduled observations")
        site = SITES["AIRBASE_02" if folder == AIR else "ARMY_BASE_02"]
        key = "mpstar" if kind == "mpstar" else "airbase_eoir" if folder == AIR else "armybase_eoir"
        for r in records:
            require(set(r) == FIELDS[kind] and r["sensor_id"] == sid, f"{sid}: exact schema/source mismatch")
            require(not any(uid in json.dumps(r) for uid in IDS), f"{sid}: hidden ID leakage")
            require("confidence" not in r or 0 <= r["confidence"] <= 1, f"{sid}: invalid confidence")
            if kind in ("ew", "cctv"):
                require(r["detected"] is True, f"{sid}: non-detection is forbidden")
                if kind == "ew":
                    require(r["emitter_id"] == "RF-001", f"{sid}: invalid RF ID")
                    group = [truth[r["timestamp"], uid] for uid in IDS]
                    centroid = {f: sum(p[f] for p in group) / 5 for f in ("latitude", "longitude")}
                    require(r["bearing_deg"] == geometry(site, centroid)[0], f"{sid}: incorrect sector bearing")
                else:
                    require(r["camera_id"] in {"CAM-001", "CAM-002", "CAM-003"}, "Invalid camera")
                continue
            reverse = {m[key]: uid for uid, m in mapping.items()}
            require(r["track_id"] in reverse, f"{sid}: unknown track")
            bearing, distance, elevation = geometry(site, truth[r["timestamp"], reverse[r["track_id"]]])
            require(r["azimuth_deg"] == bearing, f"{sid}: wrong site-relative azimuth")
            require(r["range_km"] == distance if kind == "mpstar" else r["elevation_deg"] == elevation, f"{sid}: wrong geometry")
            require((r["classification"], r["subtype"]) in ({("UAS", "fixed-wing")} if kind == "mpstar" else {("UAS", "fixed-wing"), ("UNKNOWN", "unknown")}), f"{sid}: invalid classification")
        if kind in ("mpstar", "eoir"):
            for i, time in enumerate(expected_times):
                selected = range(5) if kind == "mpstar" else ORDERS[folder][:COUNTS[folder][i]]
                require({r["track_id"] for r in records if r["timestamp"] == time} == {mapping[IDS[j]][key] for j in selected}, f"{sid}: duplicate or wrong resolved tracks")
    air = files[f"{AIR}/eoir.json"]
    army = files[f"{ARMY}/eoir.json"] if ARMY in folders else []
    require(COUNTS[AIR][0] < 5 and COUNTS[ARMY][0] < 5 and COUNTS[AIR] != COUNTS[ARMY], "Missing count disagreement")
    unknown = [r for r in air + army if r["classification"] == "UNKNOWN"]
    require(len(unknown) == 1 and unknown[0] in air, "Expected one Airbase UNKNOWN event")
    u = unknown[0]
    following = next(r for r in air if r["track_id"] == u["track_id"] and r["timestamp"] > u["timestamp"])
    require(following["classification"] == "UAS" and following["subtype"] == "fixed-wing" and following["confidence"] > u["confidence"], "Same EO track must recover next scan")
    for records in (air, army):
        for track in {r["track_id"] for r in records}:
            values = [r["confidence"] for r in records if r["track_id"] == track]
            require(any(b < a for a, b in zip(values, values[1:])), "EO confidence must not be monotonic")
    for folder in folders:
        require(files[f"{folder}/all_sensor_events.json"] == combine([files[f"{f}/{k}.json"] for f, k, *_ in SENSORS if f == folder]), f"{folder}: combined stream differs or is unsorted")
    if AIR in folders and ARMY in folders:
        require(files["scenario_02_all_sensor_events.json"] == combine([files[f"{f}/{k}.json"] for f, k, *_ in SENSORS]), "Combined stream differs, is unsorted, or contains development data")
    # Also validate configs, expected behavior, and every persisted value against the deterministic model.
    require(files == build(positions, associations(), folders), "Dataset differs from the seeded Scenario 2 model (including configuration/evaluation metadata)")


def save_files(files):
    for name, data in files.items():
        path = OUTPUT / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def airbase_file_names():
    return ["scenario_config.json",
            "shared_ground_truth/ground_truth_positions.json",
            "shared_ground_truth/ground_truth_associations.json",
            "shared_ground_truth/scenario_02_expected_behavior.json",
            *[f"{AIR}/{name}.json" for name in
              ("mpstar", "eoir", "ew", "all_sensor_events", "scenario_config")]]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-only", action="store_true", help="Validate saved shared truth and Airbase files without writing")
    args = parser.parse_args()
    validate_scenario_01()
    if args.validate_only:
        files = {name: read(OUTPUT / name) for name in airbase_file_names()}
    else:
        files = build(trajectories(), associations(), folders=(AIR,))
    validate(files, folders=(AIR,))
    if not args.validate_only:
        save_files(files)
        validate({name: read(OUTPUT / name) for name in files}, folders=(AIR,))
    print("PASS: shared five-UAS truth and Airbase schemas, schedules, geometry, identities and disagreement.")
    print("PASS: all 13 original Scenario 1 files unchanged (SHA-256).")
    print("Run generate_armybase_02_scenario.py next to generate Army observations and the combined stream.")


if __name__ == "__main__":
    main()
