"""Regression coverage for four shared USVs across three fictional sites."""
from collections import Counter
import copy
import hashlib
import json
import subprocess
import sys
import unittest

import generate_navybase_03_scenario as s


class ScenarioThreeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.names = s.navy_file_names() + s.site_file_names(s.AIR) + s.site_file_names(s.ARMY) + ["scenario_03_all_sensor_events.json"]
        cls.files = {name: s.read(s.OUTPUT / name) for name in cls.names}
        cls.positions = cls.files["shared_ground_truth/ground_truth_positions.json"]
        cls.truth = {(p["timestamp"], p["usv_id"]): p for p in cls.positions}
        cls.mapping = cls.files["shared_ground_truth/ground_truth_associations.json"]

    def test_complete_validation_json_inventory_and_sites(self):
        s.validate(self.files)
        self.assertEqual(len(self.names), 20)
        self.assertEqual({p.relative_to(s.OUTPUT).as_posix() for p in s.OUTPUT.rglob("*.json")}, set(self.names))
        self.assertEqual(self.files["scenario_config.json"]["sites"], {
            "NAVY_BASE_03": {"latitude": 1.260, "longitude": 103.720},
            "ARMY_BASE_03": {"latitude": 1.265, "longitude": 103.800},
            "AIRBASE_03": {"latitude": 1.290, "longitude": 103.860}})
        for folder, site_id in s.SITE_IDS.items():
            config = self.files[f"{folder}/scenario_config.json"]
            self.assertEqual((config["latitude"], config["longitude"]), (s.SITES[site_id]["latitude"], s.SITES[site_id]["longitude"]))

    def test_four_northbound_separated_physical_paths(self):
        self.assertEqual(len(self.positions), 7204)
        self.assertEqual(len(self.truth), 7204)
        self.assertEqual({p["usv_id"] for p in self.positions}, {"USV-01", "USV-02", "USV-03", "USV-04"})
        self.assertEqual(set(Counter(p["timestamp"] for p in self.positions).values()), {4})
        for uid in s.IDS:
            path = [self.truth[s.stamp(t), uid] for t in range(1801)]
            self.assertEqual((path[0]["timestamp"], path[-1]["timestamp"]), ("15:00:00", "15:30:00"))
            self.assertTrue(all(path[0]["latitude"] < site["latitude"] for site in s.SITES.values()))
            self.assertTrue(all(b["latitude"] > a["latitude"] and s.geometry(a, b)[1] < .02 for a, b in zip(path, path[1:])))
            self.assertGreater(path[-1]["latitude"] - path[0]["latitude"], 10 * abs(path[-1]["longitude"] - path[0]["longitude"]))
            self.assertTrue(all(5 <= p["speed_knots"] <= 20 and p["classification"] == "USV" for p in path))
        for time in ("15:00:00", "15:15:00", "15:30:00"):
            for i, uid in enumerate(s.IDS):
                for other in s.IDS[i + 1:]:
                    self.assertGreater(s.geometry(self.truth[time, uid], self.truth[time, other])[1], .1)

    def test_exact_requested_hidden_mapping(self):
        expected = {
            "USV-01": {"coastal_radar": "NAVY-UNK-003", "army_eoir": "ARMY-EO-002", "airbase_mpstar": "RDR-003", "airbase_eoir": "EO-004"},
            "USV-02": {"coastal_radar": "NAVY-UNK-001", "army_eoir": "ARMY-EO-004", "ais_mmsi": 990000003, "airbase_mpstar": "RDR-001", "airbase_eoir": "EO-002"},
            "USV-03": {"coastal_radar": "NAVY-UNK-004", "army_eoir": "ARMY-EO-001", "airbase_mpstar": "RDR-004", "airbase_eoir": "EO-003"},
            "USV-04": {"coastal_radar": "NAVY-UNK-002", "army_eoir": "ARMY-EO-003", "airbase_mpstar": "RDR-002", "airbase_eoir": "EO-001"}}
        self.assertEqual(self.mapping, expected)
        for key in ("coastal_radar", "army_eoir", "airbase_mpstar", "airbase_eoir"):
            self.assertNotEqual([self.mapping[u][key].split("-")[-1] for u in s.IDS], ["001", "002", "003", "004"])

    def test_object_sensor_counts_classification_and_shared_geometry(self):
        for folder, kind, sid, minutes, offset in s.SENSORS:
            if kind not in ("coastal_radar", "mpstar", "eoir"):
                continue
            rows = self.files[f"{folder}/{kind}.json"]
            times = [s.stamp(t) for t in s.schedule(minutes, offset)]
            counts = ([1, 1, 2, 2, 2, 3, 3, 3, 4, 4] if folder == s.ARMY else [1, 1, 1, 2, 2, 2, 3, 3, 3, 4]) if kind == "eoir" else [4] * len(times)
            self.assertEqual(Counter(r["timestamp"] for r in rows), dict(zip(times, counts)))
            reverse = {m[s.track_key(folder, kind)]: uid for uid, m in self.mapping.items()}
            acquired = set()
            for time in times:
                scan = [r for r in rows if r["timestamp"] == time]
                ids = {r["track_id"] for r in scan}
                self.assertTrue(acquired <= ids)
                acquired = ids
            self.assertEqual(len(acquired), 4)
            for r in rows:
                p = self.truth[r["timestamp"], reverse[r["track_id"]]]
                if kind == "coastal_radar":
                    self.assertEqual((r["lat"], r["lon"], r["velocity_knots"], r["altitude_m"]), (p["latitude"], p["longitude"], p["speed_knots"], 0))
                else:
                    bearing, distance = s.geometry(s.SITES[s.SITE_IDS[folder]], p)
                    self.assertEqual(r["azimuth_deg"], round(bearing, 3))
                    self.assertEqual(r["range_km"], round(distance, 4)) if kind == "mpstar" else self.assertEqual(r["elevation_deg"], 0)
                if kind != "eoir":
                    expected = ("UNKNOWN", "unknown") if r["timestamp"] < "15:09:00" else ("SURFACE_CRAFT", "unknown") if r["timestamp"] < "15:21:00" else ("USV", "unmanned-suspected")
                    self.assertEqual((r["classification"], r["subtype"]), expected)
                elif r["timestamp"] >= "15:18:01":
                    self.assertEqual((r["classification"], r["subtype"]), ("USV", "small-surface-craft"))

    def test_only_one_cooperative_ais_identity(self):
        rows = self.files[f"{s.NAVY}/ais.json"]
        self.assertEqual(len(rows), 6)
        self.assertEqual([u for u, m in self.mapping.items() if "ais_mmsi" in m], ["USV-02"])
        for r in rows:
            p = self.truth[r["timestamp"], "USV-02"]
            self.assertEqual((r["mmsi"], r["vessel_name"]), (990000003, "SIMULATED COOPERATIVE CRAFT"))
            self.assertEqual((r["lat"], r["lon"], r["sog_knots"], r["cog_deg"]), (p["latitude"], p["longitude"], p["speed_knots"], p["course_deg"]))
            self.assertNotIn("detected", r)

    def test_cctv_unchanged_and_always_negative(self):
        rows = self.files[f"{s.ARMY}/cctv.json"]
        self.assertEqual([r["timestamp"] for r in rows], [f"15:{m:02d}:05" for m in range(0, 30, 4)])
        for r in rows:
            self.assertIs(r["detected"], False)
            self.assertEqual((r["classification"], r["confidence"]), ("no_relevant_visual_anomaly", 0.0))
            self.assertNotIn("track_id", r)
        self.assertEqual(hashlib.sha256((s.OUTPUT / s.ARMY / "cctv.json").read_bytes()).hexdigest(), "bde9db94ca1d65163e8d155b10a310babb534e085e0182da88f57cc984eeb933")

    def test_ew_and_sar_group_evidence(self):
        for folder, pattern in ((s.ARMY, [True, False, True, True, False, True]), (s.AIR, [False, True, True, False, True, True])):
            rows = self.files[f"{folder}/ew.json"]
            self.assertEqual([r["detected"] for r in rows], pattern)
            for r in rows:
                self.assertFalse({"track_id", "lat", "lon"} & set(r))
                if r["detected"]:
                    centroid = {f: sum(self.truth[r["timestamp"], u][f] for u in s.IDS) / 4 for f in ("latitude", "longitude")}
                    self.assertEqual(r["bearing_deg"], round(s.geometry(s.SITES[s.SITE_IDS[folder]], centroid)[0], 3))
                else:
                    self.assertIsNone(r["emitter_id"])
                    self.assertIsNone(r["bearing_deg"])
        rows = self.files[f"{s.NAVY}/glint_sar.json"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["timestamp"], "15:14:17")
        self.assertEqual(rows[0]["center_lat"], round(sum(self.truth["15:14:17", u]["latitude"] for u in s.IDS) / 4, 9))
        self.assertNotIn("RF-GROUP-03", json.dumps(self.mapping))
        self.assertNotIn("SAR-SIM-0301", json.dumps(self.mapping))

    def test_replay_raw_only_complete_sorted_and_within_window(self):
        replay = self.files["scenario_03_all_sensor_events.json"]
        self.assertEqual(len(replay), 178)
        for folder, count in ((s.AIR, 92), (s.ARMY, 39), (s.NAVY, 47)):
            stream = self.files[f"{folder}/all_sensor_events.json"]
            self.assertEqual(len(stream), count)
            self.assertEqual(stream, s.combine([self.files[f"{f}/{k}.json"] for f, k, *_ in s.SENSORS if f == folder]))
        self.assertEqual(replay, s.combine([self.files[f"{f}/{k}.json"] for f, k, *_ in s.SENSORS]))
        self.assertEqual({r["sensor_id"] for r in replay}, {sid for _, _, sid, _, _ in s.SENSORS})
        for folder, kind, *_ in s.SENSORS:
            for r in self.files[f"{folder}/{kind}.json"]:
                self.assertTrue("15:00:00" <= r["timestamp"] <= "15:30:00")
                self.assertEqual(set(r), s.FIELDS[kind])
                for uid in s.IDS:
                    self.assertNotIn(uid, json.dumps(r))
        for uid in s.IDS:
            self.assertNotIn(uid, json.dumps(replay))

    def test_rejects_corruptions(self):
        cases = [
            ("shared_ground_truth/ground_truth_positions.json", lambda r: r.pop()),
            ("shared_ground_truth/ground_truth_associations.json", lambda m: m["USV-01"].update(ew="RF-GROUP-03")),
            ("shared_ground_truth/ground_truth_associations.json", lambda m: m["USV-04"].update(ais_mmsi=990000004)),
            (f"{s.NAVY}/coastal_radar.json", lambda r: r.pop()),
            (f"{s.AIR}/mpstar.json", lambda r: r[0].update(range_km=0)),
            (f"{s.AIR}/mpstar.json", lambda r: r[0].update(classification="USV")),
            (f"{s.AIR}/eoir.json", lambda r: r.pop()),
            (f"{s.ARMY}/eoir.json", lambda r: r[0].update(track_id="USV-04")),
            (f"{s.ARMY}/cctv.json", lambda r: r[0].update(detected=True)),
            (f"{s.AIR}/ew.json", lambda r: r[0].update(emitter_id="USV-01")),
            (f"{s.NAVY}/glint_sar.json", lambda r: r.append(r[0].copy())),
            (f"{s.AIR}/mpstar.json", lambda r: r[-1].update(timestamp="15:30:01")),
            ("scenario_03_all_sensor_events.json", lambda r: r.reverse()),
            ("scenario_03_all_sensor_events.json", lambda r: r.pop()),
        ]
        for i, (name, corrupt) in enumerate(cases):
            with self.subTest(case=i):
                files = copy.deepcopy(self.files)
                corrupt(files[name])
                with self.assertRaises(ValueError):
                    s.validate(files)

    def test_repeatable_generators_preserve_scenarios_one_two(self):
        def hashes(root):
            return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}
        protected = {name: hashes(s.ROOT / name) for name in ("scenario_01_consistent", "scenario_02_conflicting")}
        expected = s.file_hashes(self.names)
        for _ in range(2):
            for script in ("generate_navybase_03_scenario.py", "generate_airbase_03_scenario.py", "generate_armybase_03_scenario.py"):
                result = subprocess.run([sys.executable, "-B", str(s.OUTPUT / script)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(s.file_hashes(self.names), expected)
        for name, digest in protected.items():
            self.assertEqual(hashes(s.ROOT / name), digest)


if __name__ == "__main__":
    unittest.main()
