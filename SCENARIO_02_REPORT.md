# Scenario 2 completion report

Scenario 1 and Scenario 2 are clearly separated in the same Git repository.
All 13 original Scenario 1 files were moved under `scenario_01_consistent/` and retain their original SHA-256 hashes. No Scenario 1 data was regenerated or edited. Only path constants changed in its generators.

## Repository tree

All project files are shown; `.git/` internals and Python runtime cache are omitted.

```text
SDTH/
|-- scenario_01_consistent/
|   |-- synthetic_airbase_data/
|   |   |-- all_sensor_events.json
|   |   |-- eoir.json
|   |   |-- ew.json
|   |   |-- ground_truth_associations.json
|   |   |-- ground_truth_positions.json
|   |   |-- mpstar.json
|   |   `-- scenario_config.json
|   |-- synthetic_armybase_data/
|   |   |-- all_sensor_events.json
|   |   |-- cctv.json
|   |   |-- eoir.json
|   |   |-- ew.json
|   |   |-- ground_truth_associations.json
|   |   `-- scenario_config.json
|   |-- generate_airbase_scenario.py
|   |-- generate_armybase_scenario.py
|   `-- original_sha256.json
|-- scenario_02_conflicting/
|   |-- shared_ground_truth/
|   |   |-- ground_truth_associations.json
|   |   |-- ground_truth_positions.json
|   |   `-- scenario_02_expected_behavior.json
|   |-- synthetic_airbase_02_data/
|   |   |-- all_sensor_events.json
|   |   |-- eoir.json
|   |   |-- ew.json
|   |   |-- mpstar.json
|   |   `-- scenario_config.json
|   |-- synthetic_armybase_02_data/
|   |   |-- all_sensor_events.json
|   |   |-- cctv.json
|   |   |-- eoir.json
|   |   |-- ew.json
|   |   `-- scenario_config.json
|   |-- generate_airbase_02_scenario.py
|   |-- generate_armybase_02_scenario.py
|   |-- scenario_02_all_sensor_events.json
|   `-- scenario_config.json
|-- README.md
`-- SCENARIO_02_REPORT.md
```

## Sites and starting positions

| Site | Latitude | Longitude |
|---|---:|---:|
| AIRBASE_02 | 1.275000 | 103.820000 |
| ARMY_BASE_02 | 1.263000 | 103.829000 |

Calculated spherical surface separation: **1.6678 km**.

All five start southwest of **both** sites at 14:30:00 and move generally northeast toward them.

| Physical UAS (development only) | Latitude | Longitude | Altitude (m) |
|---|---:|---:|---:|
| UAS-01 | 1.061157942 | 103.608149831 | 655.867 |
| UAS-02 | 1.068757524 | 103.614358187 | 719.709 |
| UAS-03 | 1.073420534 | 103.617869606 | 812.814 |
| UAS-04 | 1.061410457 | 103.623928488 | 858.601 |
| UAS-05 | 1.069144735 | 103.628406534 | 933.271 |

## Hidden track associations (development only)

| Physical UAS | MPSTAR | Airbase EO | Army EO |
|---|---|---|---|
| UAS-01 | RDR-002 | EO-004 | ARMY-EO-004 |
| UAS-02 | RDR-003 | EO-001 | ARMY-EO-005 |
| UAS-03 | RDR-004 | EO-003 | ARMY-EO-002 |
| UAS-04 | RDR-005 | EO-002 | ARMY-EO-003 |
| UAS-05 | RDR-001 | EO-005 | ARMY-EO-001 |

RF-001 and camera IDs are not associated one-to-one with physical UAS.

## EO resolved counts

| Timestamp | Airbase EO | Army EO |
|---|---:|---:|
| 14:30:01 | 2 | 3 |
| 14:33:01 | 3 | 3 |
| 14:36:01 | 3 | 4 |
| 14:39:01 | 4 | 4 |
| 14:42:01 | 4 | 5 |
| 14:45:01 | 5 | 5 |
| 14:48:01 | 5 | 5 |
| 14:51:01 | 5 | 5 |
| 14:54:01 | 5 | 5 |
| 14:57:01 | 5 | 5 |

The strict 15:00:00 endpoint excludes the next EO update at 15:00:01 and EW update at 15:00:02. All in-window scheduled updates are present.

## Temporary classification uncertainty

| Timestamp | Sensor-local track | Classification | Subtype | Confidence |
|---|---|---|---|---:|
| 14:42:01 | EO-003 | UNKNOWN | unknown | 0.38 |
| 14:45:01 | EO-003 | UAS | fixed-wing | 0.689 |

## Early snapshot: 14:30:00 through 14:30:05

| Sensor | Report |
|---|---|
| MPSTAR | 5 tracks |
| Airbase EO/IR | 2 tracks |
| Army EO/IR | 3 tracks |
| Airbase EW | detected=true |
| Army EW | detected=true |
| CCTV | detected=true |

This represents five physical UAS, not ten. Early EO sensors resolve different subsets.

## Validation results

- All exact sensor schemas match Scenario 1, with no unexpected fields.
- Every EW observation has detected=true (6 per site). Every CCTV observation has detected=true (8 total).
- All 16 radar scans contain five persistent tracks; no scheduled observations are missing.
- No hidden UAS ID or association appears in any raw sensor event.
- Both site streams and the 185-observation scenario_02_all_sensor_events.json are chronologically sorted and contain only raw observations.
- Geometry uses each sensor site and the single shared set of five trajectories.
- Same-track classification recovery and non-monotonic confidence validation passed.
- Ground truth, expected behavior, and configuration remain separate from replay data.
- Regeneration was byte-identical for every Scenario 2 JSON file.
- Seven deliberate in-memory corruptions were rejected: missing radar update, hidden ID field, EW non-detection, CCTV non-detection, wrong Army geometry, unsorted stream, and wrong site coordinates.
- All 13 Scenario 1 file hashes and the original inventory remain unchanged.

Commands verified, in order from repository root:

```text
python scenario_02_conflicting/generate_airbase_02_scenario.py
python scenario_02_conflicting/generate_armybase_02_scenario.py
python scenario_02_conflicting/generate_airbase_02_scenario.py --validate-only
python scenario_02_conflicting/generate_armybase_02_scenario.py --validate-only
```

The Airbase generator creates the shared truth, associations, expected behavior and
Airbase observations. The Army generator reads those inputs, generates Army observations,
and builds the combined replay stream. Common helpers live in the Airbase script and
are imported by the Army script, without generating trajectories at import time.

After this refactor, all 29 repository JSON files matched their pre-refactor SHA-256
hashes, including all 15 Scenario 2 JSON files. The five trajectories, sensor schemas,
confidence values, mappings, disagreement behavior, and combined ordering are byte-identical.
Scenario 1 was not regenerated or modified.

A clean temporary two-stage build also matched every existing Scenario 2 JSON byte.
Disabling trajectory generation during the Army run and its validation-only run did
not affect either operation. Missing shared inputs produced the required clear error.
Both validation-only entry points worked from outside the repository directory.
The replaced single generator was removed after successful validation.
