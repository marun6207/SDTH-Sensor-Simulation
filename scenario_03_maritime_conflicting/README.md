# Scenario 3 - Maritime Multi-Sensor Disagreement

`SCENARIO_03` runs from **15:00:00 through 15:30:00 inclusive**. Exactly **four
physical USVs** approach from the **south and travel generally northward**.
All object-level observations across three participating sites derive from the
same shared trajectories. There are no separate site-specific groups.

All coordinates, identities, classifications and sensor behavior are fictional
simulation data, not actual military installations or real sensor performance.
In particular, the MPSTAR maritime behavior and RF/CCTV assumptions are synthetic.

## Sites and inventory

| Site | Latitude | Longitude | Sensors |
| --- | --- | --- | --- |
| AIRBASE_03, added in the fictional southern/southeastern region | 1.290 | 103.860 | MPSTAR, EO/IR, EW |
| ARMY_BASE_03, relocated to the fictional southern region | 1.265 | 103.800 | EO/IR, EW, CCTV |
| NAVY_BASE_03, location unchanged | 1.260 | 103.720 | Coastal radar, AIS, GLINT SAR |

## Timing and counts

| Sensor | Schedule, starting at | Raw observations |
| --- | --- | --- |
| MPSTAR_AIRBASE_03 | Every 2 minutes, 15:00:00 | 64 |
| EOIR_AIRBASE_03 | Every 3 minutes, 15:00:01 | 22 |
| AIRBASE_EW_03 | Every 5 minutes, 15:00:02 | 6 |
| EOIR_ARMYBASE_03 | Every 3 minutes, 15:00:01 | 25 |
| ARMYBASE_EW_03 | Every 5 minutes, 15:00:02 | 6 |
| CCTV_ARMYBASE_03 | Every 4 minutes, 15:00:05 | 8 |
| NAVY_COASTAL_RADAR_03 | Every 3 minutes, 15:00:11 | 40 |
| MPA_OCEANS_X_AIS | Every 5 minutes, 15:00:07 | 6 |
| GLINT_SAR_PASS_SIM_03 | One pass at 15:14:17 | 1 |

Full timestamps must be <= 15:30:00. MPSTAR includes 15:30:00; all second-offset
15:30 observations are excluded. Equal timestamps use deterministic sensor and
local-identity ordering.

At EO scan minutes `00, 03, 06, 09, 12, 15, 18, 21, 24, 27` (second `01`):

- Army resolved counts: `1, 1, 2, 2, 2, 3, 3, 3, 4, 4`.
- Airbase resolved counts: `1, 1, 1, 2, 2, 2, 3, 3, 3, 4`.

## Disagreement and convergence

Both radars maintain four persistent tracks from their first scheduled scan.
Their classifications progress by time: `UNKNOWN / unknown` before 15:09,
`SURFACE_CRAFT / unknown` from 15:09 until 15:21, and
`USV / unmanned-suspected` from 15:21 onward. Applied to their schedules, MPSTAR
changes at 15:10:00 and 15:22:00; coastal radar changes at 15:09:11 and 15:21:11.
Track IDs never change with classification.

The two EO sensors acquire different subsets in different orders. Initial
`SURFACE_CRAFT / unknown` becomes `USV / small-surface-craft` from 15:18:01.
Army `ARMY-EO-002` temporarily becomes `UNKNOWN` at 15:12:01 and recovers at
15:15:01. Seeded confidence improves overall with dips on established tracks;
newly acquired late tracks may have only one or two observations.

AIS is cooperative reporting: **only hidden USV-02** reports fictional MMSI
`990000003`, named `SIMULATED COOPERATIVE CRAFT`. The other three emit no AIS
messages. This is not AIS missing radar targets, and no negative AIS records
are generated. The hidden association appears only in development data.

Army and Airbase EW report group-sector RF evidence, never exact object positions
or individual USV identities. At `15:00:02, 15:05:02, 15:10:02, 15:15:02,
15:20:02, 15:25:02`, the detection sequences are:

- Army: `true, false, true, true, false, true`; confidence
  `0.32, 0, 0.64, 0.71, 0, 0.78`. The first positive report is ambiguous.
- Airbase: `false, true, true, false, true, true`; confidence
  `0, 0.42, 0.58, 0, 0.68, 0.74`.

Positive EW bearings use each site's view of the four-contact centroid.
`RF-GROUP-03` denotes event-level evidence, not an individual association.
Negative EW reports have null emitter/bearing and zero confidence.

Army CCTV is operational but **all eight observations remain negative**, unchanged
at 15:00:05, 15:04:05, 15:08:05, 15:12:05, 15:16:05, 15:20:05, 15:24:05 and
15:28:05. Records retain `detected=false`, `no_relevant_visual_anomaly`, zero
confidence and camera/image fields. They contain no tracks or USV associations.
Non-detection is not evidence that the physical USVs do not exist.

GLINT contributes one maritime return-cluster anomaly at the shared contact-area
centroid, not four identified tracks. Its synthetic dimensions describe an area,
not an individual hull. EW, CCTV and GLINT have no one-to-one USV associations.

Nexus must reconcile counts, cooperative identity, classifications, confidence,
timing, modalities and shuffled local IDs. Late radar/EO evidence converges on
four contacts while AIS remains one reporting identity and CCTV remains negative.

## Files and replay

**Use `scenario_03_all_sensor_events.json` as the primary Nexus replay.** It contains
**178 raw observations: 92 Airbase, 39 Army and 47 Navy**, chronologically sorted.
It excludes hidden USV IDs, associations and expected-behavior metadata.

- `synthetic_airbase_03_data/`: `mpstar.json`, `eoir.json`, `ew.json`,
  `all_sensor_events.json`, `scenario_config.json`.
- `synthetic_armybase_03_data/`: `eoir.json`, `ew.json`, `cctv.json`,
  `all_sensor_events.json`, `scenario_config.json`.
- `synthetic_navybase_03_data/`: `coastal_radar.json`, `ais.json`, `glint_sar.json`,
  `all_sensor_events.json`, `scenario_config.json`.
- `shared_ground_truth/`: `ground_truth_positions.json` (four one-second physical
  paths, speed/course and true type), `ground_truth_associations.json` (requested
  hidden local-track mapping), `scenario_03_expected_behavior.json` (evaluation).
- Root `scenario_config.json`: sites, schedules and synthetic assumptions.

Maritime schemas and Scenario 2 Airbase/Army field names are preserved. Ground
truth IDs `USV-01` through `USV-04` exist only in development/evaluation files.
Raw maritime coordinates and site-relative radar/EO geometry describe observations.

## Generate and validate

From the repository root:

```text
cd scenario_03_maritime_conflicting
python -B generate_navybase_03_scenario.py
python -B generate_airbase_03_scenario.py
python -B generate_armybase_03_scenario.py
python -B generate_navybase_03_scenario.py --validate-only
python -B generate_airbase_03_scenario.py --validate-only
python -B generate_armybase_03_scenario.py --validate-only
python -B -m unittest discover -s . -p test_scenario_03.py
```

Navy writes shared truth and Navy data. Airbase reads those inputs and writes its
feeds. Army reads saved Navy/shared/Airbase inputs, writes Army feeds and builds
the complete replay. Downstream generators protect their upstream inputs by hash.
Run all three in order to refresh the complete scenario. Missing inputs produce
an error directing you to the prerequisite generator.

Generation validates before and after writing. Validation-only commands do not
write. Tests cover four separated northbound paths, shared geometry, the requested
mapping, classification/count progression, group evidence, unchanged negative CCTV,
exact schemas, strict timing, raw-only replay, corruption rejection, repeated
byte-identical generation and preservation of Scenarios 1 and 2. Tests regenerate
only Scenario 3. Python's standard library is sufficient.
