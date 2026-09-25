# Hazard Forecast Contract v1

This package is a deterministic defensive screening tool. It forecasts movement corridors and identifies
civilian infrastructure geometrically exposed by those corridors. It does not infer intent, rank strategic
value, model weapons, or include military facilities.

## Track input

The input is one non-empty JSON array in authoritative chronological order. Each object has exactly these
fields:

```json
{
  "timestamp": "2026-09-25T12:00:00Z",
  "lat": 1.3001,
  "long": 103.8012,
  "altitude": 1200.0,
  "speed": 92.5,
  "type": "caller-owned-token"
}
```

- `timestamp` is required RFC 3339 UTC and must end in `Z`. Timestamps must strictly increase.
- `lat` and `long` are required WGS84 decimal degrees.
- `altitude` is required metres above mean sea level and must be at least `-500`.
- `speed` is optional ground speed in metres per second. Omission and `null` are equivalent.
- `type` is an optional opaque token. Omission and `null` are equivalent. A non-null value remains active
  until a later non-null value replaces it.
- Unknown fields, numeric strings, booleans used as numbers, infinities, and NaN values are rejected.

The first altitude determines the default domain: greater than 5 m is `air`; otherwise it is `surface`.
Use `--domain` when that rule is not appropriate.

## Type mapping

The optional `--type-map` file is a JSON object mapping opaque input tokens to one of:

```text
air_slow
air_rotary
air_fixed_wing
air_high_speed
surface_maritime_slow
surface_maritime_fast
unknown_air
unknown_surface
```

Only kinematic limits are associated with these profiles. Unmapped tokens use the conservative unknown
profile for the inferred domain and produce an `unmapped_type` warning.

## OSM snapshot specification

Pass either a bounding box:

```json
{"snapshot_id":"region-2026-09-25","bbox":[1.1,103.5,1.6,104.2]}
```

or one valid GeoJSON Polygon under `polygon`. Optional `endpoint` and `user_agent` fields override the
Overpass endpoint and identifying user agent. Refresh writes `raw-overpass.json`, `features.geojson`, and
`manifest.json`. Replay verifies the two content hashes and never refreshes the snapshot.

## Replay output

`snapshots.jsonl` contains one `hazard-forecast-snapshot/v1` object per observation. Each object records:

- Active domain, type token, generic profile, and mapping status.
- Motion inputs, derived values, clamps, residuals, and model selection.
- Nominal centerline, likely corridor, possible corridor, and forecast checkpoints as GeoJSON.
- Time-ordered infrastructure exposures with danger geometry, public OSM identity/tags, and explanation.
- Structured warnings such as `domain_conflict`, `unmapped_type`, `insufficient_heading_data`, and
  `speed_disagreement`.

`result.json` contains the full replay as `hazard-replay-result/v1`. GeoJSON files split out observations,
centerlines, corridors, exposed infrastructure, and danger areas. `manifest.json` contains SHA-256 hashes
of all generated artifacts. `map.html` renders those artifacts without recalculating the forecast.

Urgency is geometric and time-based only: `immediate` at 120 seconds or less, `near_term` at 300 seconds or
less, and `monitor` for the remainder of the configured horizon. Category never changes urgency.
