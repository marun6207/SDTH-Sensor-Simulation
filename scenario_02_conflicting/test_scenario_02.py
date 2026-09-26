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

    def test_existing_sites_positions_ais_and_sar_unchanged(self):
        # Frozen byte fingerprints from before the coastal acquisition change.
        expected = {'synthetic_airbase_02_data': 'c17c3328ef71c2b4218db0630fa769459b16418dab62bdfd97df23526e8a52e2', 'synthetic_armybase_02_data': 'cf321ec69e0b191c71199793b4935c51b3921e5e2606c40a02c82e6eb7de5e25', 'shared_ground_truth/ground_truth_positions.json': 'bc549a47b08003f0f82b1a4295241e7c395971d4485f1b0087fbed529e11e2f9', 'synthetic_navybase_02_data/ais.json': 'be34316b5441b2c5a1d5fcea55f97ed75fbe99a8ff7ac0d6602dcaaf4266700a', 'synthetic_navybase_02_data/glint_sar.json': '8bcd7f643bc40f4ba047a78f33cdd839bf4a12480966bc82f2d810dcdd2f9734'}
        for group, digest in expected.items():
            with self.subTest(group=group):
                path = scenario.OUTPUT / group
                paths = [path] if path.is_file() else sorted(path.glob("*.json"))
                actual = {p.relative_to(scenario.OUTPUT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
                self.assertEqual(hashlib.sha256(json.dumps(actual, sort_keys=True).encode()).hexdigest(), digest)

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
