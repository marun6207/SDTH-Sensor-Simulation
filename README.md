# Synthetic C2 Sensor Dataset

This project generates a reproducible, fictional multi-sensor dataset for a
Command-and-Control (C2) and Common Operating Picture (COP) demonstration.
The data is suitable for testing sensor ingestion, data unification, track
correlation, sensor fusion, and plotting on a Singapore map.

This is a synthetic hackathon scenario. It is not a model of real military
sensor performance, communications, weapon performance, or an actual attack
trajectory. The geographic coordinates are synthetic WGS84 coordinates chosen
only to make the tracks coherent on a map.

## Scenario 1

Scenario 1 is named **Consistent Multi-Sensor Detection**. Five synthetic
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
is stored in [synthetic_airbase_data/scenario_config.json](synthetic_airbase_data/scenario_config.json).

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
the result in [synthetic_armybase_data/scenario_config.json](synthetic_armybase_data/scenario_config.json).

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
synthetic_airbase_data/
	scenario_config.json
	mpstar.json
	eoir.json
	ew.json
	ground_truth_positions.json
	ground_truth_associations.json
	all_sensor_events.json

synthetic_armybase_data/
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

## Running the Generators

Open the project folder in VS Code and open **Terminal > New Terminal**.
Run the original Airbase generator with:

```text
python generate_airbase_scenario.py
```

Run the Army Base generator with:

```text
python generate_armybase_scenario.py
```

The Army generator expects the existing Airbase configuration and ground truth
to exist. It writes only to `synthetic_armybase_data/` and checks that the
existing Airbase JSON files were not modified.

Both generators use fixed random seeds so repeated runs produce reproducible
measurements. No external Python packages are required.

## Validation

The generators validate exact raw schemas and fail if fields are missing,
renamed, or added. They also check confidence ranges, timestamp boundaries,
track persistence, chronological event ordering, ground-truth coordinate
bounds, and the separation between raw observations and development-only
ground truth.

## Web application

The `web-app` branch also contains a Python Dash tactical scenario simulator. It is intended for
synthetic training and demonstrations; it does not connect to live sensors.

### Setup and launch

From the repository root, create and activate a virtual environment, install the dependencies, and
start the server:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

Open <http://127.0.0.1:8050/> in a browser. The map uses OpenStreetMap tiles, so map tiles require
internet access.

### Create and run a scenario

1. Choose a sensor, hostile contact, or civilian air/vessel contact from **Place entity**, then click the map to place it.
2. Select an entity in **Entity inspector** to edit coordinates, sensor limits, refresh rate,
   probabilities, orientation, and enabled state.
3. Select a hostile contact and choose **Add waypoint on map**. Click successive map positions to
   build its route. Arrival times are derived from the previous waypoint's speed; air contacts
   support altitude and hold time, while surface contacts remain at zero altitude.
4. For hostile contacts, set **EMCON** (active, passive, or silent) and per-sensor detectable
   range caps when needed.
5. Use the timeline controls to play, pause, restart, scrub, and change simulation speed.
6. Click **Generate outputs**. The seeded simulation produces one JSON stream per sensor. CCTV
   reports include track, bearing, range, classification, confidence, and deterministic image
   references when eligible targets are detected.
7. Download an individual sensor file or click **Download all JSON** for separate files.

Use **Export scenario** to save complete scenario JSON and **Import scenario** to restore it.
Saved scenarios persist in the browser; generated outputs remain in memory.

### Test the application

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

For browser acceptance tests, install the development dependencies and Chromium first:

```powershell
python -m pip install -r requirements-dev.txt
$env:PLAYWRIGHT_BROWSERS_PATH = "$PWD\.venv\pw-browsers"
python -m playwright install chromium
python -m pytest tests/e2e -q
```

### Create sensor disagreement data

Use `generate_simulated_data.py` to regenerate the checked-in example under
[`examples/sensor_disagreement`](examples/sensor_disagreement). It starts from the demonstration
scenario and deliberately changes sensor behavior while keeping the target track the same:

```powershell
.\.venv\Scripts\python.exe generate_simulated_data.py
```

To create your own disagreement, copy `build_disagreement_scenario()` and adjust sensor or contact
settings before calling `generate_outputs(scenario)`. Useful patterns include:

- Set one sensor's `classification_probability` to `0` while another sensor retains a non-zero
  value. Both can detect the same target, but one emits `UNKNOWN`.
- Give one sensor a smaller `detection_range_km`, `field_of_view_deg`, or target
  `detectable_range_km` cap. It will miss a contact that another sensor reports.
- Add an `EmitterEvent(enabled=False)` to create an EW outage, or an `AisEvent(enabled=False)` to
  create an AIS outage while SAR or another sensor continues reporting.
- Use different `refresh_rate_s` values to create timestamp gaps, then compare records by
  `timestamp` and `track_id`.

Keep `random_seed` fixed when comparing runs. The simulator uses that seed for detection and
classification checks, so the same scenario and seed produce identical JSON output.

## Civil-infrastructure impact prediction

The `hazard_forecast` package performs deterministic, defensive screening of a live target history
against an immutable OpenStreetMap snapshot. It interpolates observations at a fixed cadence,
projects a straight likely corridor, builds a compact radial possible area without turn hypotheses,
and reports affected civil infrastructure. The generated MapLibre map uses red for affected
infrastructure, yellow for the likely corridor, and orange for the possible area.

Create the example snapshot:

```powershell
.\.venv\Scripts\python.exe -m hazard_forecast osm-refresh snapshot-spec.json `
  --output osm-snapshot
```

Replay the example at ten-second observation and prediction intervals:

```powershell
.\.venv\Scripts\python.exe -m hazard_forecast replay trajectory_target_input.json `
  --snapshot osm-snapshot `
  --output forecast-output `
  --type-map trajectory_target_type_map.json `
  --observation-step-s 10 `
  --horizon-s 120 `
  --step-s 10 `
  --likely-only `
  --track-id live-target-001
```

For cumulative live input, replace `replay` with `assess` and write to a JSON file with `--output`.
See the [`hazard_forecast` README](hazard_forecast/README.md) for the system architecture, classification checks, and military-site filtering. The full input, output, and safety contract is documented in [`hazard_forecast/CONTRACT.md`](hazard_forecast/CONTRACT.md).
