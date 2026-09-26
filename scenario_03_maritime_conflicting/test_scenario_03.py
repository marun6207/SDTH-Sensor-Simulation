"""Scenario 3 regression tests, including saved-data corruption and regeneration."""
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

import generate_navybase_03_scenario as scenario


class ScenarioThreeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.names = scenario.navy_file_names() + [
            f"{scenario.ARMY}/{kind}.json" for kind in ("eoir", "ew", "cctv", "all_sensor_events", "scenario_config")
        ] + ["scenario_03_all_sensor_events.json"]
        cls.files = {name: scenario.read(scenario.OUTPUT / name) for name in cls.names}

    def test_complete_saved_validation_and_json_inventory(self):
        scenario.validate(self.files)
        self.assertEqual({p.relative_to(scenario.OUTPUT).as_posix() for p in scenario.OUTPUT.rglob("*.json")}, set(self.names))
        self.assertEqual(len(self.names), 15)

    def test_three_shared_physical_trajectories(self):
        rows = self.files["shared_ground_truth/ground_truth_positions.json"]
        self.assertEqual(len(rows), 5403)
        self.assertEqual({p["usv_id"] for p in rows}, {"USV-01", "USV-02", "USV-03"})
        self.assertTrue(all(n == 3 for n in Counter(p["timestamp"] for p in rows).values()))
        for uid in scenario.IDS:
            path = [p for p in rows if p["usv_id"] == uid]
            self.assertEqual((path[0]["timestamp"], path[-1]["timestamp"]), ("15:00:00", "15:30:00"))
            self.assertTrue(all(p["classification"] == "USV" and p["subtype"] == "small-surface-craft" for p in path))
            self.assertGreater(path[-1]["latitude"], path[0]["latitude"])
            self.assertGreater(path[-1]["longitude"], path[0]["longitude"])

    def test_radar_and_eo_progression_persistence_and_geometry(self):
        truth = {(r["timestamp"], r["usv_id"]): r for r in self.files["shared_ground_truth/ground_truth_positions.json"]}
        mapping = self.files["shared_ground_truth/ground_truth_associations.json"]
        radar = self.files[f"{scenario.NAVY}/coastal_radar.json"]
        eo = self.files[f"{scenario.ARMY}/eoir.json"]
        radar_times = [f"15:{m:02d}:11" for m in range(0, 30, 3)]
        eo_times = [f"15:{m:02d}:01" for m in range(0, 30, 3)]
        self.assertEqual(Counter(r["timestamp"] for r in radar), dict.fromkeys(radar_times, 3))
        self.assertEqual(Counter(r["timestamp"] for r in eo), dict(zip(eo_times, [1, 1, 2, 2, 2, 3, 3, 3, 3, 3])))
        expected_types = ["UNKNOWN"] * 3 + ["SURFACE_CRAFT"] * 4 + ["USV"] * 3
        for time, classification in zip(radar_times, expected_types):
            scan = [r for r in radar if r["timestamp"] == time]
            self.assertEqual({r["track_id"] for r in scan}, {"NAVY-UNK-001", "NAVY-UNK-002", "NAVY-UNK-003"})
            self.assertEqual({r["classification"] for r in scan}, {classification})
        for key, rows in (("coastal_radar", radar), ("army_eoir", eo)):
            reverse = {m[key]: uid for uid, m in mapping.items()}
            for r in rows:
                p = truth[r["timestamp"], reverse[r["track_id"]]]
                if key == "coastal_radar":
                    self.assertEqual((r["lat"], r["lon"], r["velocity_knots"], r["altitude_m"]),
                                     (p["latitude"], p["longitude"], p["speed_knots"], 0))
                else:
                    self.assertEqual(r["azimuth_deg"], round(scenario.geometry(scenario.SITES["ARMY_BASE_03"], p)[0], 3))
                    self.assertEqual(r["elevation_deg"], 0)
        ambiguous = [r for r in eo if r["classification"] == "UNKNOWN"]
        self.assertEqual([(r["timestamp"], r["track_id"]) for r in ambiguous], [("15:12:01", "ARMY-EO-002")])
        self.assertTrue(all(r["classification"] == "USV" for r in eo if r["timestamp"] >= "15:18:01"))
        self.assertNotEqual([mapping[u]["coastal_radar"].split("-")[-1] for u in scenario.IDS],
                            [mapping[u]["army_eoir"].split("-")[-1] for u in scenario.IDS])

    def test_ais_is_one_cooperative_identity(self):
        mapping = self.files["shared_ground_truth/ground_truth_associations.json"]
        self.assertEqual([u for u, m in mapping.items() if "ais_mmsi" in m], ["USV-02"])
        ais = self.files[f"{scenario.NAVY}/ais.json"]
        self.assertEqual(len(ais), 6)
        self.assertEqual({r["mmsi"] for r in ais}, {990000003})
        self.assertEqual({r["vessel_name"] for r in ais}, {"SIMULATED COOPERATIVE CRAFT"})
        truth = {p["timestamp"]: p for p in self.files["shared_ground_truth/ground_truth_positions.json"] if p["usv_id"] == "USV-02"}
        for r in ais:
            self.assertEqual((r["lat"], r["lon"]), (truth[r["timestamp"]]["latitude"], truth[r["timestamp"]]["longitude"]))
            self.assertNotIn("detected", r)

    def test_ew_and_sar_are_group_evidence(self):
        ew = self.files[f"{scenario.ARMY}/ew.json"]
        self.assertEqual([r["detected"] for r in ew], [True, False, True, True, False, True])
        self.assertEqual(ew[0]["classification"], "ambiguous_rf_activity")
        positions = self.files["shared_ground_truth/ground_truth_positions.json"]
        for r in ew:
            self.assertFalse({"lat", "lon", "track_id"} & set(r))
            if r["detected"]:
                group = [p for p in positions if p["timestamp"] == r["timestamp"]]
                centroid = {field: sum(p[field] for p in group) / 3 for field in ("latitude", "longitude")}
                self.assertEqual(r["bearing_deg"], round(scenario.geometry(scenario.SITES["ARMY_BASE_03"], centroid)[0], 3))
            else:
                self.assertIsNone(r["bearing_deg"])
                self.assertIsNone(r["emitter_id"])
        mapping = json.dumps(self.files["shared_ground_truth/ground_truth_associations.json"])
        self.assertNotIn("RF-GROUP-03", mapping)
        self.assertNotIn("SAR-SIM-0301", mapping)
        sar = self.files[f"{scenario.NAVY}/glint_sar.json"]
        self.assertEqual(len(sar), 1)
        self.assertEqual(sar[0]["timestamp"], "15:14:17")
        self.assertNotIn("track_id", sar[0])

    def test_replay_raw_only_exact_sensors_and_inclusive_window(self):
        replay = self.files["scenario_03_all_sensor_events.json"]
        self.assertEqual(len(replay), 74)
        self.assertEqual(len(self.files[f"{scenario.ARMY}/all_sensor_events.json"]), 37)
        self.assertEqual(len(self.files[f"{scenario.NAVY}/all_sensor_events.json"]), 37)
        self.assertEqual({r["sensor_id"] for r in replay}, {"NAVY_COASTAL_RADAR_03", "MPA_OCEANS_X_AIS", "GLINT_SAR_PASS_SIM_03", "EOIR_ARMYBASE_03", "ARMYBASE_EW_03", "CCTV_ARMYBASE_03"})
        self.assertEqual([r["timestamp"] for r in replay], sorted(r["timestamp"] for r in replay))
        self.assertTrue(all("15:00:00" <= r["timestamp"] <= "15:30:00" for r in replay))
        for uid in scenario.IDS:
            self.assertNotIn(uid, json.dumps(replay))
        for r in replay:
            self.assertFalse({"usv_id", "development_only", "associations"} & set(r))

    def test_cctv_negative_observations_and_combined_inclusion(self):
        rows = self.files[f"{scenario.ARMY}/cctv.json"]
        times = ["15:00:05", "15:04:05", "15:08:05", "15:12:05",
                 "15:16:05", "15:20:05", "15:24:05", "15:28:05"]
        self.assertEqual(len(rows), 8)
        self.assertEqual([r["timestamp"] for r in rows], times)
        config = self.files[f"{scenario.ARMY}/scenario_config.json"]["sensor_schedules"]["CCTV_ARMYBASE_03"]
        self.assertEqual(times, [scenario.stamp(t) for t in scenario.schedule(config["interval_minutes"], config["second"])])
        reference = scenario.read(scenario.ROOT / "scenario_02_conflicting/synthetic_armybase_02_data/cctv.json")
        for r in rows:
            self.assertEqual(set(r), set(reference[0]))
            self.assertEqual(r["sensor_id"], "CCTV_ARMYBASE_03")
            self.assertIs(r["detected"], False)
            self.assertEqual(r["classification"], "no_relevant_visual_anomaly")
            self.assertEqual(r["confidence"], 0.0)
            self.assertNotIn("track_id", r)
            for uid in scenario.IDS:
                self.assertNotIn(uid, json.dumps(r))
        for name in (f"{scenario.ARMY}/all_sensor_events.json", "scenario_03_all_sensor_events.json"):
            stream = self.files[name]
            self.assertEqual([r for r in stream if r["sensor_id"] == "CCTV_ARMYBASE_03"], rows)
            self.assertEqual([r["timestamp"] for r in stream], sorted(r["timestamp"] for r in stream))
        for uid, mapping in self.files["shared_ground_truth/ground_truth_associations.json"].items():
            self.assertEqual(set(mapping), {"coastal_radar", "army_eoir", "ais_mmsi"} if uid == "USV-02" else {"coastal_radar", "army_eoir"})

    def test_existing_sensor_files_and_shared_truth_unchanged(self):
        # Byte fingerprints captured before adding CCTV; all existing raw feeds are protected.
        expected = {'shared_ground_truth/ground_truth_associations.json': 'e7d7e3408b7b22a1f6dedcd13cff57a4bb1a8d6d02e0f18e2323911232be6b8c', 'shared_ground_truth/ground_truth_positions.json': '4c31f008384eb3daddc8696469bcbb18b1c823a5ab290f21fdab94c5fb47dd44', 'synthetic_armybase_03_data/eoir.json': '2a471722e416cc02023f6f753a8740113915925e211f7575281b50fbfd32229b', 'synthetic_armybase_03_data/ew.json': 'c28334bec802f4f9d2d455722f050f1d4b5a28ad1f671040b914c79d0e56aa93', 'synthetic_navybase_03_data/ais.json': '1bc3e46736b5dbad20de8294b3ecae4c537b0eeaa6d051cee5e2c25cebd6a4e4', 'synthetic_navybase_03_data/all_sensor_events.json': 'b48b36e4c58663d9f4e0ecb3bf73a55b98efee8f5be01613bed3fc6bfd644a89', 'synthetic_navybase_03_data/coastal_radar.json': 'ba46d89342067930296818047373eac751087b4744e7a9159fced87c94410809', 'synthetic_navybase_03_data/glint_sar.json': 'ebbd0fbd7d7584283ba839ab99e5e31e4f671e28d96dbaf654d03dcbbb86ad6d', 'synthetic_navybase_03_data/scenario_config.json': '8a9c022d5c92d6c0842eb91b3133eb845314df0645466eed4efaae79e889b237'}
        for name, digest in expected.items():
            with self.subTest(file=name):
                self.assertEqual(hashlib.sha256((scenario.OUTPUT / name).read_bytes()).hexdigest(), digest)

    def test_validation_rejects_corruption(self):
        cases = [
            (f"{scenario.ARMY}/cctv.json", lambda r: r[0].update(detected=True)),
            (f"{scenario.ARMY}/cctv.json", lambda r: r[0].update(classification="USV")),
            (f"{scenario.ARMY}/cctv.json", lambda r: r[0].update(track_id="CCTV-001")),
            (f"{scenario.ARMY}/cctv.json", lambda r: r[0].update(image="USV-01.jpg")),
            (f"{scenario.ARMY}/cctv.json", lambda r: r.pop()),
            ("shared_ground_truth/ground_truth_positions.json", lambda r: r.pop()),
            ("shared_ground_truth/ground_truth_associations.json", lambda m: m["USV-01"].update(ais_mmsi=990000004)),
            (f"{scenario.NAVY}/coastal_radar.json", lambda r: r.pop(0)),
            (f"{scenario.NAVY}/coastal_radar.json", lambda r: r[0].update(classification="USV")),
            (f"{scenario.NAVY}/coastal_radar.json", lambda r: r[0].update(lat=1.4)),
            (f"{scenario.ARMY}/eoir.json", lambda r: r.pop()),
            (f"{scenario.ARMY}/eoir.json", lambda r: r[0].update(track_id="USV-01")),
            (f"{scenario.NAVY}/ais.json", lambda r: r[0].update(lon=103.9)),
            (f"{scenario.NAVY}/glint_sar.json", lambda r: r.append(r[0].copy())),
            (f"{scenario.ARMY}/ew.json", lambda r: r[0].update(emitter_id="USV-01")),
            (f"{scenario.NAVY}/coastal_radar.json", lambda r: r[-1].update(timestamp="15:30:11")),
            (f"{scenario.ARMY}/all_sensor_events.json", lambda r: r.pop()),
            ("scenario_03_all_sensor_events.json", lambda r: r.reverse()),
            ("scenario_03_all_sensor_events.json", lambda r: r[0].update(sensor_id="UNEXPECTED_SENSOR")),
        ]
        for index, (name, corrupt) in enumerate(cases):
            with self.subTest(index=index, file=name):
                files = copy.deepcopy(self.files)
                corrupt(files[name])
                with self.assertRaises(ValueError):
                    scenario.validate(files)

    def test_generators_repeat_deterministically_and_preserve_existing_scenarios(self):
        def hashes(paths, root):
            return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.is_file()}
        protected_paths = [p for name in ("scenario_01_consistent", "scenario_02_conflicting") for p in (scenario.ROOT / name).rglob("*")]
        protected = hashes(protected_paths, scenario.ROOT)
        expected = hashes(scenario.OUTPUT.rglob("*.json"), scenario.OUTPUT)
        for _ in range(2):
            for script in ("generate_navybase_03_scenario.py", "generate_armybase_03_scenario.py"):
                result = subprocess.run([sys.executable, "-B", str(scenario.OUTPUT / script)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(hashes(scenario.OUTPUT.rglob("*.json"), scenario.OUTPUT), expected)
        self.assertEqual(hashes(protected_paths, scenario.ROOT), protected)


if __name__ == "__main__":
    unittest.main()
