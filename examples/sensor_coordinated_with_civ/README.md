# Coordinated Demo with civilian traffic

This is an extended Coordinated Demo scenario containing both hostile and civilian traffic. It is
synthetic training data for checking mixed-track display, sensor eligibility, AIS ingestion, and
classification workflows.

- Duration: 2,666 seconds (44 minutes 26 seconds)
- Random seed: `2026`
- Sensors: 16 radar, EO/IR, AIS, SAR, fusion, and coastal CCTV sensors
- Contacts: 6 hostile contacts (3 fixed-wing air, 3 surface vessels), 7 civilian vessels, and 1
  civilian fixed-wing aircraft
- Civilian vessels have active AIS transmitters with unique synthetic MMSIs
- Civilian air traffic has no AIS transmitter and is handled by radar/EO/IR sensors

The scenario definition is `Coordinated-Demo-With-Civ_scenario.json`. The remaining JSON files are
one output array per sensor. The three AIS files contain civilian-vessel reports while their
transmitters are active. The fusion file is empty because this scenario does not define manual AIS
to SAR fusion mappings.

To use the scenario in the web app, choose **Import scenario** and select the scenario JSON. To
regenerate the outputs, load the scenario with `Scenario.model_validate()` and call
`generate_outputs(scenario)` from the repository's Python environment.
