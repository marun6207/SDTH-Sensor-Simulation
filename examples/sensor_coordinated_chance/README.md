# Coordinated Demo — probabilistic sensors

This folder contains a second run of the same **Coordinated Demo** scenario and contacts as
`sensor_coordinated_100`, but with realistic probabilistic sensor behavior. It is useful for testing
missed detections, unknown classifications, uneven refresh timing, and fusion logic.

- Scenario duration: 2,666 seconds (44 minutes 26 seconds)
- Random seed: `2026` for deterministic regeneration
- Contacts: three hostile fixed-wing air contacts and three hostile surface vessels
- Sensors: 16 radar, EO/IR, AIS, SAR, fusion, and coastal CCTV sensors
- 3D radar: 95% detection / 85% classification
- 2D radar: 90% detection / 70% classification, 0.4-second refresh
- EO/IR: 90% detection / 75% classification
- CCTV: 80% detection / 60% classification, 3-second refresh

Compared with the 100% dataset, this run can contain missing reports and `UNKNOWN` classifications
at otherwise eligible timestamps. Since the seed is fixed, rerunning the same scenario produces the
same byte-equivalent outputs.

`Coordinated-Demo-chance_scenario.json` is the complete scenario definition. The other JSON files
contain one output array per sensor and use the naming pattern `scenario_sensor-id_sensor-type.json`.
