# Scenario 3 - Maritime Multi-Sensor Disagreement

`SCENARIO_03` runs from **15:00:00 through 15:30:00 inclusive**. Exactly three
physical USVs approach from the southwest along smooth northeast/east trajectories.
Navy and Army observe the same objects, with disagreement in resolved counts,
cooperative identity, classification, confidence, timing and local track IDs.
There is no Airbase in this scenario.

All coordinates, identities and behavior are synthetic simulation data. The sites
do not represent actual military installations, and the scenario makes no claims
about real sensor performance or USV communications.

## Fictional sites and schedules

| Site | Latitude | Longitude | Sensors |
| --- | --- | --- | --- |
| ARMY_BASE_03, western Singapore region | 1.350 | 103.700 | EO/IR, EW |
| NAVY_BASE_03, southwestern Singapore region | 1.260 | 103.720 | Coastal radar, AIS, GLINT SAR |

| Sensor | Schedule | Records |
| --- | --- | --- |
| NAVY_COASTAL_RADAR_03 | Every 3 minutes, starting 15:00:11 | 30 |
| MPA_OCEANS_X_AIS | Every 5 minutes, starting 15:00:07 | 6 |
| EOIR_ARMYBASE_03 | Every 3 minutes, starting 15:00:01 | 23 |
| ARMYBASE_EW_03 | Every 5 minutes, starting 15:00:02 | 6 |
| GLINT_SAR_PASS_SIM_03 | One pass at 15:14:17 | 1 |

Full timestamps must be <= 15:30:00. Thus the final radar/EO scans occur at
15:27:11 / 15:27:01; no 15:30 second-offset observations are generated.

## Disagreement and convergence

- **Coastal radar** maintains three persistent `NAVY-UNK-*` surface tracks from
  its first scan, always at zero altitude. Classification progresses from
  `UNKNOWN / unknown` (15:00:11-15:06:11), through `SURFACE_CRAFT / unknown`
  (15:09:11-15:18:11), to `USV / unmanned-suspected` (15:21:11 onward).
- **Army EO/IR** resolves `1, 1, 2, 2, 2, 3, 3, 3, 3, 3` contacts on successive
  three-minute scans. Its independently shuffled `ARMY-EO-*` IDs persist.
  Initial `SURFACE_CRAFT / unknown` classifications become
  `USV / small-surface-craft` from 15:18:01. One track becomes `UNKNOWN` at
  15:12:01 and recovers at 15:15:01. Seeded confidence improves overall with dips.
- **AIS** reports only one cooperative identity, `SIMULATED COOPERATIVE CRAFT`
  with synthetic offline MMSI `990000003`. Only hidden object `USV-02` transmits
  in this simulation; the other two send no AIS messages. AIS is cooperative
  reporting, not a radar missing two targets, and produces no negative detections.
- **EW** supplies intermittent sector evidence: weak ambiguous activity at
  15:00:02, no relevant detection at 15:05:02, relevant activity at 15:10:02 and
  15:15:02, no detection at 15:20:02, and relevant activity at 15:25:02.
  `RF-GROUP-03` is group-level evidence, never a one-to-one USV association.
  Positive bearings point toward the group centroid; negative records have null
  emitter/bearing and zero confidence. EW provides no exact object coordinates.
- **GLINT SAR** supplies one maritime return-cluster anomaly at the contact-area
  centroid, not three identified objects. Its dimensions describe a synthetic
  anomaly area rather than an individual hull.

Late radar and EO agree on three contacts with differing classification specificity.
AIS still reports one identity; RF and SAR remain supplementary group evidence.
Nexus must infer cross-sensor associations rather than match track-number suffixes.

## Files and Nexus replay

**Replay `scenario_03_all_sensor_events.json` in Nexus.** It contains only raw
observations, sorted by timestamp with deterministic sensor/identity tie-breaking:
**66 records total**, comprising **29 Army** and **37 Navy** records.

```text
scenario_03_maritime_conflicting/
  README.md
  generate_navybase_03_scenario.py
  generate_armybase_03_scenario.py
  test_scenario_03.py
  scenario_config.json
  scenario_03_all_sensor_events.json
  shared_ground_truth/
    ground_truth_positions.json
    ground_truth_associations.json
    scenario_03_expected_behavior.json
  synthetic_armybase_03_data/
    eoir.json
    ew.json
    all_sensor_events.json
    scenario_config.json
  synthetic_navybase_03_data/
    coastal_radar.json
    ais.json
    glint_sar.json
    all_sensor_events.json
    scenario_config.json
```

The shared truth contains `USV-01` through `USV-03`, one-second positions, surface
speed/course and the true `USV / small-surface-craft` type. Associations and expected
behavior are development/evaluation files, excluded from raw replay. Neither
hidden IDs nor those associations appear in any raw feed. Maritime observations
retain their schema-defined coordinates. EO/IR and EW use Scenario 2 Army field
names; maritime feeds use the repository's existing maritime schemas.

## Generate and validate

From the repository root:

```text
cd scenario_03_maritime_conflicting
python -B generate_navybase_03_scenario.py
python -B generate_armybase_03_scenario.py
python -B generate_navybase_03_scenario.py --validate-only
python -B generate_armybase_03_scenario.py --validate-only
python -B -m unittest discover -s . -p test_scenario_03.py
```

Navy writes shared truth and Navy data first. Army reads the saved truth and
associations, writes Army data and the full replay, and verifies that Navy/shared
inputs remain unchanged. Fixed seeds and Python's standard library suffice.
Generation validates before writing and after saving; `--validate-only` does not
write. Tests cover shared geometry, counts, classification, identity separation,
group evidence, exact schemas, timing, ordering, rejected corruptions, repeatable
generation and preservation of Scenarios 1/2. Regeneration tests rewrite only
Scenario 3 outputs and compare their bytes across repeated runs.
