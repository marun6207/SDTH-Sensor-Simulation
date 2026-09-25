# Sensor disagreement example

This directory contains deterministic outputs from `generate_simulated_data.py`. The scenario is
synthetic and intentionally creates disagreements that a fusion or operator workflow should surface:

- `GIRAFFE_AIRBASE_01` classifies the airborne contact as `UAS` while `EOIR_AIRBASE_01` detects it
  but reports `UNKNOWN` because its classification probability is set to zero.
- `CCTV_COASTAL_01` detects the vessel but reports `UNKNOWN` rather than a vessel class.
- AIS changes identity and then goes offline according to the vessel's AIS events, while
  `GLINT_SAR_01` continues producing surface detections.
- `ARMY_EW_01` stops reporting when the airborne contact's emitter event disables its transmitter.

Regenerate the files from the repository root with:

```powershell
.\.venv\Scripts\python.exe generate_simulated_data.py
```

The fixed scenario seed (`17`) makes repeated runs byte-equivalent. Compare records with matching
timestamps and track IDs to identify missing reports, `UNKNOWN` classifications, AIS identity
changes, and emitter outages.
