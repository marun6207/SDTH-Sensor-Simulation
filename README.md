# Synthetic C2 Sensor Dataset

This project generates a reproducible, fictional multi-sensor dataset for a
Command-and-Control (C2) and Common Operating Picture (COP) demonstration.
The data is suitable for testing sensor ingestion, data unification, track
correlation, sensor fusion, and plotting on a Singapore map.

This is a synthetic hackathon scenario. It is not a model of real military
sensor performance, communications, weapon performance, or an actual attack
trajectory. The geographic coordinates are synthetic WGS84 coordinates chosen
only to make the tracks coherent on a map.

---

## 🏛️ Relationship with Nexus C2 (Three Operational Pillars)

> **Primary hero is airborne `S2_osint_swarm`. Maritime secondary track is `S1_trojan` (tri-service + GLINT hull anchor) then `S3_sar_ais` (GLINT macro × SIA × AIS dark vessel). marun `scenario_02_conflicting` is a legacy fusion bench, not Nexus S2.**

### Three-Pillar Operational Mapping

| Rank | Nexus ID | Role | GLINT Usage |
|------|----------|------|-------------|
| **1 (Primary Hero)** | `S2_osint_swarm` | In-flight OSINT ~50 × radar 4 / RF silence → GNSS denial + GBAD (Cognitive / Autonomous Saturation / Anti-Exhaustion) | **Not used** (Air domain & social sensor) |
| **2** | `S1_trojan` | Maritime + Land/Air: AIS vs coastal radar, CNI VETO, Option B (Tri-service contradiction + spatial SAR mothership lock) | **Used** — Mothership aft-deck / hull spatial anchor (already in narrative & export) |
| **3** | `S3_sar_ais` | Dark vessel: Dual-SAR × thin AIS → Approach Patrol (Orbital latency → reachable ellipse → USV intercept) | **Primary showcase** — macro cluster (`:5051` / live) + SIA micro |

*Auxiliary baseline*: `S1_ais_spoof` serves as a lightweight baseline outside the three pillars (no GLINT).

### Data Role Alignment with marun

| Data Feed | Storage Location | marun Role |
|-----------|------------------|------------|
| **S2 Synthetic** (OSINT / radar 4 / acoustic / RF silent) | marun **new** `exports/s2_osint_swarm_*.jsonl` | marun canonical export (*`scenario_02_conflicting` is a legacy fusion bench, not Nexus S2*) |
| **Trojan Maritime + Land/Air + GLINT row** | Existing `synthetic_maritime_data/` → `exports/s1_trojan_*` | marun `exports/s1_trojan_scenario.jsonl` |
| **S3 Coastal AIS / Radar** | marun optional; **GLINT macro / SIA chip owned by Nexus / Team 02 / SIA** | GLINT `:5051` / SIA `:5050` / Indago DuckDB |

*Note on `scenario_02_conflicting/`*: The in-repo directory `scenario_02_conflicting/` is a **legacy fusion benchmark** (evaluating dual-site Airbase vs Army Base 5-UAS resolution), **not** Nexus `S2_osint_swarm`. Nexus `S2_osint_swarm` represents the 50-drone autonomous saturation raid triggered by in-flight civilian passenger OSINT and will be housed under `exports/s2_osint_swarm_*.jsonl`.

---

The repository contains **two separated legacy scenarios** in the same Git repository:

- `scenario_01_consistent/`: existing five-UAS multi-sensor corroboration, for
  ingestion and fusion of mutually supporting observations.
- `scenario_02_conflicting/`: a shared five-UAS southwest approach with controlled
  disagreement between two synthetic sites (legacy fusion benchmark).

Generate Scenario 2 by running its Airbase generator first, then its Army generator:

```text
cd scenario_02_conflicting
python generate_airbase_02_scenario.py
python generate_armybase_02_scenario.py
```

The Airbase generator creates the shared five-UAS physical ground truth, associations,
expected behavior, scenario configuration, and Airbase observations. The Army generator
reads that saved ground truth and mapping, creates Army observations, and writes the
combined `scenario_02_all_sensor_events.json`. It never generates trajectories or writes
the shared truth or Airbase files. Run both scripts in this order to refresh a scenario.
Missing shared inputs cause a clear error directing you to run the Airbase generator first.
The Army script imports common observation and validation helpers from the Airbase script;
there is only one implementation of those helpers.

From the Scenario 2 directory, validate saved data without writing:

```text
python generate_airbase_02_scenario.py --validate-only
python generate_armybase_02_scenario.py --validate-only
```

The first validates shared truth and Airbase files; the second validates the complete
scenario and combined stream. Both verify the archived Scenario 1 SHA-256 manifest.
No external packages
are required. See [the completed report](SCENARIO_02_REPORT.md) for the full directory
tree, starting positions, hidden associations, count progression, and validation results.

## Scenario 1 - Multi-Sensor Corroboration

Scenario 1 is named **Multi-Sensor Corroboration** (previously Consistent Multi-Sensor Detection). Five synthetic
fixed-wing UAS objects move as a loose swarm from the eastern side of
`AIRBASE_01` toward the airbase area during:

```text
14:30:00 through 15:00:00
```

The physical objects are represented internally by:

```text
UAS-01  UAS-02  UAS-03  UAS-04  UAS-05
```

Their positions are stored separately in WGS84 ground truth. Raw sensor feeds
do not contain latitude, longitude, or these internal object IDs. The purpose
of the scenario is to let a future fusion layer infer that different sensor
tracks describe the same physical event.

The best-case scenario is intentionally mutually consistent:

- MPSTAR reports five persistent inbound radar tracks.
- EO/IR reports visual observations classified as `UAS` with subtype
  `fixed-wing`.
- EW reports persistent RF activity classified as `suspected_uas_link` in the
  same general sector.
- Army Base sensors observe the same physical UAS trajectories from a second
  location and use different viewing geometry.

The measurements are not identical because the sensors use different
modalities and are located at different sites.

## Sensor Sites

### AIRBASE_01

`AIRBASE_01` is the original synthetic sensor site. Its fixed WGS84 location
is stored in [scenario_01_consistent/synthetic_airbase_data/scenario_config.json](scenario_01_consistent/synthetic_airbase_data/scenario_config.json).

Sensors at this site are:

- **MPSTAR**: five persistent tracks, `RDR-001` through `RDR-005`, updating
  every 2 minutes.
- **EO/IR**: tracks `EO-001` through `EO-005`, updating every 3 minutes.
  Fewer tracks may be visible in the early scans, then more become available.
- **EW**: one persistent supporting RF signature, `RF-001`, updating every
  5 minutes. `RF-001` is evidence about the overall event, not a specific UAS.

### ARMY_BASE_01

`ARMY_BASE_01` is generated separately approximately 2 km southwest of
`AIRBASE_01`. The generator reads the existing Airbase configuration instead
of hard-coding its coordinates, calculates the southwest offset, and stores
the result in [scenario_01_consistent/synthetic_armybase_data/scenario_config.json](scenario_01_consistent/synthetic_armybase_data/scenario_config.json).

Sensors at this site are:

- **EO/IR**: Army-specific tracks `ARMY-EO-001` through `ARMY-EO-005`, using
  the same EO/IR schema as the Airbase sensor and updating every 3 minutes.
- **CCTV**: simple visual detections from `CAM-001`, `CAM-002`, and
  `CAM-003`, updating every 4 minutes. CCTV reports that a UAS is visible but
  does not identify the fixed-wing subtype.
- **EW**: sensor `ARMYBASE_EW_01`, using persistent emitter `RF-001` and
  updating every 5 minutes. This RF signature is not mapped to an individual
  UAS.

Both sites reuse the same Airbase ground-truth trajectory. Army Base does not
create a second independent swarm.

## Asynchronous Updates

The sensor streams intentionally update at different intervals and use small
second offsets:

```text
MPSTAR: 14:30:00, 14:32:00, 14:34:00, ...
EO/IR:  14:30:01, 14:33:01, 14:36:01, ...
EW:     14:30:02, 14:35:02, 14:40:02, ...
CCTV:   14:30:05, 14:34:05, 14:38:05, ...
```

This allows an ingestion or fusion system to process a realistic event stream
rather than assuming all sensors report simultaneously.

## Output Files

The two sites are deliberately separated in the VS Code Explorer:

```text
scenario_01_consistent/synthetic_airbase_data/
  scenario_config.json
  mpstar.json
  eoir.json
  ew.json
  ground_truth_positions.json
  ground_truth_associations.json
  all_sensor_events.json

scenario_01_consistent/synthetic_armybase_data/
  scenario_config.json
  eoir.json
  cctv.json
  ew.json
  ground_truth_associations.json
  all_sensor_events.json
```

### Raw sensor files

Raw files contain only their defined sensor fields. They do not contain
geographic ground truth or fused object IDs:

- `mpstar.json`: 80 observations, five radar records per 16 scans.
- `eoir.json`: 50 Airbase EO/IR observations.
- `ew.json`: 7 Airbase EW observations.
- Army `eoir.json`: 50 observations.
- Army `cctv.json`: 8 CCTV observations.
- Army `ew.json`: 7 observations.

### Development and evaluation files

- `ground_truth_positions.json` contains the shared latitude/longitude
  position of each UAS at every minute. It is not sensor data.
- `ground_truth_associations.json` contains hidden object-to-track mappings
  for evaluating correlation. RF emitters and CCTV cameras are intentionally
  not mapped to individual UAS objects.
- `all_sensor_events.json` combines only that site's raw sensor records and
  sorts them chronologically without adding fields.

## Original Scenario 1 generators

The existing Scenario 1 datasets are preserved byte-for-byte under `scenario_01_consistent/`.
The commands below are retained for reference: running them overwrites those archived
datasets. They are not needed to generate Scenario 2. Only their directory paths have changed.

Open the project folder in VS Code and open **Terminal > New Terminal**.
Run the original Airbase generator with:

```text
cd scenario_01_consistent
python generate_airbase_scenario.py
```

Run the Army Base generator with:

```text
python generate_armybase_scenario.py
```

The Army generator expects the existing Airbase configuration and ground truth
to exist. It writes only to `scenario_01_consistent/synthetic_armybase_data/` and checks that the
existing Airbase JSON files were not modified.

Both generators use fixed random seeds so repeated runs produce reproducible
measurements. No external Python packages are required.

## Validation

The generators validate exact raw schemas and fail if fields are missing,
renamed, or added. They also check confidence ranges, timestamp boundaries,
track persistence, chronological event ordering, ground-truth coordinate
bounds, and the separation between raw observations and development-only
ground truth.

## Trojan mothership overlay (issue #116)

Navy AIS (Happy Tug 8), coastal radar (~120 kt UAS), GLINT SAR, POIs, and
story EW LOBs live under
[`synthetic_maritime_data/`](synthetic_maritime_data/)
(see [synthetic_maritime_data/README.md](synthetic_maritime_data/README.md)).
Canonical C2 export files live under [`exports/`](exports/)
(see [exports/README.md](exports/README.md)).

The canonical stream merges Scenario 1 land/air feeds from
`scenario_01_consistent/` with the maritime overlay (story contradiction is
AIS vs coastal radar). Run from the repository root:

```text
python generate_maritime_overlay.py
python generate_canonical_stream.py
```

Outputs:

- `exports/s1_trojan_scenario.jsonl` — time-compressed multi-service stream
- `exports/site_origins.json` — site latitudes/longitudes for polar
  reverse-geocode
- `exports/pois.json` — Jurong CNI + military POI buffers

## Scenario 2 - Multi-Sensor Disagreement

**Southwest UAS Approach with Multi-Sensor Disagreement** retains a hidden ground
truth of exactly five physical fixed-wing UAS approaching AIRBASE_02 and ARMY_BASE_02
from the southwest. Unlike Scenario 1's generally corroborating observations, the
sensors intentionally begin with differing assessments of the same physical event.

Disagreement is introduced through different numbers and subsets of independently
resolved objects, different sensor-local track identities and confidence levels,
temporary EO/IR classification uncertainty, asynchronous updates, and different
viewing geometry caused by the geographically separated sites.

MPSTAR consistently resolves all five tracks. Initially, Airbase EO/IR resolves
fewer objects, while Army EO/IR may resolve a different number or subset of the same
five UAS. One persistent EO/IR track temporarily reports `UNKNOWN` with low confidence
before returning to `UAS` / `fixed-wing`. EW continues to provide supporting RF
evidence for the overall event, and CCTV provides supporting visual UAS evidence.
Nexus C2 must reconcile these observations. As the UAS approach, both EO/IR sensors
progressively resolve all five objects, moving the picture from **multi-sensor
disagreement** toward **stronger multi-sensor corroboration**. Fewer EO/IR tracks
indicate incomplete resolution: **five physical UAS remain present throughout**.

All sensors stay operational. Disagreement is **not** created through sensor outages,
missed scheduled updates, radar track dropouts, RF or CCTV non-detection, or random
or physically nonsensical measurements.

AIRBASE_02 is at **1.275000, 103.820000** and ARMY_BASE_02 is at **1.263000,
103.829000**. Their spherical surface separation is **1.6678 km**. These are
fictional scenario coordinates.

The group approaches northeast from southwest of both sites over 14:30:00 through 15:00:00.
Continuous curved trajectories have different starting positions, paths, and altitudes.
The development file samples them every second, including all observation times.
The fixed seed is `20260925`. Geometry uses a spherical Earth with radius 6371.0088 km,
surface range, and local flat elevation relative to synthetic sites at altitude zero.
This is a coherent synthetic observation model, not a calibrated sensor performance model.

Acquisition order is a scripted model of different viewpoints and gradual resolution.
Confidence depends on approach distance with independent seeded quality variation
and small non-monotonic changes.

| Sensor | Interval | Seconds | Observations |
| --- | ---: | ---: | ---: |
| Airbase MPSTAR | 2 min | :00 | 80 |
| Airbase EO/IR | 3 min | :01 | 41 |
| Airbase EW | 5 min | :02 | 6 |
| Army EO/IR | 3 min | :01 | 44 |
| Army CCTV | 4 min | :05 | 8 |
| Army EW | 5 min | :02 | 6 |

Scenario 2 uses a strict inclusive **15:00:00** boundary. Radar reports at 15:00:00;
EO at 15:00:01 and EW at 15:00:02 are outside the scenario and are not scheduled.
This differs from the archived Scenario 1 convention, which includes end-minute offsets.
CCTV rotates CAM-001, CAM-002, and CAM-003, one scheduled camera observation per scan.
EW RF-001 represents the general group sector, with bearings derived from the shared
five-object centroid at each site's location. Neither cameras nor RF-001 map to a UAS.
Image names are synthetic references; image files are not generated.

At 14:42:01, one existing Airbase EO track reports UNKNOWN/unknown with confidence
0.38; at 14:45:01 the same ID returns to UAS/fixed-wing with improved confidence.
Both EO systems independently resolve five objects from 14:45:01 onward. Radar
resolves five at every scheduled scan.

### Replay versus development data

Use [scenario_02_all_sensor_events.json](scenario_02_conflicting/scenario_02_all_sensor_events.json)
as the primary Nexus C2 input: all **185** raw observations sorted chronologically.
The two site folders also contain individual feeds and chronological per-site combined
streams. Raw observations use exactly the original sensor schemas, with no hidden
physical identifiers, geographic truth, associations, or evaluation metadata.

`shared_ground_truth/ground_truth_positions.json`, `ground_truth_associations.json`,
and `scenario_02_expected_behavior.json` are **developer/evaluation only**. Do not
supply them, or scenario configuration files, as normal Nexus C2 replay input.
Expected behavior documents count progression, temporary uncertainty, supporting
EW/CCTV evidence, and periods of disagreement and increasing corroboration.

### Scenario 2 validation

Generation validates before writing and again after reading the saved JSON files.
It checks exact schemas against the archived Scenario 1 feeds, all scheduled counts,
track persistence and associations, physical trajectory continuity and northeast motion,
southwest starts, site coordinates and separation, geometry against shared truth,
confidence variation, classification recovery, positive EW/CCTV evidence, absence of
hidden IDs, combined-stream equality and chronological sorting. It also compares all
saved data and development metadata with the deterministic model. Validation errors
raise an exception with the failed condition. The original SHA-256 manifest checks
Scenario 1 inventory and bytes before and after generation.
