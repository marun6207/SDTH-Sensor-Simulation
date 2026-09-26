# Scenario 2 - Multi-Sensor Disagreement

Exactly **five physical fixed-wing UAS** approach Singapore from the southeast
between 14:30:00 and 15:00:00. All three sites observe the same trajectories.
Development-only truth identifies a fictional simulated Shahed-type swarm.
Site locations, identification rules and lack of detectable RF are simulation
assumptions, not real installation coordinates or real-world sensor/UAS claims.
This legacy fusion benchmark is distinct from Nexus `S2_osint_swarm`.

## Sites and sensors

| Fictional site | Latitude | Longitude | Sensors |
| --- | --- | --- | --- |
| AIRBASE_02 (eastern Singapore) | 1.345000 | 103.965000 | MPSTAR, EO/IR, EW |
| ARMY_BASE_02 (Pulau Tekong region) | 1.415000 | 104.045000 | EO/IR, CCTV, EW |
| NAVY_BASE_02 (southern Singapore region) | 1.255000 | 103.835000 | AIS, coastal radar, GLINT SAR |

The Army site's broad island placement was checked against the
[NUS locality gazetteer](https://lkcnhm.nus.edu.sg/app/uploads/2017/04/gazetteer_locality_names.pdf).
All bearings, ranges and elevations use the relevant fictional site and shared
truth. Navy generates two clearly fictional vessels with synthetic offline MMSIs:
AIS reports their cooperative maritime positions, and coastal radar observes
the same surface traffic using persistent `SURFACE-207` and `SURFACE-412` tracks
at zero altitude. AIS and the surface tracks retain their existing behavior.
GLINT SAR provides one maritime deck-anomaly candidate at 14:44:17. These three
feeds preserve the field names and array structure of `synthetic_maritime_data/`;
that existing dataset is unchanged. AIS and SAR remain maritime-only.

Coastal radar additionally detects approaching airborne contacts only when each
object's surface range from `NAVY_BASE_02` is **31 km or less** at a scheduled
scan. This fictional threshold is recorded in the Navy configuration. The same
five shared trajectories drive detection: no extra swarm is created. All five
are first reported at **14:45:11**, after five vessel-only scans. Their persistent,
independently shuffled `NAVY-UNK-001` through `NAVY-UNK-005` IDs are mapped to
physical objects only in the development association file. Coastal radar reports
`UNKNOWN` / `unknown` throughout, with exact shared positions, non-zero altitude,
speed derived from the preceding second, and synthetic RCS 0.035 m2.

Missing early coastal tracks mean **not yet detected by this sensor**, not that
the objects do not exist. Nexus must correlate the later Navy contacts with
earlier Airbase/Army evidence; Navy does not independently identify their type.

## Disagreement and progression

The scenario combines six sources of disagreement: different resolved counts
and subsets, classification specificity, varying confidence and temporary
uncertainty, EW non-corroboration, asynchronous timing, and different viewing
geometry from geographically separated sites.

- **Early:** Airbase MPSTAR maintains five tracks classified `UAS` / `shahed-type`.
  Airbase EO/IR resolves two and Army EO/IR three different members of the same
  five, initially classified `UAS` / `fixed-wing`. Unresolved UAS still exist.
- **Middle:** EO/IR resolves progressively more objects. Confidence improves
  overall with temporary dips. Airbase `EO-003` becomes `UNKNOWN` / `unknown`
  at 14:42:01 (confidence 0.38), returning to fixed-wing at 14:45:01.
  Both EO/IR sensors resolve five from 14:45:01. Coastal radar acquires five
  additional UNKNOWN airborne contacts at 14:45:11 alongside its two vessels.
- **Late:** The synthetic EO/IR identification rule is range <= 18 km. Airbase
  reports `shahed-type` from 14:48:01 and Army from 14:51:01. MPSTAR still resolves
  five; Navy retains five UNKNOWN contacts. Fusion can combine the evidence
  despite different classification specificity and varying confidence.

EW never provides relevant RF corroboration. Its existing field names are
preserved, with `detected=false`, `emitter_id=null`, `bearing_deg=null`,
`classification="no_relevant_rf_detection"`, and `confidence=0.0` (no positive
RF detection confidence). Consumers must accept these nulls; no emitter or
bearing is fabricated. This synthetic RF assumption does not describe all real
Shahed-type UAS. Lack of EW corroboration must not automatically invalidate the
radar/EO evidence. Army CCTV provides event-level UAS visibility from three
rotating cameras, not individual counts or hidden associations.

## Asynchronous observations

| Sensor | Interval | First update |
| --- | --- | --- |
| Airbase MPSTAR | 2 minutes | 14:30:00 |
| Airbase and Army EO/IR | 3 minutes | 14:30:01 |
| Airbase and Army EW | 5 minutes | 14:30:02 |
| Army CCTV | 4 minutes | 14:30:05 |
| Navy AIS | 5 minutes | 14:30:07 |
| Navy coastal radar | 3 minutes | 14:30:11 |
| Navy GLINT SAR | One asynchronous pass | 14:44:17 |

Updates after 15:00:00 are excluded. Each aerial tracking sensor uses independently
shuffled local IDs; matching numeric suffixes do not imply the same object.

## Files and replay

**Use `scenario_02_all_sensor_events.json` as the primary Nexus C2 replay input
for this scenario.** Its 243 raw observations combine all three sites chronologically.
Navy contributes 58: 12 AIS, 45 coastal radar (20 vessel + 25 airborne), and 1 GLINT SAR.

- `synthetic_airbase_02_data/`: `mpstar.json`, `eoir.json`, `ew.json`,
  `all_sensor_events.json`, `scenario_config.json`.
- `synthetic_armybase_02_data/`: `eoir.json`, `cctv.json`, `ew.json`,
  `all_sensor_events.json`, `scenario_config.json`.
- `synthetic_navybase_02_data/`: `ais.json`, `coastal_radar.json`,
  `glint_sar.json`, `all_sensor_events.json`, `scenario_config.json`.
- `shared_ground_truth/`: `ground_truth_positions.json` (one-second positions,
  hidden identities and true simulated subtype), `ground_truth_associations.json`
  (hidden object-to-track mapping), `scenario_02_expected_behavior.json` (evaluation).
- Root `scenario_config.json`: all sites, schedules and simulation assumptions.

Each site stream combines only its raw modality files. Raw feeds expose no
hidden UAS identities or object-to-sensor associations. Coastal radar reports
coordinates for its observed contacts; AIS and SAR report vessel/candidate coordinates.
Configuration and development/evaluation files stay separate from replay data.

## Generate and validate

From the repository root, run the existing two commands in order:

```text
cd scenario_02_conflicting
python generate_airbase_02_scenario.py
python generate_armybase_02_scenario.py
```

Airbase writes shared truth, evaluation metadata, configuration and Airbase
observations. The Army generator then reads those saved inputs, generates Army
and Navy observations, and writes the combined replay. It does not regenerate
trajectories or alter upstream files. Missing inputs direct you to run Airbase
first. Fixed seeds make generation reproducible; no external packages are needed.

Validate saved files without writing:

```text
python generate_airbase_02_scenario.py --validate-only
python generate_armybase_02_scenario.py --validate-only
python -B -m unittest discover -s . -p test_scenario_02.py
```

Generation validates before writing and after saving. Validation checks five
complete shared trajectories and their fingerprint, southeast approach, site
regions, exact schemas, geometry, schedules, radar persistence, EO counts/subsets
and classification progression, confidence variation, uncertainty/recovery,
EW non-detection, independent IDs, hidden-data separation, chronological streams,
and agreement with the deterministic model. Both commands check Scenario 1's
archived SHA-256 manifest; Army also verifies unchanged Airbase/shared inputs.
Navy checks enforce reference schemas, unchanged vessel observations, range-gated
acquisition, persistent UNKNOWN airborne contacts tied to shared trajectories,
maritime-only AIS/SAR, and complete sorted streams. Regression tests freeze the
Airbase/Army outputs, shared positions, AIS and SAR by SHA-256 and check the exact
Navy file inventory. Validation failures stop execution.
