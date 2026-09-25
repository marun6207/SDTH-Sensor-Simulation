# Joint Sensor Simulator

A Python-first Dash application for authoring synthetic air and maritime threat scenarios, previewing sensor coverage and contact movement, and generating deterministic sensor JSON files.

## Setup

PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

Open <http://127.0.0.1:8050>. The OpenStreetMap basemap requires internet access.

## Workflow

1. Select a sensor or hostile contact in the left palette and click the map.
2. Select a hostile in the inspector and choose **Add waypoint on map**. Each map click extends its route and derives arrival time from geodesic distance and the previous waypoint's speed.
3. Edit the validated JSON to change range, FOV, refresh rate, waypoint altitude/speed/hold, emitter events, or AIS events.
   For hostile contacts, the dedicated target panel also provides Active, Passive, and Silent EMCON modes plus per-sensor-type detectability range caps.
4. Use the lower timeline to preview movement and geometric detection links.
5. Select **Generate outputs** to run the seeded batch simulation.
6. Download one JSON array per sensor, or use **Download all JSON** for separate files.

Scenario definitions are versioned and stored in browser local storage. **Export scenario** and **Import scenario** transfer full authoring data. Generated messages stay in memory.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest
```

For the browser acceptance test, install the development dependencies and the
project-local Chromium runtime first:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
$env:PLAYWRIGHT_BROWSERS_PATH = "$PWD\.venv\pw-browsers"
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe -m pytest tests
```

The simulator is for synthetic training and demonstration; it does not connect to live sensors.

## Civil-infrastructure danger forecasting

The `hazard_forecast` package is a separate defensive screening module. It replays one JSON array of
timestamped positions, creates deterministic likely/possible movement corridors, and reports civilian
infrastructure exposed by those corridors. It does not model weapons, targets, or strategic value.

Install the project to expose the `hazard-forecast` command:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
```

Validate a track, create a bounded OSM snapshot, and replay it:

```powershell
hazard-forecast validate track.json
hazard-forecast osm-refresh snapshot-spec.json --output osm-snapshot
hazard-forecast replay track.json --snapshot osm-snapshot --output forecast-output
```

`snapshot-spec.json` contains either `{"bbox": [south, west, north, east]}` or a GeoJSON Polygon under
`polygon`. Snapshot refresh is the only analytical command that accesses the network; replay uses the
immutable snapshot and writes JSONL, consolidated JSON, GeoJSON, an attributed Leaflet map, and a hash
manifest. Use `--type-map mapping.json` to map caller-owned opaque type tokens to the documented generic
mobility profiles.

The complete field and artifact definitions are in
[`hazard_forecast/CONTRACT.md`](hazard_forecast/CONTRACT.md).
