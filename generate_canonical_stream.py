"""Merge air / army / maritime into a time-compressed canonical JSONL export.

Output:
  exports/s1_trojan_scenario.jsonl
  exports/site_origins.json
  exports/pois.json
"""

from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent
AIR = ROOT / "scenario_01_consistent" / "synthetic_airbase_data"
ARMY = ROOT / "scenario_01_consistent" / "synthetic_armybase_data"
MAR = ROOT / "synthetic_maritime_data"
EXPORT = ROOT / "exports"

# Demo pitch window: map 30 min wall clock onto ~184 s narrative.
WALL_START = datetime(2026, 9, 25, 14, 30, 0)
WALL_END = datetime(2026, 9, 25, 15, 0, 0)
DEMO_DURATION_S = 184.0


def parse_hms(value: str) -> datetime:
    h, m, s = value.split(":")
    return datetime(2026, 9, 25, int(h), int(m), int(s))


def time_s(ts: str) -> float:
    moment = parse_hms(ts)
    wall = (WALL_END - WALL_START).total_seconds()
    elapsed = (moment - WALL_START).total_seconds()
    return round(max(0.0, min(DEMO_DURATION_S, elapsed / wall * DEMO_DURATION_S)), 1)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def polar_to_row(
    *,
    service: str,
    source: str,
    sensor_id: str,
    ts: str,
    site: dict[str, Any],
    azimuth_deg: float | None = None,
    range_km: float | None = None,
    bearing_deg_value: float | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "time_s": time_s(ts),
        "service": service,
        "source": source,
        "sensor_id": sensor_id,
        "timestamp": ts,
        "site_id": site["site_id"],
        "site_lat": site["latitude"],
        "site_lon": site["longitude"],
    }
    if azimuth_deg is not None:
        row["azimuth_deg"] = azimuth_deg
    if range_km is not None:
        row["range_km"] = range_km
    if bearing_deg_value is not None:
        row["bearing_deg"] = bearing_deg_value
    if extra:
        row.update(extra)
    return row


def main() -> None:
    if not MAR.exists():
        raise SystemExit("Run generate_maritime_overlay.py first")

    air_cfg = load_json(AIR / "scenario_config.json")
    army_cfg = load_json(ARMY / "scenario_config.json")
    maritime_cfg = load_json(MAR / "scenario_config.json")
    pois = load_json(MAR / "pois.json")
    ais = load_json(MAR / "ais.json")
    radar = load_json(MAR / "coastal_radar.json")
    glint = load_json(MAR / "glint_sar.json")
    ew_story = load_json(MAR / "ew_story_overlay.json")

    rows: list[dict[str, Any]] = []

    # --- Navy AIS ---
    for ev in ais:
        rows.append(
            {
                "time_s": time_s(ev["timestamp"]),
                "service": "NAVY",
                "source": "NAVY_AIS",
                "sensor_id": ev["sensor_id"],
                "mmsi": ev["mmsi"],
                "vessel_name": ev["vessel_name"],
                "lat": ev["lat"],
                "lon": ev["lon"],
                "sog_knots": ev["sog_knots"],
                "cog_deg": ev["cog_deg"],
                "timestamp": ev["timestamp"],
            }
        )

    # --- Navy coastal radar (speed disagreement hero) ---
    for ev in radar:
        rows.append(
            {
                "time_s": time_s(ev["timestamp"]),
                "service": "NAVY",
                "source": "NAVY_COASTAL_RADAR",
                "sensor_id": ev["sensor_id"],
                "track_id": ev["track_id"],
                "lat": ev["lat"],
                "lon": ev["lon"],
                "velocity_knots": ev["velocity_knots"],
                "altitude_m": ev["altitude_m"],
                "rcs_m2": ev["rcs_m2"],
                "classification": ev["classification"],
                "subtype": ev.get("subtype"),
                "timestamp": ev["timestamp"],
            }
        )

    # --- Space GLINT ---
    for ev in glint:
        rows.append(
            {
                "time_s": time_s(ev["timestamp"]),
                "service": "SPACE",
                "source": "SPACE_SAR",
                "sensor_id": ev["sensor_id"],
                "candidate_id": ev["candidate_id"],
                "center_lat": ev["center_lat"],
                "center_lon": ev["center_lon"],
                "length_m": ev["length_m"],
                "width_m": ev["width_m"],
                "anomaly": ev["anomaly"],
                "anomaly_length_m": ev.get("anomaly_length_m"),
                "timestamp": ev["timestamp"],
            }
        )

    # --- Air MPSTAR / EOIR / EW (polar, existing) ---
    for ev in load_json(AIR / "mpstar.json"):
        rows.append(
            polar_to_row(
                service="AIR_FORCE",
                source="AIR_RADAR",
                sensor_id=ev["sensor_id"],
                ts=ev["timestamp"],
                site=air_cfg,
                azimuth_deg=ev["azimuth_deg"],
                range_km=ev["range_km"],
                extra={
                    "track_id": ev["track_id"],
                    "classification": ev["classification"],
                    "subtype": ev.get("subtype"),
                },
            )
        )
    for ev in load_json(AIR / "eoir.json"):
        rows.append(
            polar_to_row(
                service="AIR_FORCE",
                source="AIR_EOIR",
                sensor_id=ev["sensor_id"],
                ts=ev["timestamp"],
                site=air_cfg,
                azimuth_deg=ev["azimuth_deg"],
                extra={
                    "track_id": ev["track_id"],
                    "elevation_deg": ev.get("elevation_deg"),
                    "classification": ev["classification"],
                    "confidence": ev.get("confidence"),
                    "image": ev.get("image"),
                },
            )
        )
    for ev in load_json(AIR / "ew.json"):
        rows.append(
            polar_to_row(
                service="AIR_FORCE",
                source="AIR_EW",
                sensor_id=ev["sensor_id"],
                ts=ev["timestamp"],
                site=air_cfg,
                bearing_deg_value=ev["bearing_deg"],
                extra={
                    "emitter_id": ev.get("emitter_id"),
                    "classification": ev.get("classification"),
                    "confidence": ev.get("confidence"),
                },
            )
        )

    # --- Army EOIR / CCTV / EW ---
    for ev in load_json(ARMY / "eoir.json"):
        rows.append(
            polar_to_row(
                service="ARMY",
                source="ARMY_EOIR",
                sensor_id=ev["sensor_id"],
                ts=ev["timestamp"],
                site=army_cfg,
                azimuth_deg=ev["azimuth_deg"],
                extra={
                    "track_id": ev["track_id"],
                    "elevation_deg": ev.get("elevation_deg"),
                    "classification": ev["classification"],
                    "confidence": ev.get("confidence"),
                    "image": ev.get("image"),
                },
            )
        )
    for ev in load_json(ARMY / "cctv.json"):
        rows.append(
            {
                "time_s": time_s(ev["timestamp"]),
                "service": "ARMY",
                "source": "ARMY_CCTV",
                "sensor_id": ev["sensor_id"],
                "camera_id": ev.get("camera_id"),
                "status": "BOUNDING_BOX_LOCKED" if ev.get("detected") else "NO_DETECT",
                "classification": ev.get("classification"),
                "confidence": ev.get("confidence"),
                "image": ev.get("image"),
                "site_id": army_cfg["site_id"],
                "site_lat": army_cfg["latitude"],
                "site_lon": army_cfg["longitude"],
                "timestamp": ev["timestamp"],
            }
        )
    for ev in load_json(ARMY / "ew.json"):
        rows.append(
            polar_to_row(
                service="ARMY",
                source="ARMY_EW",
                sensor_id=ev["sensor_id"],
                ts=ev["timestamp"],
                site=army_cfg,
                bearing_deg_value=ev["bearing_deg"],
                extra={
                    "emitter_id": ev.get("emitter_id"),
                    "classification": ev.get("classification"),
                    "confidence": ev.get("confidence"),
                },
            )
        )

    # --- Story LOB overlay (Air ∩ Army toward mothership narrative) ---
    for ev in ew_story["air_ew_story"]:
        rows.append(
            polar_to_row(
                service="AIR_FORCE",
                source="AIR_EW",
                sensor_id=ev["sensor_id"],
                ts=ev["timestamp"],
                site=air_cfg,
                bearing_deg_value=ev["bearing_deg"],
                extra={
                    "emitter_id": ev.get("emitter_id"),
                    "freq_mhz": ev.get("freq_mhz"),
                    "protocol": ev.get("protocol"),
                    "classification": ev.get("classification"),
                    "confidence": ev.get("confidence"),
                    "story_lob": True,
                },
            )
        )
    for ev in ew_story["army_ew_story"]:
        rows.append(
            polar_to_row(
                service="ARMY",
                source="ARMY_EW",
                sensor_id=ev["sensor_id"],
                ts=ev["timestamp"],
                site=army_cfg,
                bearing_deg_value=ev["bearing_deg"],
                extra={
                    "emitter_id": ev.get("emitter_id"),
                    "remote_id": ev.get("remote_id"),
                    "classification": ev.get("classification"),
                    "confidence": ev.get("confidence"),
                    "story_lob": True,
                },
            )
        )

    rows.sort(key=lambda r: (r["time_s"], r["service"], r["source"]))

    EXPORT.mkdir(parents=True, exist_ok=True)
    out_jsonl = EXPORT / "s1_trojan_scenario.jsonl"
    with out_jsonl.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")

    site_origins = {
        "AIRBASE_01": {
            "latitude": air_cfg["latitude"],
            "longitude": air_cfg["longitude"],
        },
        "ARMY_BASE_01": {
            "latitude": army_cfg["latitude"],
            "longitude": army_cfg["longitude"],
        },
        "mothership": maritime_cfg["mothership"],
        "demo_duration_s": DEMO_DURATION_S,
    }
    (EXPORT / "site_origins.json").write_text(json.dumps(site_origins, indent=2) + "\n")
    (EXPORT / "pois.json").write_text(json.dumps(pois, indent=2) + "\n")
    print(f"Wrote {len(rows)} events → {out_jsonl}")


if __name__ == "__main__":
    main()
