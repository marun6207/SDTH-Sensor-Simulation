# Synthetic C2 Sensor Dataset

This project generates a reproducible, fictional multi-sensor dataset for a
Command-and-Control (C2) and Common Operating Picture (COP) demonstration.
It supports testing sensor ingestion, data unification, track correlation,
sensor fusion, and plotting on a Singapore map.

This is a synthetic hackathon scenario. It is not a model of real military
sensor performance, communications, weapon performance, or an actual attack
trajectory. Geographic coordinates are synthetic WGS84 coordinates chosen
only to make the tracks coherent on a map.

## Scenarios

The repository contains **three main synthetic scenarios**:

| Scenario | Directory | Overview |
| --- | --- | --- |
| 1 - Multi-Sensor Corroboration | [scenario_01_consistent/](scenario_01_consistent/) | Five fixed-wing UAS observed by sensors that generally provide mutually supporting evidence. |
| 2 - Multi-Sensor Disagreement | [scenario_02_conflicting/](scenario_02_conflicting/) | Five shared physical fixed-wing UAS observed across Airbase, Army and Navy sources, with differing resolution, classification, timing and modalities before stronger corroboration. |
| 3 - Maritime Multi-Sensor Disagreement | [scenario_03_maritime_conflicting/](scenario_03_maritime_conflicting/) | Four shared physical USVs approaching from the south, with radar, EO/IR, AIS, EW, CCTV and GLINT providing different evidence about the same maritime event. |

## Repository Structure

```text
scenario_01_consistent/
  synthetic_airbase_data/         # Airbase feeds, config and shared truth
  synthetic_armybase_data/        # Army feeds, config and associations
  original_sha256.json            # Archived data preservation manifest
scenario_02_conflicting/
  synthetic_airbase_02_data/
  synthetic_armybase_02_data/
  synthetic_navybase_02_data/
  shared_ground_truth/
  scenario_config.json
  scenario_02_all_sensor_events.json
scenario_03_maritime_conflicting/
  synthetic_airbase_03_data/
  synthetic_armybase_03_data/
  synthetic_navybase_03_data/
  shared_ground_truth/
  scenario_config.json
  scenario_03_all_sensor_events.json
synthetic_maritime_data/          # Separate Trojan maritime overlay
exports/                         # Canonical C2 exports
```

Each scenario directory also contains its generators and README. Scenarios 2
and 3 include regression tests. Each site folder contains individual modality
feeds, a `scenario_config.json`, and a chronological `all_sensor_events.json`.

The separate [maritime overlay](synthetic_maritime_data/README.md) combines
Navy AIS, coastal radar, GLINT SAR, POIs and story EW with Scenario 1 land/air
feeds in the [canonical exports](exports/README.md). Its existing root commands
are `python generate_maritime_overlay.py` followed by
`python generate_canonical_stream.py`. See those READMEs for export details.

## Scenario 1 - Multi-Sensor Corroboration

Five synthetic fixed-wing UAS approach `AIRBASE_01` from the east during
**14:30:00-15:00:00**. `ARMY_BASE_01`, approximately 2 km southwest of Airbase,
observes the same trajectories from another viewpoint. Its position is derived
from the saved Airbase configuration.

| Site | Sensor | Interval / first update | Observations |
| --- | --- | --- | ---: |
| AIRBASE_01 | MPSTAR | 2 min / 14:30:00 | 80 |
| AIRBASE_01 | EO/IR | 3 min / 14:30:01 | 50 |
| AIRBASE_01 | EW | 5 min / 14:30:02 | 7 |
| ARMY_BASE_01 | EO/IR | 3 min / 14:30:01 | 50 |
| ARMY_BASE_01 | CCTV | 4 min / 14:30:05 | 8 |
| ARMY_BASE_01 | EW | 5 min / 14:30:02 | 7 |

MPSTAR maintains five tracks. EO/IR progressively resolves the UAS and reports
`UAS` / `fixed-wing`. EW provides persistent supporting `RF-001` evidence about
the overall event. CCTV reports UAS visibility without identifying the subtype.
Neither EW nor CCTV maps to individual UAS. This archived scenario includes
end-minute second-offset observations, unlike the strict boundaries below.

From the repository root, the original generation commands are:

```text
cd scenario_01_consistent
python generate_airbase_scenario.py
python generate_armybase_scenario.py
```

These commands overwrite the archived datasets and are not needed for Scenarios
2 or 3. Army reads existing Airbase configuration/truth, writes its own feeds,
and checks that Airbase JSON files remain unchanged. Generation validates schemas,
confidence, timing, track persistence, event ordering and ground-truth constraints.

Replay uses the per-site
[Airbase stream](scenario_01_consistent/synthetic_airbase_data/all_sensor_events.json)
(137 observations) and
[Army stream](scenario_01_consistent/synthetic_armybase_data/all_sensor_events.json)
(65 observations). There is no scenario-wide replay file in this directory.
Raw feeds contain no geographic truth or hidden UAS IDs. Shared positions are
sampled every minute in the Airbase development files.

## Scenario 2 - Multi-Sensor Disagreement

Exactly **five shared physical fixed-wing UAS** approach from the **southeast
toward the northwest**, during **14:30:00-15:00:00 inclusive**. All three sites
use the same one-second trajectories. The simulated `shahed-type` identity and
RF silence are fictional scenario assumptions.

| Synthetic site | Latitude | Longitude | Sensors |
| --- | ---: | ---: | --- |
| AIRBASE_02, eastern region | 1.345000 | 103.965000 | MPSTAR, EO/IR, EW |
| ARMY_BASE_02, Pulau Tekong region | 1.415000 | 104.045000 | EO/IR, CCTV, EW |
| NAVY_BASE_02, southern region | 1.255000 | 103.835000 | Coastal radar, AIS, GLINT SAR |

### Schedules and observations

| Sensor | Interval / first update | Observations |
| --- | --- | ---: |
| Airbase MPSTAR | 2 min / 14:30:00 | 80 |
| Airbase EO/IR | 3 min / 14:30:01 | 41 |
| Airbase EW | 5 min / 14:30:02 | 6 |
| Army EO/IR | 3 min / 14:30:01 | 44 |
| Army CCTV | 4 min / 14:30:05 | 8 |
| Army EW | 5 min / 14:30:02 | 6 |
| Navy AIS | 5 min / 14:30:07 | 12 |
| Navy coastal radar | 3 min / 14:30:11 | 45 |
| Navy GLINT SAR | Single pass / 14:44:17 | 1 |

Updates after 15:00:00 are excluded; MPSTAR includes the final 15:00:00 scan.

### Disagreement and progression

- MPSTAR resolves five persistent `UAS` / `shahed-type` tracks throughout.
  Airbase EO/IR initially resolves two objects and Army EO/IR three, using
  different subsets and independently shuffled local IDs. Both resolve all
  five from 14:45:01; unresolved objects remain physically present.
- EO/IR initially reports `UAS` / `fixed-wing`. Airbase `EO-003` temporarily
  reports `UNKNOWN` / `unknown` at 14:42:01 with confidence 0.38, recovering
  at 14:45:01. A synthetic range threshold of 18 km enables `shahed-type`
  identification from 14:48:01 at Airbase and 14:51:01 at Army. Confidence
  improves overall with seeded variation and temporary dips.
- Both EW feeds remain operational but report `detected=false`, null emitter
  and bearing, `no_relevant_rf_detection`, and zero confidence throughout.
  Absence of RF corroboration does not invalidate radar/EO evidence.
- Army CCTV rotates three cameras. Only the final scan at **14:58:05** provides
  positive group-level `UAS` evidence. Earlier scans report
  `no_relevant_uas_detection`, `detected=false`, and zero confidence.
- Navy coastal radar maintains two surface-vessel tracks, `SURFACE-207` and
  `SURFACE-412`. It additionally acquires all five shared airborne contacts
  at **14:45:11**, when they meet the synthetic site-relative range threshold
  of **31 km**. These persistent `NAVY-UNK-001` through `NAVY-UNK-005` tracks
  remain `UNKNOWN` / `unknown`, with non-zero altitude. The 45 records comprise
  20 vessel and 25 airborne observations. Early absence means not yet detected.
- AIS reports two fictional cooperative vessels with MMSIs `990000001` and
  `990000002`, rather than the UAS. GLINT supplies one maritime deck-anomaly
  candidate at 14:44:17. AIS and SAR remain maritime context.

### Generation, replay and validation

From the repository root, run in order:

```text
cd scenario_02_conflicting
python -B generate_airbase_02_scenario.py
python -B generate_armybase_02_scenario.py
```

Airbase writes shared truth, associations, expected behavior, configuration and
Airbase feeds. Army then reads those inputs, generates **Army and Navy** feeds,
and writes the combined replay without changing shared truth or Airbase files.
Missing inputs produce an error directing you to run Airbase first.

Use [scenario_02_all_sensor_events.json](scenario_02_conflicting/scenario_02_all_sensor_events.json)
as the primary C2 replay: **243 chronologically sorted raw observations**
(127 Airbase, 58 Army, 58 Navy).

From the Scenario 2 directory, validate saved files without writing:

```text
python -B generate_airbase_02_scenario.py --validate-only
python -B generate_armybase_02_scenario.py --validate-only
```

The first checks shared/Airbase data; the second checks the complete scenario.
Both verify Scenario 1's archived SHA-256 manifest. Checks cover schemas,
schedules, shared trajectory fingerprint and geometry, southeast approach,
EO resolution/classification/recovery, EW and CCTV behavior, Navy acquisition
and maritime context, hidden-data separation, sorted replay and deterministic
model equality. Army also hashes upstream inputs to verify preservation.
The existing regression command is:

```text
python -B -m unittest discover -s . -p test_scenario_02.py
```

## Scenario 3 - Maritime Multi-Sensor Disagreement

Exactly **four shared physical USVs** approach from the **south and travel
generally northward**, during **15:00:00-15:30:00 inclusive**. All object-level
observations relate to these same four hidden physical objects; sites do not
create independent groups. Shared trajectories are sampled every second.

| Synthetic site | Latitude | Longitude | Sensors |
| --- | ---: | ---: | --- |
| AIRBASE_03, southern/southeastern region | 1.290000 | 103.860000 | MPSTAR-style radar, EO/IR, EW |
| ARMY_BASE_03, southern region | 1.265000 | 103.800000 | EO/IR, EW, CCTV |
| NAVY_BASE_03, synthetic maritime site | 1.260000 | 103.720000 | Coastal radar, AIS, GLINT SAR |

All site coordinates are synthetic. Navy Base 03 remains a synthetic maritime
site; the Airbase maritime radar behavior and EW/CCTV assumptions describe only
this fictional demonstration.

### Schedules and observations

| Sensor | Interval / first update | Observations |
| --- | --- | ---: |
| Airbase MPSTAR | 2 min / 15:00:00 | 64 |
| Airbase EO/IR | 3 min / 15:00:01 | 22 |
| Airbase EW | 5 min / 15:00:02 | 6 |
| Army EO/IR | 3 min / 15:00:01 | 25 |
| Army EW | 5 min / 15:00:02 | 6 |
| Army CCTV | 4 min / 15:00:05 | 8 |
| Navy coastal radar | 3 min / 15:00:11 | 40 |
| Navy AIS | 5 min / 15:00:07 | 6 |
| Navy GLINT SAR | Single pass / 15:14:17 | 1 |

Updates after 15:30:00 are excluded; MPSTAR includes 15:30:00. Equal timestamps
use deterministic sensor and local-identity ordering.

### Disagreement and progression

Both Navy coastal radar and Airbase MPSTAR maintain **four persistent tracks**
from their first scans. Classification progresses from `UNKNOWN` / `unknown`
to `SURFACE_CRAFT` / `unknown`, then `USV` / `unmanned-suspected`. Coastal radar
changes at 15:09:11 and 15:21:11; MPSTAR changes at 15:10:00 and 15:22:00.
Classification changes do not change track IDs.

Army and Airbase EO/IR progressively resolve different subsets of the four
contacts. At scan minutes `00, 03, 06, 09, 12, 15, 18, 21, 24, 27` (second `01`):

- Army counts: `1, 1, 2, 2, 2, 3, 3, 3, 4, 4`.
- Airbase counts: `1, 1, 1, 2, 2, 2, 3, 3, 3, 4`.

EO classification starts as `SURFACE_CRAFT` / `unknown` and becomes
`USV` / `small-surface-craft` from 15:18:01. Army `ARMY-EO-002` temporarily
reports `UNKNOWN` at 15:12:01 and recovers at 15:15:01. Confidence generally
improves with seeded dips.

**Only one of the four USVs reports cooperative AIS**, using fictional MMSI
`990000003`. Its association with hidden `USV-02` exists only in developer/evaluation
ground truth. Raw AIS does not expose hidden USV IDs. The other three objects
send no AIS messages; there are no negative AIS records.

Army and Airbase EW provide intermittent **event/group-level RF evidence**,
not one-to-one USV tracks. At the six scheduled scans, Army detection is
`true, false, true, true, false, true`; Airbase detection is
`false, true, true, false, true, true`. Positive reports use `RF-GROUP-03`
and bearings toward the shared group centroid from each site. The first Army
report is ambiguous. Negative reports have null emitter/bearing and zero confidence.

Army CCTV remains operational, rotating three cameras, but **all eight scans
report no relevant synthetic visual anomaly**: `detected=false`,
`classification="no_relevant_visual_anomaly"`, and zero confidence. Camera/image
fields remain present; there are no individual tracks or USV associations.

GLINT SAR supplies one asynchronous maritime return-cluster anomaly at
15:14:17, centered on the shared contact area. Its dimensions describe an area,
not an individual hull; it does not resolve four USV tracks. EW, CCTV and GLINT
have no one-to-one USV associations. Non-detection does not imply physical absence.

Together these feeds present different counts, identities, classifications,
confidence levels, timings and modalities for the **same four-object event**.
Late radar/EO evidence converges on four contacts while AIS remains one reporting
identity and CCTV remains negative.

### Generation, replay and validation

From the repository root, run in order:

```text
cd scenario_03_maritime_conflicting
python -B generate_navybase_03_scenario.py
python -B generate_airbase_03_scenario.py
python -B generate_armybase_03_scenario.py
```

Navy writes shared truth, configuration, evaluation metadata and Navy feeds.
Airbase reads saved Navy/shared inputs and writes Airbase feeds. Army reads
Navy/shared/Airbase inputs, writes Army feeds and builds the complete replay.
Downstream generators protect upstream inputs by hash; missing inputs identify
the prerequisite generator. Run all three in order to refresh the scenario.

Use [scenario_03_all_sensor_events.json](scenario_03_maritime_conflicting/scenario_03_all_sensor_events.json)
as the primary C2 replay: **178 chronologically sorted raw observations**
(92 Airbase, 39 Army, 47 Navy).

From the Scenario 3 directory, validate saved files without writing:

```text
python -B generate_navybase_03_scenario.py --validate-only
python -B generate_airbase_03_scenario.py --validate-only
python -B generate_armybase_03_scenario.py --validate-only
```

These successively check Navy/shared data, Navy/shared/Airbase data, and the
complete scenario. Validation covers four separated northbound paths, shared
geometry and associations, schemas, strict timing, classification/count
progression, group evidence, negative CCTV, raw-only replay and deterministic
model equality. The existing regression command is:

```text
python -B -m unittest discover -s . -p test_scenario_03.py
```

The Scenario 3 tests **regenerate Scenario 3 data**, checking byte-identical
reproducibility, corruption rejection and preservation of Scenarios 1 and 2.
Use the validation-only commands when saved files must remain untouched.

## Data Model

### Raw feeds and hidden ground truth

Raw observations contain sensor-local fields such as `sensor_id`, `timestamp`,
`track_id` where applicable, measurements, classification and confidence where
supported by that modality. Radar/EO feeds may use site-relative geometry;
maritime feeds may contain observed contact coordinates. These coordinates do
not make a raw observation a hidden ground-truth record.

Developer/evaluation files contain hidden physical IDs, shared trajectories,
object-to-track associations and expected behavior. In Scenarios 2 and 3,
`shared_ground_truth/ground_truth_positions.json`, `ground_truth_associations.json`,
and `scenario_02_expected_behavior.json` or `scenario_03_expected_behavior.json`
are **not normal Nexus/C2 replay inputs**. Configuration is separate metadata,
not a sensor event stream. Image filenames are synthetic references.

Combined replay files contain only chronologically sorted raw sensor observations,
without hidden physical IDs, associations or expected-behavior metadata. Local
track suffixes across sensors do not imply a shared physical identity. Fusion
must infer associations from evidence rather than read evaluation mappings.

### Site configuration and sensor location

For Scenarios 2 and 3, each site's `scenario_config.json` contains `scenario_id`,
`site_id`, `latitude`, `longitude`, `start_time`, `end_time` and `sensor_schedules`.
The sensor IDs under `sensor_schedules` belong to that site. Individual observations
do not need to repeat the site's fixed coordinates.

For example, `MPSTAR_AIRBASE_02` is anchored to the coordinates in
[synthetic_airbase_02_data/scenario_config.json](scenario_02_conflicting/synthetic_airbase_02_data/scenario_config.json).
A UI can resolve `sensor_id -> site_id -> site latitude/longitude` using these
configs. Keep this lookup scoped to the scenario, since some sensor IDs recur.

### Multiple tracks per scan

One sensor may produce multiple object-level observations at the same timestamp.
For example, an MPSTAR scan can report `RDR-001`, `RDR-002`, `RDR-003`, `RDR-004`
and `RDR-005` together. Therefore, `sensor_id + timestamp` is not necessarily
unique; `sensor_id + track_id + timestamp` can identify a particular track update
within the scenario. Other modalities use identities such as MMSI or candidate ID.

A UI should interpret the hierarchy as:

```text
Site -> Sensor -> Scan timestamp -> zero, one, or multiple track observations
```

## Validation

Generators use fixed seeds and Python's standard library; no external packages
are required. Scenarios 2 and 3 validate before writing and after reading saved
outputs, checking exact schemas, schedules, geometry, evidence progression,
raw/development separation and deterministic content. Validation failures stop
execution with the failed condition.

The commands in each scenario section distinguish generation from read-only
validation. Preservation checks protect archived or upstream data; regression
tests provide additional scenario-specific coverage. Detailed documentation is
available in the [Scenario 1 README](scenario_01_consistent/README.md),
[Scenario 2 README](scenario_02_conflicting/README.md), and
[Scenario 3 README](scenario_03_maritime_conflicting/README.md).
