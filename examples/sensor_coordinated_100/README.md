# Coordinated Demo — deterministic 100% sensors

This folder contains a generated run of the **Coordinated Demo** scenario. It is a synthetic,
repeatable multi-sensor dataset for checking schemas, track alignment, and downstream ingestion.

- Scenario duration: 2,666 seconds (44 minutes 26 seconds)
- Random seed: `2026`
- Contacts: three hostile fixed-wing air contacts and three hostile surface vessels
- Sensors: 16 radar, EO/IR, AIS, SAR, fusion, and coastal CCTV sensors
- Detection and classification probabilities: `1.0` for every sensor
- Refresh rate: `1` second for every sensor

Because every eligible check succeeds, this is the useful baseline for validating expected coverage
and comparing file schemas without random misses. A zero-message file can still be valid when a
contact is outside that sensor's domain, range, FOV, altitude limits, or transmission window.

`Coordinated-Demo_scenario.json` is the complete scenario definition. The other JSON files contain
one output array per sensor and use the naming pattern `scenario_sensor-id_sensor-type.json`.
