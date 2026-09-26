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
    "AIRBASE_02": {"latitude": 1.345000, "longitude": 103.965000},
    "ARMY_BASE_02": {"latitude": 1.415000, "longitude": 104.045000},
    "NAVY_BASE_02": {"latitude": 1.255000, "longitude": 103.835000},
}
AIR = "synthetic_airbase_02_data"
ARMY = "synthetic_armybase_02_data"
NAVY = "synthetic_navybase_02_data"
SITE_IDS = {AIR: "AIRBASE_02", ARMY: "ARMY_BASE_02", NAVY: "NAVY_BASE_02"}
TRACKS = [("mpstar", "RDR"), ("airbase_eoir", "EO"),
          ("armybase_eoir", "ARMY-EO"), ("navy_coastal", "NAVY-UNK")]
COASTAL_ACQUISITION_RANGE_KM = 31.0
EO_IDENTIFICATION_RANGE_KM = 18.0  # Fictional identification rule, not sensor performance.
# site, filename, sensor ID, interval in minutes, second offset
SENSORS = [
    (AIR, "mpstar", "MPSTAR_AIRBASE_02", 2, 0),
    (AIR, "eoir", "EOIR_AIRBASE_02", 3, 1),
    (AIR, "ew", "AIRBASE_EW_02", 5, 2),
    (ARMY, "eoir", "EOIR_ARMYBASE_02", 3, 1),
    (ARMY, "cctv", "CCTV_ARMYBASE_02", 4, 5),
    (ARMY, "ew", "ARMYBASE_EW_02", 5, 2),
    (NAVY, "ais", "MPA_OCEANS_X_AIS", 5, 7),
    (NAVY, "coastal_radar", "NAVY_COASTAL_RADAR_02", 3, 11),
    (NAVY, "glint_sar", "GLINT_SAR_PASS_SIM_02", None, 857),
]
FIELDS = {
    "mpstar": set("sensor_id timestamp track_id azimuth_deg range_km classification subtype".split()),
    "eoir": set("sensor_id timestamp track_id azimuth_deg elevation_deg classification subtype confidence image".split()),
    "ew": set("sensor_id timestamp emitter_id detected bearing_deg classification confidence".split()),
    "cctv": set("sensor_id timestamp camera_id detected classification confidence image".split()),
}
FIELDS["ais"] = set("sensor_id timestamp mmsi vessel_name lat lon sog_knots cog_deg".split())
FIELDS["coastal_radar"] = set("sensor_id timestamp track_id lat lon velocity_knots altitude_m rcs_m2 classification subtype".split())
FIELDS["glint_sar"] = set("sensor_id timestamp candidate_id center_lat center_lon length_m width_m anomaly anomaly_length_m".split())
MARITIME_KINDS = {"ais", "coastal_radar", "glint_sar"}
# Fictional offline identities; no connection to live vessels or the UAS mapping.
VESSELS = [
    {"mmsi": 990000001, "name": "SIMULATED SOUTHERN TRADER", "track": "SURFACE-207",
     "lat": 1.210, "lon": 103.810, "speed": 8.0, "course": 75.0, "subtype": "cargo", "rcs": 180.0},
    {"mmsi": 990000002, "name": "SIMULATED SOUTHERN TUG", "track": "SURFACE-412",
     "lat": 1.200, "lon": 103.870, "speed": 6.0, "course": 285.0, "subtype": "tug", "rcs": 45.0},
]
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
    if minutes is None:  # A single SAR pass, not a continuously updating radar.
        return [second]
    return list(range(second, 1801, minutes * 60))


def sensor_schedule(minutes, second):
    return {"observation_times": [stamp(second)], "mode": "single_pass"} if minutes is None else {"interval_minutes": minutes, "second": second}


def maritime_records(kind, sensor_id, minutes, offset):
    """Independent surface traffic; deliberately has no UAS truth/mapping inputs."""
    records = []
    rng = random.Random(SEED + 200)
    # Seeded, constant offsets keep the same vessel path coherent across modalities.
    offsets = [(rng.uniform(-.0001, .0001), rng.uniform(-.0001, .0001)) for _ in VESSELS]
    for second in schedule(minutes, offset):
        for index, vessel in enumerate(VESSELS):
            if kind == "glint_sar" and index != 0:
                continue
            distance = vessel["speed"] * 1.852 * second / 3600
            course = math.radians(vessel["course"])
            lat = round(vessel["lat"] + offsets[index][0] + math.degrees(distance * math.cos(course) / RADIUS), 6)
            lon = round(vessel["lon"] + offsets[index][1] + math.degrees(distance * math.sin(course) / (RADIUS * math.cos(math.radians(vessel["lat"])))), 6)
            event = {"sensor_id": sensor_id, "timestamp": stamp(second)}
            if kind == "ais":
                event.update(mmsi=vessel["mmsi"], vessel_name=vessel["name"], lat=lat, lon=lon,
                             sog_knots=vessel["speed"], cog_deg=vessel["course"])
            elif kind == "coastal_radar":
                event.update(track_id=vessel["track"], lat=lat, lon=lon, velocity_knots=vessel["speed"],
                             altitude_m=0.0, rcs_m2=vessel["rcs"], classification="VESSEL", subtype=vessel["subtype"])
            else:
                event.update(candidate_id="SAR-SIM-0201", center_lat=lat, center_lon=lon,
                             length_m=72.0, width_m=13.0, anomaly="SYNTHETIC_DECK_STRUCTURE", anomaly_length_m=8.0)
            records.append(event)
    return records


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
        parameters.append((24 + i * .55 + rng.uniform(-.15, .15),
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
                "latitude": round(1.340 + math.degrees(north / RADIUS), 9),
                "longitude": round(103.990 + math.degrees(east / (RADIUS * math.cos(math.radians(1.340)))), 9),
                "altitude_m": round(altitude + 35 * math.sin(2 * math.pi * f + phase), 3),
                "classification": "UAS", "subtype": "shahed-type"})
    return positions


def associations():
    rng = random.Random(SEED + 1)
    result = {uid: {} for uid in IDS}
    for key, prefix in TRACKS:
        numbers = list(range(1, 6))
        rng.shuffle(numbers)
        for uid, number in zip(IDS, numbers):
            result[uid][key] = f"{prefix}-{number:03d}"
    return result


def confidence(rng, scan, distance, modality):
    base = {"eoir": .61, "ew": .66, "cctv": .70}[modality]
    # Alternating small quality changes ensure confidence is not perfectly monotonic.
    quality = .035 if scan % 2 == 0 else -.035
    return round(max(.1, min(.97, base + .01 * scan + .22 * (1 - min(distance / 34, 1))
                             + quality + rng.uniform(-.012, .012))), 3)


def combine(streams):
    return sorted([r for stream in streams for r in stream], key=lambda r: (r["timestamp"], r["sensor_id"], r.get("track_id", "")))


# Fingerprint of the revised deterministic physical scenario. Validation can verify
# the exact trajectories without regenerating them in the Army process.
TRAJECTORY_SHA256 = "9c79ebedcc39dbb31c06e9423efe157dcbac305e12671b4f041657c903749665"


def track_key(folder, kind):
    return "navy_coastal" if folder == NAVY else "mpstar" if kind == "mpstar" else "airbase_eoir" if folder == AIR else "armybase_eoir"


def coastal_contacts(truth, mapping, sensor_id, minutes, offset):
    """Range-gated observations of existing physical objects, with no type knowledge."""
    records = []
    for second in schedule(minutes, offset):
        for uid in IDS:
            position = truth[stamp(second), uid]
            if geometry(SITES["NAVY_BASE_02"], position)[1] > COASTAL_ACQUISITION_RANGE_KM:
                continue
            previous = truth[stamp(second - 1), uid]
            speed = round(geometry(previous, position)[1] * 3600 / 1.852, 3)
            records.append({"sensor_id": sensor_id, "timestamp": stamp(second),
                "track_id": mapping[uid]["navy_coastal"], "lat": position["latitude"],
                "lon": position["longitude"], "velocity_knots": speed,
                "altitude_m": position["altitude_m"], "rcs_m2": .035,
                "classification": "UNKNOWN", "subtype": "unknown"})
    return records


def build(positions, mapping, folders=(AIR, ARMY, NAVY)):
    """Derive requested site outputs from supplied truth; never create trajectories."""
    truth = {(p["timestamp"], p["uas_id"]): p for p in positions}
    files = {"shared_ground_truth/ground_truth_positions.json": positions,
             "shared_ground_truth/ground_truth_associations.json": mapping}
    for sensor_index, (folder, kind, sensor_id, minutes, offset) in enumerate(SENSORS):
        if folder not in folders:
            continue
        if kind in MARITIME_KINDS:
            records = maritime_records(kind, sensor_id, minutes, offset)
            if kind == "coastal_radar":
                records = combine([records, coastal_contacts(truth, mapping, sensor_id, minutes, offset)])
            files[f"{folder}/{kind}.json"] = records
            continue
        site = SITES[SITE_IDS[folder]]
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
                    event.update(detected=False, emitter_id=None, bearing_deg=None,
                                 classification="no_relevant_rf_detection", confidence=0.0)
                else:
                    camera = f"CAM-{scan % 3 + 1:03d}"
                    event.update(camera_id=camera, image=f"{camera.replace('-', '')}_{time.replace(':', '')}.jpg")
                records.append(event)
                continue
            selected = range(5) if kind == "mpstar" else ORDERS[folder][:COUNTS[folder][scan]]
            key = track_key(folder, kind)
            for i in selected:
                track = mapping[IDS[i]][key]
                bearing, distance, elevation = geometry(site, group[i])
                event = {"sensor_id": sensor_id, "timestamp": time, "track_id": track,
                         "azimuth_deg": bearing, "classification": "UAS", "subtype": "fixed-wing"}
                if kind == "mpstar":
                    event["range_km"] = distance
                    event["subtype"] = "shahed-type"
                else:
                    if distance <= EO_IDENTIFICATION_RANGE_KM:
                        event["subtype"] = "shahed-type"
                    event.update(elevation_deg=elevation, confidence=confidence(rng, scan, distance, kind),
                                 image=f"{track.replace('-', '')}_{time.replace(':', '')}.jpg")
                    if folder == AIR and scan == 4 and i == 2:
                        event.update(classification="UNKNOWN", subtype="unknown", confidence=.38)
                records.append(event)
        files[f"{folder}/{kind}.json"] = records
    config = {"scenario_id": "SCENARIO_02", "scenario_name": "Southeast UAS Approach with Multi-Sensor Disagreement",
              "start_time": "14:30:00", "end_time": "15:00:00", "hidden_physical_uas_count": 5,
              "general_approach_direction": "southeast to northwest", "fixed_random_seed": SEED,
              "simulation_notice": "Fictional sites, not real installations. Simulated Shahed-type identification and RF silence are scenario assumptions, not real-world performance claims.",
              "eoir_identification_range_km": EO_IDENTIFICATION_RANGE_KM,
              "ew_policy": "No relevant detectable RF signature; detected=false, emitter_id/bearing_deg=null, confidence=0 (no positive detection confidence).",
              "sites": SITES, "coordinate_system": "WGS84", "site_altitude_m": 0,
              "timing_policy": "Strict inclusive end at 15:00:00; later second-offset updates are outside the window.",
              "geometry_model": "Spherical Earth radius 6371.0088 km; surface radar range; local flat elevation from altitude.",
              "trajectory_model": "Linear east/north approach with smooth sinusoidal lateral and altitude variation; one-second truth samples.",
              "resolution_model": "Scripted acquisition by viewpoint: Airbase object order 1,3,5,2,4; Army 2,4,1,5,3. Unresolved objects still exist.",
              "sensor_schedules": {sid: sensor_schedule(m, s) for _, _, sid, m, s in SENSORS}}
    files["scenario_config.json"] = config
    for folder, site_id in SITE_IDS.items():
        if folder not in folders:
            continue
        files[f"{folder}/scenario_config.json"] = {"scenario_id": "SCENARIO_02", "site_id": site_id,
            **SITES[site_id], "start_time": config["start_time"], "end_time": config["end_time"],
            "sensor_schedules": {sid: config["sensor_schedules"][sid] for f, _, sid, _, _ in SENSORS if f == folder}}
        if folder == NAVY:
            files[f"{folder}/scenario_config.json"]["modality_policy"] = {
                "ais": "Two fictional cooperative vessels; synthetic offline MMSIs 990000001/990000002; never UAS.",
                "coastal_radar": "Two persistent surface vessels plus range-gated UNKNOWN airborne contacts from the shared trajectories.",
                "glint_sar": "One asynchronous maritime SAR/anomaly candidate at 14:44:17; not an aerial track.",
            }
            files[f"{folder}/scenario_config.json"]["coastal_acquisition"] = {
                "surface_range_km": COASTAL_ACQUISITION_RANGE_KM,
                "rule": "Each contact detected at scheduled scans when surface range from NAVY_BASE_02 <= threshold; UNKNOWN/unknown throughout.",
                "measurement_model": "Exact shared positions and altitude; speed from preceding one-second displacement; synthetic RCS 0.035 m2.",
            }
        files[f"{folder}/all_sensor_events.json"] = combine([files[f"{f}/{k}.json"] for f, k, *_ in SENSORS if f == folder])
    if all(folder in folders for folder in SITE_IDS):
        files["scenario_02_all_sensor_events.json"] = combine([files[f"{f}/{k}.json"] for f, k, *_ in SENSORS])
    if AIR not in folders:
        return files
    unknown = next(r for r in files[f"{AIR}/eoir.json"] if r["classification"] == "UNKNOWN")
    files["shared_ground_truth/scenario_02_expected_behavior.json"] = {
        "development_only": True, "hidden_physical_uas_count": 5, "true_simulated_subtype": "shahed-type",
        "expected_mpstar_count_per_scan": 5,
        "navy_coastal_acquisition_range_km": COASTAL_ACQUISITION_RANGE_KM,
        "navy_coastal_airborne_counts": [{"timestamp": stamp(t), "count": sum(geometry(SITES["NAVY_BASE_02"], truth[stamp(t), uid])[1] <= COASTAL_ACQUISITION_RANGE_KM for uid in IDS)} for t in schedule(3, 11)],
        "classification_progression": {"radar": "UAS / shahed-type from first scan",
            "eoir": "UAS / fixed-wing until site-relative range <= 18 km, then UAS / shahed-type, except the temporary UNKNOWN event"},
        "eoir_counts": [{"timestamp": stamp(t), "airbase": COUNTS[AIR][i], "armybase": COUNTS[ARMY][i]}
                        for i, t in enumerate(schedule(3, 1))],
        "classification_uncertainty": {"sensor_id": unknown["sensor_id"], "track_id": unknown["track_id"],
            "timestamp": unknown["timestamp"], "classification": "UNKNOWN", "subtype": "unknown", "confidence": .38,
            "restored_timestamp": "14:45:01", "restored_classification": "UAS", "restored_subtype": "fixed-wing"},
        "ew_support": "Every scheduled update detected=false; no relevant RF signature is detectable in this simulation. Absence of RF does not invalidate radar/EO evidence.",
        "navy_support": "Coastal radar initially sees only vessels, then acquires five UNKNOWN airborne contacts at 14:45:11 within 31 km using the same shared truth. Missing early tracks mean not yet detected, not nonexistent. AIS/SAR remain maritime.",
        "cctv_support": "Every scheduled update detected=true; three rotating cameras provide event-level evidence, not object counts.",
        "early": "Airbase radar resolves five shahed-type UAS; EO resolves 2/3 fixed-wing subsets; EW does not corroborate.",
        "middle": "EO counts and confidence generally increase, with site-dependent subtype convergence and one UNKNOWN; Airbase radar maintains five; EW remains negative.",
        "late": "Both EO sensors resolve five shahed-type UAS by 14:51:01; confidence still varies, EW remains negative.",
        "early_snapshot": {"window": "14:30:00 through 14:30:05", "mpstar": 5, "airbase_eoir": 2,
                           "armybase_eoir": 3, "navy_coastal_airborne": 0, "airbase_ew_detected": False, "armybase_ew_detected": False, "cctv_detected": True}}
    return files


def validate_scenario_01():
    folder = ROOT / "scenario_01_consistent"
    manifest = read(folder / "original_sha256.json")
    actual_paths = {p.relative_to(folder).as_posix() for name in ("synthetic_airbase_data", "synthetic_armybase_data") for p in (folder / name).rglob("*") if p.is_file()}
    require(actual_paths == set(manifest), "Scenario 1 file inventory changed")
    for name, digest in manifest.items():
        require(hashlib.sha256((folder / name).read_bytes()).hexdigest() == digest,
                f"Scenario 1 bytes changed: {name}")


def validate_maritime(kind, sensor_id, minutes, offset, records, mapping):
    reference = read(ROOT / "synthetic_maritime_data" / f"{kind}.json")
    require(reference and all(set(r) == FIELDS[kind] for r in reference), f"{kind}: maritime reference schema mismatch")
    expected_times = [stamp(t) for t in schedule(minutes, offset)]
    count = 1 if kind == "glint_sar" else len(VESSELS)
    require(Counter(r["timestamp"] for r in records) == dict.fromkeys(expected_times, count), f"{kind}: missing/extra maritime observations")
    uas_tracks = {track for m in mapping.values() for track in m.values()}
    for r in records:
        require(set(r) == FIELDS[kind] and r["sensor_id"] == sensor_id, f"{kind}: exact maritime schema/source mismatch")
        require(not any(uid in json.dumps(r) for uid in IDS), f"{kind}: hidden UAS ID leakage")
        require(not any(str(value) in uas_tracks for value in r.values()), f"{kind}: UAS track used for maritime observation")
        lat, lon = (r["center_lat"], r["center_lon"]) if kind == "glint_sar" else (r["lat"], r["lon"])
        require(1.18 <= lat <= 1.24 and 103.79 <= lon <= 103.89, f"{kind}: outside southern maritime area")
        if kind == "ais":
            require(r["mmsi"] in {v["mmsi"] for v in VESSELS}, "AIS: invalid synthetic MMSI")
            require(r["vessel_name"].startswith("SIMULATED ") and 0 < r["sog_knots"] <= 15 and 0 <= r["cog_deg"] < 360, "AIS: invalid vessel identity/motion")
        elif kind == "coastal_radar":
            require(r["classification"] == "VESSEL" and r["subtype"] in {"cargo", "tug"}
                    and r["altitude_m"] == 0 and 0 < r["velocity_knots"] <= 15 and r["rcs_m2"] > 0,
                    "Coastal radar must contain surface vessels only")
            require(r["track_id"] in {v["track"] for v in VESSELS}, "Invalid independent surface track")
        else:
            require(r["candidate_id"] == "SAR-SIM-0201" and r["anomaly"] == "SYNTHETIC_DECK_STRUCTURE"
                    and 0 < r["anomaly_length_m"] < r["length_m"] and r["width_m"] > 0,
                    "GLINT must remain a maritime SAR/anomaly candidate")
    require(records == maritime_records(kind, sensor_id, minutes, offset), f"{kind}: maritime data differs from seeded model")


def validate_coastal(records, truth, mapping, sensor_id, minutes, offset):
    reverse = {m["navy_coastal"]: uid for uid, m in mapping.items()}
    surface_ids = {v["track"] for v in VESSELS}
    airborne = [r for r in records if r["track_id"] not in surface_ids]
    require(airborne, "Missing late coastal acquisitions")
    acquired = set()
    for second in schedule(minutes, offset):
        time = stamp(second)
        scan = [r for r in airborne if r["timestamp"] == time]
        expected = {mapping[uid]["navy_coastal"] for uid in IDS
                    if geometry(SITES["NAVY_BASE_02"], truth[time, uid])[1] <= COASTAL_ACQUISITION_RANGE_KM}
        observed = {r["track_id"] for r in scan}
        require(len(scan) == len(expected) and observed == expected, "Incorrect range-gated coastal acquisition")
        require(acquired <= observed, "Acquired coastal contact lost persistence")
        acquired = observed
    require(len(acquired) == 5 and not any(r["timestamp"] == stamp(offset) for r in airborne), "Expected early absence and five late coastal contacts")
    for r in airborne:
        require(set(r) == FIELDS["coastal_radar"] and r["sensor_id"] == sensor_id, "Wrong airborne coastal schema/source")
        require(r["track_id"] in reverse and not any(uid in json.dumps(r) for uid in IDS), "Hidden or invalid coastal identity")
        position = truth[r["timestamp"], reverse[r["track_id"]]]
        require((r["lat"], r["lon"], r["altitude_m"]) == (position["latitude"], position["longitude"], position["altitude_m"]), "Coastal contact differs from shared trajectory")
        require(r["altitude_m"] > 0 and r["velocity_knots"] > 0 and r["rcs_m2"] == .035, "Invalid airborne coastal measurements")
        require((r["classification"], r["subtype"]) == ("UNKNOWN", "unknown"), "Coastal radar must not identify airborne type")
    require(records == combine([maritime_records("coastal_radar", sensor_id, minutes, offset),
                                coastal_contacts(truth, mapping, sensor_id, minutes, offset)]), "Coastal stream differs from model or is unsorted")


def validate(files, folders=(AIR, ARMY, NAVY)):
    validate_scenario_01()
    config = files["scenario_config.json"]
    require(config["sites"] == SITES, "Incorrect synthetic site coordinates")
    regions = {"AIRBASE_02": (1.32, 1.37, 103.94, 103.99),
               "ARMY_BASE_02": (1.40, 1.43, 104.03, 104.07),
               "NAVY_BASE_02": (1.24, 1.28, 103.81, 103.86)}
    for site_id, (south, north, west, east) in regions.items():
        site = config["sites"][site_id]
        require(south <= site["latitude"] <= north and west <= site["longitude"] <= east,
                f"{site_id}: outside fictional site region")
    require(len({offset for _, _, _, _, offset in SENSORS}) >= 4, "Missing asynchronous offsets")
    positions = files["shared_ground_truth/ground_truth_positions.json"]
    require(hashlib.sha256(json.dumps(positions, sort_keys=True).encode()).hexdigest() == TRAJECTORY_SHA256,
            "Shared trajectories differ from the revised seeded Scenario 2")
    truth = {(p["timestamp"], p["uas_id"]): p for p in positions}
    require(len(positions) == len(truth) == 1801 * 5 and {p["uas_id"] for p in positions} == set(IDS), "Expected exactly five complete physical trajectories")
    require(all(p["classification"] == "UAS" and p["subtype"] == "shahed-type" for p in positions), "Incorrect simulated physical type")
    for uid in IDS:
        path = [truth[stamp(t), uid] for t in range(1801)]
        for site in SITES.values():
            require(path[0]["latitude"] < site["latitude"] and path[0]["longitude"] > site["longitude"], f"{uid} must start southeast")
            require(geometry(site, path[-1])[1] < geometry(site, path[0])[1], f"{uid} must approach defended sites")
        require(all(b["latitude"] > a["latitude"] and b["longitude"] < a["longitude"] and geometry(a, b)[1] < .05 for a, b in zip(path, path[1:])), f"{uid} trajectory discontinuity or wrong direction")
    mapping = files["shared_ground_truth/ground_truth_associations.json"]
    require(set(mapping) == set(IDS), "Association object inventory mismatch")
    for key, prefix in TRACKS:
        require({mapping[u][key] for u in IDS} == {f"{prefix}-{i:03d}" for i in range(1, 6)}, f"Invalid {key} ID mapping")
        require(any(mapping[u][key] != f"{prefix}-{i:03d}" for i, u in enumerate(IDS, 1)), f"Unshuffled {key} IDs")
    require(all(set(m) == {key for key, _ in TRACKS} for m in mapping.values()), "Associations must exclude RF and CCTV")
    permutations = [tuple(mapping[u][key].rsplit("-", 1)[-1] for u in IDS) for key, _ in TRACKS]
    require(len(set(permutations)) == len(TRACKS), "Sensor track numbers must use independent permutations")
    require(len({track for m in mapping.values() for track in m.values()}) == 20, "Sensor-local IDs must be distinct")
    for folder, kind, sid, minutes, offset in SENSORS:
        if folder not in folders:
            continue
        records = files[f"{folder}/{kind}.json"]
        if kind in MARITIME_KINDS:
            if kind == "coastal_radar":
                validate_coastal(records, truth, mapping, sid, minutes, offset)
                surface = [r for r in records if r["track_id"] in {v["track"] for v in VESSELS}]
                validate_maritime(kind, sid, minutes, offset, surface, mapping)
            else:
                validate_maritime(kind, sid, minutes, offset, records, mapping)
            continue
        if folder != NAVY:
            legacy_folder = "synthetic_airbase_data" if folder == AIR else "synthetic_armybase_data"
            legacy = read(ROOT / "scenario_01_consistent" / legacy_folder / f"{kind}.json")
            require(all(set(r) == FIELDS[kind] for r in legacy), f"Scenario 1 {kind} schema mismatch")
        expected_times = [stamp(t) for t in schedule(minutes, offset)]
        counts = Counter(r["timestamp"] for r in records)
        expected_counts = COUNTS[folder] if kind == "eoir" else [5 if kind == "mpstar" else 1] * len(expected_times)
        require(counts == dict(zip(expected_times, expected_counts)), f"{sid}: missing/extra scheduled observations")
        site = SITES[SITE_IDS[folder]]
        key = track_key(folder, kind)
        for r in records:
            require(set(r) == FIELDS[kind] and r["sensor_id"] == sid, f"{sid}: exact schema/source mismatch")
            require(not any(uid in json.dumps(r) for uid in IDS), f"{sid}: hidden ID leakage")
            require("confidence" not in r or 0 <= r["confidence"] <= 1, f"{sid}: invalid confidence")
            if kind in ("ew", "cctv"):
                if kind == "ew":
                    require(r["detected"] is False and r["emitter_id"] is None and r["bearing_deg"] is None
                            and r["classification"] == "no_relevant_rf_detection" and r["confidence"] == 0,
                            f"{sid}: EW must not corroborate or invent an emitter/bearing")
                else:
                    require(r["detected"] is True and r["classification"] == "UAS", f"{sid}: missing CCTV support")
                    require(r["camera_id"] in {"CAM-001", "CAM-002", "CAM-003"}, "Invalid camera")
                continue
            reverse = {m[key]: uid for uid, m in mapping.items()}
            require(r["track_id"] in reverse, f"{sid}: unknown track")
            bearing, distance, elevation = geometry(site, truth[r["timestamp"], reverse[r["track_id"]]])
            require(r["azimuth_deg"] == bearing, f"{sid}: wrong site-relative azimuth")
            radar = kind == "mpstar"
            if radar:
                require(r["range_km"] == distance, f"{sid}: wrong radar range")
            if kind == "eoir":
                require(r["elevation_deg"] == elevation, f"{sid}: wrong elevation")
            subtype = "shahed-type" if radar or distance <= EO_IDENTIFICATION_RANGE_KM else "fixed-wing"
            uncertain = folder == AIR and kind == "eoir" and r["timestamp"] == "14:42:01" and reverse[r["track_id"]] == IDS[2]
            require((r["classification"], r["subtype"]) == (("UNKNOWN", "unknown") if uncertain else ("UAS", subtype)),
                    f"{sid}: wrong classification progression")
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
        if records:
            require(all(r["subtype"] == "fixed-wing" for r in records if r["timestamp"] == "14:30:01"), "EO must initially be less specific")
            require(all(r["subtype"] == "shahed-type" for r in records if r["timestamp"] >= "14:51:01"), "Late EO must converge")
        for track in {r["track_id"] for r in records}:
            values = [r["confidence"] for r in records if r["track_id"] == track]
            require(any(b < a for a, b in zip(values, values[1:])), "EO confidence must not be monotonic")
            require(values[-1] > values[0], "EO confidence must improve overall")
    for folder in folders:
        require(files[f"{folder}/all_sensor_events.json"] == combine([files[f"{f}/{k}.json"] for f, k, *_ in SENSORS if f == folder]), f"{folder}: combined stream differs or is unsorted")
        allowed = {sid for f, _, sid, _, _ in SENSORS if f == folder}
        require({r["sensor_id"] for r in files[f"{folder}/all_sensor_events.json"]} == allowed, "Unexpected sensor in site stream")
    if all(folder in folders for folder in SITE_IDS):
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
