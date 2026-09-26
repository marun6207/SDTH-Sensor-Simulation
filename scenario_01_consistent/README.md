# Scenario 1 – Multi-Sensor Corroboration

This is the baseline case: sensors broadly corroborate the same event. Five
synthetic fixed-wing UAS approach `AIRBASE_01` from the east during the
14:30–15:00 scenario. The hidden physical objects are `UAS-01` through `UAS-05`.
Both sites observe these same five trajectories; Army Base does not create a
second swarm. Different viewpoints and sensor modalities produce different measurements.

## Sites and observations

`AIRBASE_01` is the original site. `ARMY_BASE_01` is approximately 2 km southwest,
with its location calculated from the saved Airbase configuration.

| Site | Sensor | Observations |
| --- | --- | --- |
| AIRBASE_01 | MPSTAR | Five persistent inbound radar tracks, `RDR-001`–`RDR-005`. |
| AIRBASE_01 | EO/IR | `EO-001`–`EO-005`, classified as `UAS` / `fixed-wing`; fewer tracks are visible initially. |
| AIRBASE_01 | EW | Persistent `RF-001` activity classified as `suspected_uas_link` in the same general sector. |
| ARMY_BASE_01 | EO/IR | `ARMY-EO-001`–`ARMY-EO-005`, observing the shared trajectories from a second viewpoint. |
| ARMY_BASE_01 | CCTV | UAS visibility from `CAM-001`–`CAM-003`, without fixed-wing subtype identification. |
| ARMY_BASE_01 | EW | `ARMYBASE_EW_01` reports supporting `RF-001` activity. |

EW supports the overall event; neither RF emitters nor CCTV cameras are mapped
to individual physical UAS.

## Asynchronous updates

| Sensor | Interval | First update |
| --- | --- | --- |
| MPSTAR | 2 minutes | 14:30:00 |
| EO/IR at both sites | 3 minutes | 14:30:01 |
| EW at both sites | 5 minutes | 14:30:02 |
| CCTV | 4 minutes | 14:30:05 |

These intervals and second offsets let ingestion and fusion process asynchronous
observations rather than assume simultaneous reports.

## Files

- `synthetic_airbase_data/`: `mpstar.json`, `eoir.json`, `ew.json`,
  `all_sensor_events.json`, `scenario_config.json`, `ground_truth_positions.json`,
  and `ground_truth_associations.json`.
- `synthetic_armybase_data/`: `eoir.json`, `cctv.json`, `ew.json`,
  `all_sensor_events.json`, `scenario_config.json`, and `ground_truth_associations.json`.
- `original_sha256.json`: preservation manifest checked by Scenario 2 validation.

The modality files are raw sensor observations: they contain no latitude,
longitude, or hidden UAS IDs. Each site's `all_sensor_events.json` combines its
raw records chronologically without adding fields.

Configuration and ground truth are separate development/evaluation inputs.
`scenario_config.json` describes the site; Airbase `ground_truth_positions.json`
stores the shared WGS84 positions at one-minute intervals; association files
provide hidden object-to-track mappings for evaluating correlation. They are
not raw sensor feeds.

## Run the generators

From the repository root, run Airbase first, then Army Base:

```text
cd scenario_01_consistent
python generate_airbase_scenario.py
python generate_armybase_scenario.py
```

These commands overwrite the archived Scenario 1 datasets. They are not needed
to generate Scenario 2. Both use fixed random seeds and require no external
Python packages. Army Base reads the existing Airbase configuration and ground
truth, writes its own output folder, and checks that Airbase JSON files remain unchanged.

The generators validate schemas, confidence ranges, timing, track persistence,
event ordering, and ground-truth constraints.
