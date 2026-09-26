"""Generate fictional Scenario 3 shared truth/Navy feeds; common validation helpers."""
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
SEED = 20260926
RADIUS = 6371.0088
IDS = ["USV-01", "USV-02", "USV-03", "USV-04"]
NAVY = "synthetic_navybase_03_data"
ARMY = "synthetic_armybase_03_data"
AIR = "synthetic_airbase_03_data"
SITES = {"ARMY_BASE_03": {"latitude": 1.265, "longitude": 103.800},
         "AIRBASE_03": {"latitude": 1.290, "longitude": 103.860},
         "NAVY_BASE_03": {"latitude": 1.260, "longitude": 103.720}}
SITE_IDS = {NAVY: "NAVY_BASE_03", ARMY: "ARMY_BASE_03", AIR: "AIRBASE_03"}
# folder, modality, sensor ID, minutes (None = one pass), seconds from 15:00
SENSORS = [(NAVY, "coastal_radar", "NAVY_COASTAL_RADAR_03", 3, 11),
           (NAVY, "ais", "MPA_OCEANS_X_AIS", 5, 7),
           (NAVY, "glint_sar", "GLINT_SAR_PASS_SIM_03", None, 857),
           (ARMY, "eoir", "EOIR_ARMYBASE_03", 3, 1),
           (ARMY, "ew", "ARMYBASE_EW_03", 5, 2),
           (ARMY, "cctv", "CCTV_ARMYBASE_03", 4, 5),
           (AIR, "mpstar", "MPSTAR_AIRBASE_03", 2, 0),
           (AIR, "eoir", "EOIR_AIRBASE_03", 3, 1),
           (AIR, "ew", "AIRBASE_EW_03", 5, 2)]
FIELDS = {
    "mpstar": set("sensor_id timestamp track_id azimuth_deg range_km classification subtype".split()),
    "coastal_radar": set("sensor_id timestamp track_id lat lon velocity_knots altitude_m rcs_m2 classification subtype".split()),
    "ais": set("sensor_id timestamp mmsi vessel_name lat lon sog_knots cog_deg".split()),
    "glint_sar": set("sensor_id timestamp candidate_id center_lat center_lon length_m width_m anomaly anomaly_length_m".split()),
    "eoir": set("sensor_id timestamp track_id azimuth_deg elevation_deg classification subtype confidence image".split()),
    "ew": set("sensor_id timestamp emitter_id detected bearing_deg classification confidence".split()),
    "cctv": set("sensor_id timestamp camera_id detected classification confidence image".split()),
}
EO_COUNTS = {ARMY: [1, 1, 2, 2, 2, 3, 3, 3, 4, 4], AIR: [1, 1, 1, 2, 2, 2, 3, 3, 3, 4]}
EO_ORDER = {ARMY: ["USV-03", "USV-01", "USV-04", "USV-02"], AIR: ["USV-04", "USV-02", "USV-01", "USV-03"]}
MMSI = 990000003  # Fictional offline identifier, not a live vessel identity.
EW_DETECTED = {ARMY: [True, False, True, True, False, True], AIR: [False, True, True, False, True, True]}
EW_CONFIDENCE = {ARMY: [.32, 0.0, .64, .71, 0.0, .78], AIR: [0.0, .42, .58, 0.0, .68, .74]}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def stamp(second):
    return f"15:{second // 60:02d}:{second % 60:02d}"


def schedule(minutes, offset):
    return [offset] if minutes is None else list(range(offset, 1801, minutes * 60))


def geometry(site, position):
    """Synthetic spherical surface range and bearing; no performance assumptions."""
    a, b = map(math.radians, (site["latitude"], position["latitude"]))
    d = math.radians(position["longitude"] - site["longitude"])
    h = math.sin((b - a) / 2) ** 2 + math.cos(a) * math.cos(b) * math.sin(d / 2) ** 2
    distance = 2 * RADIUS * math.asin(math.sqrt(min(1, h)))
    bearing = math.degrees(math.atan2(math.sin(d) * math.cos(b),
        math.cos(a) * math.sin(b) - math.sin(a) * math.cos(b) * math.cos(d))) % 360
    return bearing, distance


def trajectories():
    rng = random.Random(SEED)
    paths = []
    for i in range(len(IDS)):
        lat0 = 1.080 + .001 * i + rng.uniform(-.0002, .0002)
        lon0 = 103.770 + .0018 * i + rng.uniform(-.0002, .0002)
        bend = rng.uniform(-.0004, .0004)
        path = []
        for second in range(1801):
            f = second / 1800
            path.append({"latitude": round(lat0 + .140 * f + bend * math.sin(math.pi * f), 9),
                         "longitude": round(lon0 + .002 * f - bend * math.sin(math.pi * f), 9)})
        paths.append(path)
    records = []
    for second in range(1801):
        for uid, path in zip(IDS, paths):
            previous, following = (path[second], path[second + 1]) if second < 1800 else (path[second - 1], path[second])
            course, distance = geometry(previous, following)
            records.append({"timestamp": stamp(second), "usv_id": uid, **path[second],
                "speed_knots": round(distance * 3600 / 1.852, 3), "course_deg": round(course, 3),
                "classification": "USV", "subtype": "small-surface-craft"})
    return records


def associations():
    return {"USV-01": {"coastal_radar": "NAVY-UNK-003", "army_eoir": "ARMY-EO-002", "airbase_mpstar": "RDR-003", "airbase_eoir": "EO-004"},
            "USV-02": {"coastal_radar": "NAVY-UNK-001", "army_eoir": "ARMY-EO-004", "ais_mmsi": MMSI, "airbase_mpstar": "RDR-001", "airbase_eoir": "EO-002"},
            "USV-03": {"coastal_radar": "NAVY-UNK-004", "army_eoir": "ARMY-EO-001", "airbase_mpstar": "RDR-004", "airbase_eoir": "EO-003"},
            "USV-04": {"coastal_radar": "NAVY-UNK-002", "army_eoir": "ARMY-EO-003", "airbase_mpstar": "RDR-002", "airbase_eoir": "EO-001"}}


def track_key(folder, kind):
    return "coastal_radar" if kind == "coastal_radar" else "airbase_mpstar" if kind == "mpstar" else "army_eoir" if folder == ARMY else "airbase_eoir"


def radar_type(second):
    return ("UNKNOWN", "unknown") if second < 540 else ("SURFACE_CRAFT", "unknown") if second < 1260 else ("USV", "unmanned-suspected")


def eo_type(scan, uid, folder):
    if folder == ARMY and scan == 4 and uid == "USV-01":
        return "UNKNOWN", "unknown"
    return ("SURFACE_CRAFT", "unknown") if scan < 6 else ("USV", "small-surface-craft")


def combine(streams):
    return sorted((r for stream in streams for r in stream),
                  key=lambda r: (r["timestamp"], r["sensor_id"], str(r.get("track_id", r.get("mmsi", r.get("candidate_id", ""))))))


def build(positions, mapping, folders=(NAVY, ARMY, AIR)):
    """Derive observations exclusively from supplied shared physical positions."""
    truth = {(p["timestamp"], p["usv_id"]): p for p in positions}
    config = {"scenario_id": "SCENARIO_03", "scenario_name": "Maritime Multi-Sensor Disagreement",
        "start_time": "15:00:00", "end_time": "15:30:00", "fixed_random_seed": SEED,
        "hidden_physical_usv_count": 4, "sites": SITES, "coordinate_system": "WGS84",
        "general_approach_direction": "south to north",
        "simulation_notice": "All coordinates, identities, classifications and behaviors are fictional simulation data; not real military installations or sensor/USV performance.",
        "timing_policy": "Full timestamp <= 15:30:00; second-offset 15:30 updates excluded.",
        "measurement_model": "Exact synthetic surface positions, zero surface altitude/elevation; spherical bearing; seeded EO confidence variation.",
        "eoir_counts": EO_COUNTS,
        "radar_classification": "UNKNOWN before 15:09; SURFACE_CRAFT from 15:09 until 15:21; USV/unmanned-suspected from 15:21, applied at each radar scan.",
        "eoir_classification": "SURFACE_CRAFT initially; one temporary UNKNOWN at 15:12:01; USV/small-surface-craft from 15:18:01.",
        "ais_policy": "Only one simulated cooperative craft reports AIS; other objects send no AIS messages, not negative detections.",
        "ew_policy": "Intermittent group-sector RF evidence; no individual object/emitter association. Synthetic assumption, not a real communications claim.",
        "cctv_policy": "Operational throughout; no relevant visual anomaly detected at any scan. Synthetic assumption, not evidence of physical object absence or real CCTV performance.",
        "sensor_schedules": {sid: {"observation_times": [stamp(offset)], "mode": "single_pass"} if minutes is None
            else {"interval_minutes": minutes, "second": offset} for _, _, sid, minutes, offset in SENSORS}}
    files = {"scenario_config.json": config, "shared_ground_truth/ground_truth_positions.json": positions,
             "shared_ground_truth/ground_truth_associations.json": mapping,
             "shared_ground_truth/scenario_03_expected_behavior.json": {
                 "development_only": True, "hidden_physical_usv_count": 4,
                 "coastal_counts": [{"timestamp": stamp(t), "count": 4, "classification": radar_type(t)[0]} for i, t in enumerate(schedule(3, 11))],
                 "mpstar_counts": [{"timestamp": stamp(t), "count": 4, "classification": radar_type(t)[0]} for t in schedule(2, 0)],
                 "eoir_counts": {SITE_IDS[f]: [{"timestamp": stamp(t), "count": EO_COUNTS[f][i]} for i, t in enumerate(schedule(3, 1))] for f in (ARMY, AIR)},
                 "ais_reporting_object": "USV-02", "ais_reporting_object_count": 1,
                 "temporary_uncertainty": {"timestamp": "15:12:01", "track_id": mapping["USV-01"]["army_eoir"], "recovery": "15:15:01"},
                 "ew_detection_sequence": EW_DETECTED, "ew_association": "Group sector only; no unique object association.",
                 "cctv_detection_sequence": [False] * len(schedule(4, 5)),
                 "cctv_association": "None; no relevant visual evidence or individual USV tracks throughout.",
                 "sar_timestamp": "15:14:17", "sar_association": "Four-contact area centroid; not four identified objects.",
                 "early": "Four UNKNOWN tracks per radar, one generic contact per EO sensor, one cooperative AIS identity.",
                 "middle": "Radar becomes SURFACE_CRAFT; EO progresses toward four, with temporary uncertainty; intermittent RF and one SAR candidate.",
                 "late": "Radar/EO converge on four USVs with different specificity; AIS still one reporting identity; group evidence cannot uniquely associate objects."}}
    for folder, kind, sid, minutes, offset in SENSORS:
        if folder not in folders:
            continue
        rng = random.Random(SEED + 1)
        records = []
        for scan, second in enumerate(schedule(minutes, offset)):
            time = stamp(second)
            group = [truth[time, uid] for uid in IDS]
            centroid = {field: sum(p[field] for p in group) / len(IDS) for field in ("latitude", "longitude")}
            if kind == "coastal_radar":
                for uid, p in zip(IDS, group):
                    classification, subtype = radar_type(second)
                    records.append({"sensor_id": sid, "timestamp": time, "track_id": mapping[uid]["coastal_radar"],
                        "lat": p["latitude"], "lon": p["longitude"], "velocity_knots": p["speed_knots"],
                        "altitude_m": 0.0, "rcs_m2": .8, "classification": classification, "subtype": subtype})
            elif kind == "ais":
                p = truth[time, "USV-02"]
                records.append({"sensor_id": sid, "timestamp": time, "mmsi": MMSI,
                    "vessel_name": "SIMULATED COOPERATIVE CRAFT", "lat": p["latitude"], "lon": p["longitude"],
                    "sog_knots": p["speed_knots"], "cog_deg": p["course_deg"]})
            elif kind == "glint_sar":
                records.append({"sensor_id": sid, "timestamp": time, "candidate_id": "SAR-SIM-0301",
                    "center_lat": round(centroid["latitude"], 9), "center_lon": round(centroid["longitude"], 9),
                    "length_m": 900.0, "width_m": 500.0, "anomaly": "SYNTHETIC_MARITIME_RETURN_CLUSTER", "anomaly_length_m": 700.0})
            elif kind == "mpstar":
                for uid, p in zip(IDS, group):
                    bearing, distance = geometry(SITES["AIRBASE_03"], p)
                    classification, subtype = radar_type(second)
                    records.append({"sensor_id": sid, "timestamp": time, "track_id": mapping[uid]["airbase_mpstar"],
                        "azimuth_deg": round(bearing, 3), "range_km": round(distance, 4),
                        "classification": classification, "subtype": subtype})
            elif kind == "eoir":
                for uid in EO_ORDER[folder][:EO_COUNTS[folder][scan]]:
                    p = truth[time, uid]
                    bearing, distance = geometry(SITES[SITE_IDS[folder]], p)
                    classification, subtype = eo_type(scan, uid, folder)
                    confidence = round(min(.97, .48 + .025 * scan + .13 * (1 - min(distance / 25, 1))
                        + (.025 if scan % 2 == 0 else -.025) + rng.uniform(-.008, .008)), 3)
                    if classification == "UNKNOWN":
                        confidence = .36
                    track = mapping[uid][track_key(folder, kind)]
                    records.append({"sensor_id": sid, "timestamp": time, "track_id": track,
                        "azimuth_deg": round(bearing, 3), "elevation_deg": 0.0,
                        "classification": classification, "subtype": subtype, "confidence": confidence,
                        "image": f"{track.replace('-', '')}_{time.replace(':', '')}.jpg"})
            elif kind == "cctv":
                camera = f"CAM-{scan % 3 + 1:03d}"
                records.append({"sensor_id": sid, "timestamp": time, "camera_id": camera,
                    "detected": False, "classification": "no_relevant_visual_anomaly", "confidence": 0.0,
                    "image": f"{camera.replace('-', '')}_{time.replace(':', '')}.jpg"})
            else:
                detected = EW_DETECTED[folder][scan]
                records.append({"sensor_id": sid, "timestamp": time, "emitter_id": "RF-GROUP-03" if detected else None,
                    "detected": detected, "bearing_deg": round(geometry(SITES[SITE_IDS[folder]], centroid)[0], 3) if detected else None,
                    "classification": ("ambiguous_rf_activity" if scan == 0 else "suspected_surface_link") if detected else "no_relevant_rf_detection",
                    "confidence": EW_CONFIDENCE[folder][scan]})
        files[f"{folder}/{kind}.json"] = records
    for folder in folders:
        site_id = SITE_IDS[folder]
        files[f"{folder}/scenario_config.json"] = {"scenario_id": "SCENARIO_03", "site_id": site_id, **SITES[site_id],
            "start_time": config["start_time"], "end_time": config["end_time"], "simulation_notice": config["simulation_notice"],
            "sensor_schedules": {sid: config["sensor_schedules"][sid] for f, _, sid, _, _ in SENSORS if f == folder}}
        files[f"{folder}/all_sensor_events.json"] = combine([files[f"{f}/{kind}.json"] for f, kind, *_ in SENSORS if f == folder])
    if set(folders) == set(SITE_IDS):
        files["scenario_03_all_sensor_events.json"] = combine([files[f"{folder}/all_sensor_events.json"] for folder in folders])
    return files


def validate(files, folders=(NAVY, ARMY, AIR)):
    require(files["scenario_config.json"]["sites"] == SITES and len(SITES) == 3, "Exactly the three configured sites required")
    require(SITES["NAVY_BASE_03"] == {"latitude": 1.260, "longitude": 103.720}, "Navy location must remain unchanged")
    positions = files["shared_ground_truth/ground_truth_positions.json"]
    truth = {(p["timestamp"], p["usv_id"]): p for p in positions}
    require(len(positions) == len(truth) == 1801 * 4 and {p["usv_id"] for p in positions} == set(IDS), "Exactly four complete physical USVs required")
    for uid in IDS:
        path = [truth[stamp(t), uid] for t in range(1801)]
        for site in SITES.values():
            require(path[0]["latitude"] < site["latitude"], "Must start south")
            require(geometry(site, path[-1])[1] < geometry(site, path[0])[1], "Must approach the sites")
        require(all(b["latitude"] > a["latitude"] and b["longitude"] > a["longitude"] and geometry(a, b)[1] < .02 for a, b in zip(path, path[1:])), "Discontinuous or wrong-direction trajectory")
        require(path[-1]["latitude"] - path[0]["latitude"] > 10 * abs(path[-1]["longitude"] - path[0]["longitude"]), "Motion must be predominantly northward")
    for second in range(1801):
        for i, uid in enumerate(IDS):
            for other in IDS[i + 1:]:
                require(.1 < geometry(truth[stamp(second), uid], truth[stamp(second), other])[1] < 1.0, "Craft separation invalid")
    require(all(5 <= p["speed_knots"] <= 20 and p["classification"] == "USV" and p["subtype"] == "small-surface-craft" for p in positions), "Invalid physical type/speed")
    require(positions == trajectories(), "Physical trajectories differ from the fixed seed")
    mapping = files["shared_ground_truth/ground_truth_associations.json"]
    require(mapping == associations(), "Incorrect hidden associations; EW/SAR must not map to individual USVs")
    require([uid for uid, m in mapping.items() if "ais_mmsi" in m] == ["USV-02"], "Only USV-02 reports AIS")
    for folder, kind, sid, minutes, offset in SENSORS:
        if folder not in folders:
            continue
        records = files[f"{folder}/{kind}.json"]
        reference = ROOT / (f"scenario_02_conflicting/synthetic_armybase_02_data/{kind}.json" if folder == ARMY else f"scenario_02_conflicting/synthetic_airbase_02_data/{kind}.json" if folder == AIR else f"synthetic_maritime_data/{kind}.json")
        require(all(set(r) == FIELDS[kind] for r in read(reference)), "Reference schema changed")
        times = [stamp(t) for t in schedule(minutes, offset)]
        counts = EO_COUNTS[folder] if kind == "eoir" else [4 if kind in ("coastal_radar", "mpstar") else 1] * len(times)
        require(Counter(r["timestamp"] for r in records) == dict(zip(times, counts)), f"{sid}: incorrect schedule/counts")
        for r in records:
            require(set(r) == FIELDS[kind] and r["sensor_id"] == sid, f"{sid}: exact schema/source mismatch")
            require("15:00:00" <= r["timestamp"] <= "15:30:00", "Timestamp outside scenario")
            require(not any(uid in json.dumps(r) for uid in IDS), "Hidden physical ID leaked")
            require("confidence" not in r or 0 <= r["confidence"] <= 1, "Invalid confidence")
            scan = times.index(r["timestamp"])
            if kind in ("coastal_radar", "mpstar", "eoir"):
                key = track_key(folder, kind)
                reverse = {m[key]: uid for uid, m in mapping.items()}
                require(r["track_id"] in reverse, "Invalid sensor-local track")
                uid = reverse[r["track_id"]]
                p = truth[r["timestamp"], uid]
                expected_type = radar_type(schedule(minutes, offset)[scan]) if kind in ("coastal_radar", "mpstar") else eo_type(scan, uid, folder)
                require((r["classification"], r["subtype"]) == expected_type, "Incorrect classification progression")
                if kind == "coastal_radar":
                    require((r["lat"], r["lon"], r["velocity_knots"], r["altitude_m"]) == (p["latitude"], p["longitude"], p["speed_knots"], 0), "Radar differs from shared surface truth")
                elif kind == "mpstar":
                    bearing, distance = geometry(SITES["AIRBASE_03"], p)
                    require(r["azimuth_deg"] == round(bearing, 3) and r["range_km"] == round(distance, 4), "MPSTAR differs from shared surface truth")
                else:
                    require(r["azimuth_deg"] == round(geometry(SITES[SITE_IDS[folder]], p)[0], 3) and r["elevation_deg"] == 0, "EO geometry differs from shared surface truth")
            elif kind == "ais":
                p = truth[r["timestamp"], "USV-02"]
                require(r["mmsi"] == MMSI and (r["lat"], r["lon"], r["sog_knots"], r["cog_deg"]) == (p["latitude"], p["longitude"], p["speed_knots"], p["course_deg"]), "AIS must report only cooperative physical object")
            elif kind == "ew":
                require(r["detected"] is EW_DETECTED[folder][scan], "Incorrect intermittent EW evidence")
                require(r["emitter_id"] == ("RF-GROUP-03" if r["detected"] else None), "EW must remain group-level")
            elif kind == "cctv":
                require(r["detected"] is False and r["classification"] == "no_relevant_visual_anomaly"
                        and r["confidence"] == 0.0, "CCTV must never provide relevant detection")
                require(r["camera_id"] == f"CAM-{scan % 3 + 1:03d}", "Incorrect CCTV camera sequence")
            else:
                centroid = {field: round(sum(truth[r["timestamp"], uid][field] for uid in IDS) / len(IDS), 9) for field in ("latitude", "longitude")}
                require((r["center_lat"], r["center_lon"]) == (centroid["latitude"], centroid["longitude"]), "SAR must describe the shared contact area")
        if kind in ("coastal_radar", "mpstar", "eoir"):
            key = track_key(folder, kind)
            for i, time in enumerate(times):
                selected = IDS if kind in ("coastal_radar", "mpstar") else EO_ORDER[folder][:EO_COUNTS[folder][i]]
                require({r["track_id"] for r in records if r["timestamp"] == time} == {mapping[uid][key] for uid in selected}, "Track subset/persistence mismatch")
        if kind == "eoir":
            for track in {r["track_id"] for r in records}:
                values = [r["confidence"] for r in records if r["track_id"] == track]
                if len(values) >= 3:
                    require(values[-1] > values[0] and any(b < a for a, b in zip(values, values[1:])), "Established EO confidence must improve with variation")
    for folder in folders:
        require(files[f"{folder}/all_sensor_events.json"] == combine([files[f"{f}/{kind}.json"] for f, kind, *_ in SENSORS if f == folder]), "Incomplete/unsorted site replay")
    if set(folders) == set(SITE_IDS):
        replay = files["scenario_03_all_sensor_events.json"]
        require(replay == combine([files[f"{f}/{kind}.json"] for f, kind, *_ in SENSORS]), "Incomplete/unsorted full replay")
        require({r["sensor_id"] for r in replay} == {sid for _, _, sid, _, _ in SENSORS}, "Unexpected sensor in replay")
    require(files == build(positions, mapping, folders), "Saved data/config/evaluation differs from deterministic model")


def save_files(files):
    for name, data in files.items():
        path = OUTPUT / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def navy_file_names():
    return ["scenario_config.json", "shared_ground_truth/ground_truth_positions.json",
            "shared_ground_truth/ground_truth_associations.json", "shared_ground_truth/scenario_03_expected_behavior.json",
            *[f"{NAVY}/{name}.json" for name in ("coastal_radar", "ais", "glint_sar", "all_sensor_events", "scenario_config")]]


def site_file_names(folder):
    return [f"{folder}/{kind}.json" for f, kind, *_ in SENSORS if f == folder] + [f"{folder}/all_sensor_events.json", f"{folder}/scenario_config.json"]


def file_hashes(names):
    return {name: hashlib.sha256((OUTPUT / name).read_bytes()).hexdigest() for name in names}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-only", action="store_true", help="Validate saved Navy/shared data without writing")
    args = parser.parse_args()
    files = {name: read(OUTPUT / name) for name in navy_file_names()} if args.validate_only else build(trajectories(), associations(), (NAVY,))
    validate(files, (NAVY,))
    if not args.validate_only:
        save_files(files)
        validate({name: read(OUTPUT / name) for name in files}, (NAVY,))
    print("PASS: shared four-USV truth, Navy schemas, schedules, geometry and classification.")
    print("Run generate_airbase_03_scenario.py next, then generate_armybase_03_scenario.py for complete replay.")


if __name__ == "__main__":
    main()
