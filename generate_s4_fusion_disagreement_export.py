#!/usr/bin/env python3
"""Emit Nexus canonical JSONL for auxiliary scenario S4_fusion_disagreement.

Source: scenario_02_conflicting (Arun multi-sensor disagreement bench).
Distinct from Pillar-1 S2_osint_swarm.

  python generate_s4_fusion_disagreement_export.py           # compressed demo subset
  python generate_s4_fusion_disagreement_export.py --full    # all raw observations
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent
SRC = ROOT / "scenario_02_conflicting"
EXPORT = ROOT / "exports"
OUT = EXPORT / "s4_fusion_disagreement_scenario.jsonl"

WALL_START = datetime(2026, 9, 25, 14, 30, 0)
WALL_END = datetime(2026, 9, 25, 15, 0, 0)
DEMO_DURATION_S = 184.0
NOMINAL_ALT_M = 120.0

# Key wall-clock stamps covering early / mid / late disagreement beats.
KEY_TIMESTAMPS = frozenset(
    {
        "14:30:00",
        "14:30:01",
        "14:30:02",
        "14:30:05",
        "14:30:07",
        "14:30:11",
        "14:42:01",
        "14:42:02",
        "14:42:11",
        "14:44:17",
        "14:45:01",
        "14:45:02",
        "14:45:05",
        "14:45:07",
        "14:45:11",
        "14:48:00",
        "14:48:01",
        "14:48:11",
        "14:51:01",
        "14:51:11",
    }
)

SENSOR_MAP: dict[str, tuple[str, str, str]] = {
    # sensor_id -> (service, source, site_key)
    "MPSTAR_AIRBASE_02": ("AIR_FORCE", "AIR_RADAR", "AIRBASE_02"),
    "EOIR_AIRBASE_02": ("AIR_FORCE", "AIR_EOIR", "AIRBASE_02"),
    "AIRBASE_EW_02": ("AIR_FORCE", "AIR_EW", "AIRBASE_02"),
    "EOIR_ARMYBASE_02": ("ARMY", "ARMY_EOIR", "ARMY_BASE_02"),
    "CCTV_ARMYBASE_02": ("ARMY", "ARMY_CCTV", "ARMY_BASE_02"),
    "ARMYBASE_EW_02": ("ARMY", "ARMY_EW", "ARMY_BASE_02"),
    "MPA_OCEANS_X_AIS": ("NAVY", "NAVY_AIS", "NAVY_BASE_02"),
    "NAVY_COASTAL_RADAR_02": ("NAVY", "NAVY_COASTAL_RADAR", "NAVY_BASE_02"),
    "GLINT_SAR_PASS_SIM_02": ("SPACE", "SPACE_SAR", "NAVY_BASE_02"),
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_hms(value: str) -> datetime:
    h, m, s = value.split(":")
    return datetime(2026, 9, 25, int(h), int(m), int(s))


def time_s(ts: str) -> float:
    moment = parse_hms(ts)
    wall = (WALL_END - WALL_START).total_seconds()
    elapsed = (moment - WALL_START).total_seconds()
    return round(max(0.0, min(DEMO_DURATION_S, elapsed / wall * DEMO_DURATION_S)), 1)


def eoir_range_km(elevation_deg: float | None) -> float:
    elev = max(float(elevation_deg or 0.5), 0.05)
    return round(NOMINAL_ALT_M / math.tan(math.radians(elev)) / 1000.0, 4)


def convert_event(ev: dict[str, Any], sites: dict[str, Any]) -> dict[str, Any] | None:
    sensor_id = str(ev.get("sensor_id", ""))
    mapped = SENSOR_MAP.get(sensor_id)
    if mapped is None:
        return None
    service, source, site_key = mapped
    site = sites[site_key]
    ts = str(ev["timestamp"])
    base: dict[str, Any] = {
        "time_s": time_s(ts),
        "service": service,
        "source": source,
        "sensor_id": sensor_id,
        "timestamp": ts,
        "site_id": site_key,
        "site_lat": site["latitude"],
        "site_lon": site["longitude"],
    }

    if source == "NAVY_AIS":
        base.update(
            mmsi=ev["mmsi"],
            vessel_name=ev["vessel_name"],
            lat=ev["lat"],
            lon=ev["lon"],
            sog_knots=ev["sog_knots"],
            cog_deg=ev["cog_deg"],
        )
        return base

    if source == "NAVY_COASTAL_RADAR":
        base.update(
            track_id=ev["track_id"],
            lat=ev["lat"],
            lon=ev["lon"],
            velocity_knots=ev["velocity_knots"],
            altitude_m=ev["altitude_m"],
            rcs_m2=ev["rcs_m2"],
            classification=ev["classification"],
            subtype=ev.get("subtype"),
        )
        return base

    if source == "SPACE_SAR":
        base.update(
            candidate_id=ev["candidate_id"],
            center_lat=ev["center_lat"],
            center_lon=ev["center_lon"],
            length_m=ev["length_m"],
            width_m=ev["width_m"],
            anomaly=ev["anomaly"],
            anomaly_length_m=ev.get("anomaly_length_m"),
        )
        return base

    if source == "ARMY_CCTV":
        base.update(
            camera_id=ev.get("camera_id"),
            status="BOUNDING_BOX_LOCKED" if ev.get("detected") else "NO_DETECT",
            classification=ev.get("classification"),
            confidence=ev.get("confidence"),
            image=ev.get("image"),
            detected=ev.get("detected"),
        )
        return base

    if source in {"AIR_EW", "ARMY_EW"}:
        base.update(
            emitter_id=ev.get("emitter_id"),
            bearing_deg=ev.get("bearing_deg"),
            classification=ev.get("classification"),
            confidence=ev.get("confidence", 0.0),
            detected=ev.get("detected", False),
            rf_negative=True,
        )
        return base

    if source == "AIR_RADAR":
        base.update(
            azimuth_deg=ev["azimuth_deg"],
            range_km=ev["range_km"],
            track_id=ev["track_id"],
            classification=ev["classification"],
            subtype=ev.get("subtype"),
        )
        return base

    if source in {"AIR_EOIR", "ARMY_EOIR"}:
        base.update(
            azimuth_deg=ev["azimuth_deg"],
            range_km=eoir_range_km(ev.get("elevation_deg")),
            track_id=ev["track_id"],
            elevation_deg=ev.get("elevation_deg"),
            classification=ev["classification"],
            subtype=ev.get("subtype"),
            confidence=ev.get("confidence"),
            image=ev.get("image"),
        )
        return base

    return None


def build_rows(*, full: bool) -> list[dict[str, Any]]:
    cfg = load_json(SRC / "scenario_config.json")
    sites = cfg["sites"]
    raw = load_json(SRC / "scenario_02_all_sensor_events.json")
    rows: list[dict[str, Any]] = []
    for ev in raw:
        if not full and str(ev.get("timestamp")) not in KEY_TIMESTAMPS:
            continue
        converted = convert_event(ev, sites)
        if converted is not None:
            rows.append(converted)
    rows.sort(key=lambda r: (r["time_s"], r["service"], r["source"], r.get("track_id", "")))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--full",
        action="store_true",
        help="Export every raw observation (default: compressed key-timestamp subset).",
    )
    args = parser.parse_args()

    events_path = SRC / "scenario_02_all_sensor_events.json"
    if not events_path.is_file():
        raise SystemExit(f"missing {events_path}; regenerate scenario_02 first")

    rows = build_rows(full=args.full)
    EXPORT.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")
    mode = "full" if args.full else "compressed"
    print(f"Wrote {len(rows)} events ({mode}) → {OUT}")


if __name__ == "__main__":
    main()
