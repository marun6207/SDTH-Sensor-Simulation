"""Regression checks for saved Scenario 2 data and intentional disagreements."""
import copy
import hashlib
import json
import unittest

import generate_airbase_02_scenario as scenario


class ScenarioValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        names = scenario.airbase_file_names() + ["scenario_02_all_sensor_events.json"]
        for folder in (scenario.ARMY, scenario.NAVY):
            names.extend(f"{folder}/{kind}.json" for f, kind, *_ in scenario.SENSORS if f == folder)
            names.extend(f"{folder}/{kind}.json" for kind in ("scenario_config", "all_sensor_events"))
        cls.saved = {name: scenario.read(scenario.OUTPUT / name) for name in names}

    def test_saved_data_and_deterministic_generation(self):
        scenario.validate(self.saved)
        self.assertEqual(self.saved, scenario.build(scenario.trajectories(), scenario.associations()))

    def test_all_non_cctv_feeds_truth_and_configs_unchanged(self):
        # Frozen byte fingerprints from before the targeted CCTV adjustment.
        expected = {'synthetic_airbase_02_data': 'c17c3328ef71c2b4218db0630fa769459b16418dab62bdfd97df23526e8a52e2', 'synthetic_navybase_02_data': '68227856b97e23c3c480dd9e2f6ede5b810dd055b35ebf258c2d67964c48a8d6', 'synthetic_armybase_02_data/eoir.json': 'fd3a2bf99bed4a8e838413efdd089de208bd93ed4f2a6e823b7abf1e8143675b', 'synthetic_armybase_02_data/ew.json': 'bb87ec17841c082b0b1c12d3b9f4f3549c21df6c5306f3825f32ae4ca76dfae9', 'synthetic_armybase_02_data/scenario_config.json': 'aeaae76cdb39b8789623c7c187bbed595cb727141776ab69b4bebfa1f71cfd52', 'shared_ground_truth/ground_truth_positions.json': 'bc549a47b08003f0f82b1a4295241e7c395971d4485f1b0087fbed529e11e2f9', 'shared_ground_truth/ground_truth_associations.json': '891bf6aa6d5f8b67a2c9d5af6fe1e568ae837687af5b5cfd962b23ffa2d84604', 'scenario_config.json': 'fc907008572d9840a92557d579a6833bd8d915ff230bfedffa227ea054974239'}
        for group, digest in expected.items():
            with self.subTest(group=group):
                path = scenario.OUTPUT / group
                paths = [path] if path.is_file() else sorted(path.glob("*.json"))
                actual = {p.relative_to(scenario.OUTPUT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
                self.assertEqual(hashlib.sha256(json.dumps(actual, sort_keys=True).encode()).hexdigest(), digest)

    def test_cctv_only_final_scan_is_positive_group_evidence(self):
        rows = self.saved[f"{scenario.ARMY}/cctv.json"]
        times = ["14:30:05", "14:34:05", "14:38:05", "14:42:05",
                 "14:46:05", "14:50:05", "14:54:05", "14:58:05"]
        self.assertEqual([r["timestamp"] for r in rows], times)
        self.assertEqual([r["detected"] for r in rows], [False] * 7 + [True])
        self.assertEqual(times, [scenario.stamp(t) for t in scenario.schedule(4, 5)])
        for r in rows:
            self.assertEqual(set(r), scenario.FIELDS["cctv"])
            self.assertEqual(r["sensor_id"], "CCTV_ARMYBASE_02")
            self.assertNotIn("track_id", r)
            for uid in scenario.IDS:
                self.assertNotIn(uid, json.dumps(r))
        for r in rows[:-1]:
            self.assertEqual(r["classification"], "no_relevant_uas_detection")
            self.assertEqual(r["confidence"], 0.0)
        self.assertEqual(rows[-1]["classification"], "UAS")
        self.assertEqual(rows[-1]["confidence"], .873)
        for name in (f"{scenario.ARMY}/all_sensor_events.json", "scenario_02_all_sensor_events.json"):
            self.assertEqual([r for r in self.saved[name] if r["sensor_id"] == "CCTV_ARMYBASE_02"], rows)

    def test_coastal_transition_and_surface_preservation(self):
        rows = self.saved[f"{scenario.NAVY}/coastal_radar.json"]
        surface = [r for r in rows if r["track_id"].startswith("SURFACE-")]
        self.assertEqual(hashlib.sha256(json.dumps(surface, sort_keys=True).encode()).hexdigest(), "5f89d00e7a0048ff9d5ed9fea67c1f5a2dd1fe0008052b62a4e20f1708c40d74")
        counts = [sum(r["timestamp"] == scenario.stamp(t) and r["track_id"].startswith("NAVY-UNK-") for r in rows) for t in scenario.schedule(3, 11)]
        self.assertEqual(counts, [0, 0, 0, 0, 0, 5, 5, 5, 5, 5])
        self.assertEqual({p.name for p in (scenario.OUTPUT / scenario.NAVY).glob("*.json")},
                         {"ais.json", "coastal_radar.json", "glint_sar.json", "all_sensor_events.json", "scenario_config.json"})

    def test_validation_rejects_corruption(self):
        def corrupt_airborne(rows, **changes):
            next(r for r in rows if r["track_id"].startswith("NAVY-UNK-")).update(changes)

        cases = [
            ("early_cctv_detection", f"{scenario.ARMY}/cctv.json", lambda rows: rows[0].update(detected=True, classification="UAS")),
            ("missing_final_cctv", f"{scenario.ARMY}/cctv.json", lambda rows: rows[-1].update(detected=False)),
            ("cctv_hidden_id", f"{scenario.ARMY}/cctv.json", lambda rows: rows[-1].update(image="UAS-01.jpg")),
            ("cctv_individual_track", f"{scenario.ARMY}/cctv.json", lambda rows: rows[-1].update(track_id="CCTV-001")),
            ("premature_acquisition", f"{scenario.NAVY}/coastal_radar.json", lambda rows: corrupt_airborne(rows, timestamp="14:30:11")),
            ("coastal_classification", f"{scenario.NAVY}/coastal_radar.json", lambda rows: corrupt_airborne(rows, classification="UAS", subtype="shahed-type")),
            ("coastal_altitude", f"{scenario.NAVY}/coastal_radar.json", lambda rows: corrupt_airborne(rows, altitude_m=0)),
            ("coastal_position", f"{scenario.NAVY}/coastal_radar.json", lambda rows: corrupt_airborne(rows, lat=1.2)),
            ("physical_count", "shared_ground_truth/ground_truth_positions.json", lambda rows: rows.pop()),
            ("site", "scenario_config.json", lambda c: c["sites"]["NAVY_BASE_02"].update(latitude=2.0)),
            ("radar_persistence", f"{scenario.NAVY}/coastal_radar.json", lambda rows: rows.pop()),
            ("eo_count", f"{scenario.AIR}/eoir.json", lambda rows: rows.pop(0)),
            ("eo_specificity", f"{scenario.ARMY}/eoir.json", lambda rows: rows[0].update(subtype="shahed-type")),
            ("eo_recovery", f"{scenario.AIR}/eoir.json", lambda rows: next(r for r in rows if r["timestamp"] == "14:45:01" and r["track_id"] == "EO-003").update(classification="UNKNOWN", subtype="unknown")),
            ("ew_positive", f"{scenario.ARMY}/ew.json", lambda rows: rows[0].update(detected=True)),
            ("ew_bearing", f"{scenario.AIR}/ew.json", lambda rows: rows[0].update(bearing_deg=100.0)),
            ("timing", f"{scenario.NAVY}/coastal_radar.json", lambda rows: rows[0].update(timestamp="14:30:00")),
            ("geometry", f"{scenario.NAVY}/coastal_radar.json", lambda rows: rows[0].update(lat=0.0)),
            ("hidden_id", f"{scenario.AIR}/mpstar.json", lambda rows: rows[0].update(track_id="UAS-01")),
            ("ordering", "scenario_02_all_sensor_events.json", lambda rows: rows.reverse()),
            ("independent_ids", "shared_ground_truth/ground_truth_associations.json", lambda m: [m[u].update(navy_coastal="NAVY-UNK-" + m[u]["mpstar"].rsplit("-", 1)[-1]) for u in scenario.IDS]),
            ("ais_uas_schema", f"{scenario.NAVY}/ais.json", lambda rows: rows[0].update(classification="UAS")),
            ("ais_identity", f"{scenario.NAVY}/ais.json", lambda rows: rows[0].update(vessel_name="UAS-01")),
            ("coastal_air_target", f"{scenario.NAVY}/coastal_radar.json", lambda rows: rows[0].update(classification="UAS", altitude_m=700)),
            ("coastal_uas_mapping", f"{scenario.NAVY}/coastal_radar.json", lambda rows: rows[0].update(track_id="NAVY-UNK-001")),
            ("sar_track_schema", f"{scenario.NAVY}/glint_sar.json", lambda rows: rows[0].update(track_id="NAVY-UNK-001")),
            ("sar_pass", f"{scenario.NAVY}/glint_sar.json", lambda rows: rows.append(dict(rows[0], timestamp="14:46:17"))),
            ("navy_inclusion", f"{scenario.NAVY}/all_sensor_events.json", lambda rows: rows.pop()),
            ("navy_order", f"{scenario.NAVY}/all_sensor_events.json", lambda rows: rows.reverse()),
            ("combined_inclusion", "scenario_02_all_sensor_events.json", lambda rows: rows.pop()),
        ]
        for name, filename, corrupt in cases:
            with self.subTest(name=name):
                files = copy.deepcopy(self.saved)
                corrupt(files[filename])
                with self.assertRaises(ValueError):
                    scenario.validate(files)


if __name__ == "__main__":
    unittest.main()
