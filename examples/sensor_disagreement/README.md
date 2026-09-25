# Coordinated Demo — sensor disagreement run

This dataset uses the same **Coordinated Demo** scenario as the `sensor_coordinated_100` and
`sensor_coordinated_chance` folders: 2,666 seconds, six hostile contacts, and all 16 radar, EO/IR,
AIS, SAR, fusion, and coastal CCTV sensors.

The tracks and waypoints are unchanged. Only sensor behavior is modified so independent sensors
disagree at seeded, timestamp-specific checks:

- RADAR_3D_01, RADAR_2D_01, and EOIR_01 have lower detection/classification probabilities than
  their paired sensors, producing intermittent misses and `UNKNOWN` classifications.
- RADAR_2D_01 and EOIR_01 refresh every two seconds; CCTV_01–03 refresh every three seconds.
- CCTV_01–03 are less reliable than CCTV_04–06, so the same surface track can appear in one group
  and be absent from the other at a given time.
- HOSTILE_AIR_01 has tighter radar/EOIR target range caps, and HOSTILE_SURFACE_01 has a tighter
  CCTV cap, creating deterministic range-based disagreement as well as random misses.
- SAR remains comparatively reliable, providing a useful comparison for surface-track coverage.
- Reported angular measurements include small errors on a randomized subset of sensor/track/time
  records. For example, one eligible report may be shifted from about 2.0° to 3.0° while the next
  report is untouched; 3D sensors can also receive a slight elevation error.

The disagreement run uses random seed `4242`. Regenerate it from the repository root with:

```powershell
.\.venv\Scripts\python.exe generate_simulated_data.py
```

`scenario.json` contains the complete modified scenario. The remaining JSON files contain one
output array per sensor. Compare records by timestamp, contact geometry, and track ID; a missing
record means the sensor failed its seeded detection check or its configured eligibility limits.
Angular differences are measurement disagreement tied to the generated track and timestamp, not a
change to the underlying contact route. The same seed reproduces the same randomized error events.
