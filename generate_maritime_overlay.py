"""Generate reproducible Navy AIS / coastal radar / GLINT / POI overlay data.

Narrative core for SDTH trojan-mothership disagreement demo (issue #116):
Happy Tug 8 at 6.1 kt vs coastal radar UAS at ~120 kt near the same patch,
plus GLINT SAR deck structure and Jurong / military POIs.
"""

from __future__ import annotations

import json
import math
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

random.seed(42)

ROOT = Path(__file__).parent
OUTPUT_DIR = ROOT / "synthetic_maritime_data"
START_TIME = datetime(2026, 9, 25, 14, 30)
END_TIME = datetime(2026, 9, 25, 15, 0)

# Happy Tug 8 / mothership (Singapore Strait west of Jurong)
MOTHERSHIP = {
    "lat": 1.2148,
    "lon": 103.6648,
    "mmsi": 563098710,
    "vessel_name": "HAPPY TUG 8",
    "sog_knots": 6.1,
    "cog_deg": 48.0,
}

# Hero UAS launched toward Jurong POI-01 (speed disagreement vs AIS)
UAS_TRACK = {
    "track_id": "RDR-NAVY-024",
    "start_lat": 1.2160,
    "start_lon": 103.6660,
    "end_lat": 1.2600,
    "end_lon": 103.7000,
    "velocity_knots": 120.4,
    "altitude_m": 71.0,
    "rcs_m2": 0.035,
}


def save_json(filename: str, data: Any) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / filename).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def timestamp(value: datetime) -> str:
    return value.strftime("%H:%M:%S")


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial great-circle bearing from (lat1,lon1) to (lat2,lon2)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def generate_ais() -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    moment = START_TIME
    while moment <= END_TIME:
        # Slow eastward drift with tiny noise
        minutes = (moment - START_TIME).total_seconds() / 60.0
        lat = MOTHERSHIP["lat"] + minutes * 0.00008 + random.uniform(-0.00002, 0.00002)
        lon = MOTHERSHIP["lon"] + minutes * 0.00012 + random.uniform(-0.00002, 0.00002)
        events.append(
            {
                "sensor_id": "MPA_OCEANS_X_AIS",
                "timestamp": timestamp(moment),
                "mmsi": MOTHERSHIP["mmsi"],
                "vessel_name": MOTHERSHIP["vessel_name"],
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "sog_knots": round(MOTHERSHIP["sog_knots"] + random.uniform(-0.1, 0.1), 2),
                "cog_deg": MOTHERSHIP["cog_deg"],
            }
        )
        moment += timedelta(minutes=5)
    return events


def generate_coastal_radar() -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    # 2-minute updates matching airbase MPSTAR cadence
    moment = START_TIME
    total = (END_TIME - START_TIME).total_seconds()
    while moment <= END_TIME:
        frac = (moment - START_TIME).total_seconds() / total
        lat = lerp(UAS_TRACK["start_lat"], UAS_TRACK["end_lat"], frac)
        lon = lerp(UAS_TRACK["start_lon"], UAS_TRACK["end_lon"], frac)
        events.append(
            {
                "sensor_id": "NAVY_COASTAL_RADAR_01",
                "timestamp": timestamp(moment),
                "track_id": UAS_TRACK["track_id"],
                "lat": round(lat + random.uniform(-0.00005, 0.00005), 6),
                "lon": round(lon + random.uniform(-0.00005, 0.00005), 6),
                "velocity_knots": UAS_TRACK["velocity_knots"],
                "altitude_m": UAS_TRACK["altitude_m"],
                "rcs_m2": UAS_TRACK["rcs_m2"],
                "classification": "UAS",
                "subtype": "fixed-wing",
            }
        )
        moment += timedelta(minutes=2)
    return events


def generate_glint() -> list[dict[str, Any]]:
    return [
        {
            "sensor_id": "GLINT_SAR_PASS_402",
            "timestamp": timestamp(START_TIME),
            "candidate_id": "SAR-DET-0881",
            "center_lat": MOTHERSHIP["lat"] - 0.0008,
            "center_lon": MOTHERSHIP["lon"] - 0.0018,
            "length_m": 78.5,
            "width_m": 14.2,
            "anomaly": "AFT_DECK_METALLIC_STRUCTURE",
            "anomaly_length_m": 12.0,
        }
    ]


def generate_pois() -> list[dict[str, Any]]:
    # Approximate rectangles / points for demo buffers (not survey-grade).
    return [
        {
            "poi_id": "POI-01",
            "name": "Jurong Island Petrochem Complex",
            "kind": "civilian_cni",
            "center_lat": 1.2660,
            "center_lon": 103.7000,
            "buffer_m": 2500.0,
            "offshore_nofire_m": 1200.0,
        },
        {
            "poi_id": "POI-02",
            "name": "Tuas Mega Port",
            "kind": "civilian_cni",
            "center_lat": 1.2400,
            "center_lon": 103.6400,
            "buffer_m": 2000.0,
            "offshore_nofire_m": 1200.0,
        },
        {
            "poi_id": "POI-03",
            "name": "Changi Naval Base",
            "kind": "military",
            "center_lat": 1.3300,
            "center_lon": 104.0200,
            "buffer_m": 1500.0,
            "offshore_nofire_m": 800.0,
        },
        {
            "poi_id": "POI-04",
            "name": "RSAF GBAD Site (synthetic)",
            "kind": "military",
            "center_lat": 1.3300,
            "center_lon": 103.7400,
            "buffer_m": 1000.0,
            "offshore_nofire_m": 800.0,
        },
    ]


def generate_ew_overlay() -> dict[str, list[dict[str, Any]]]:
    """LOB bearings from existing air/army site configs toward mothership."""
    air_cfg = json.loads(
        (ROOT / "scenario_01_consistent" / "synthetic_airbase_data" / "scenario_config.json").read_text()
    )
    army_cfg = json.loads(
        (ROOT / "scenario_01_consistent" / "synthetic_armybase_data" / "scenario_config.json").read_text()
    )
    air_brg = round(
        bearing_deg(air_cfg["latitude"], air_cfg["longitude"], MOTHERSHIP["lat"], MOTHERSHIP["lon"])
        + random.uniform(-0.4, 0.4),
        1,
    )
    army_brg = round(
        bearing_deg(army_cfg["latitude"], army_cfg["longitude"], MOTHERSHIP["lat"], MOTHERSHIP["lon"])
        + random.uniform(-0.4, 0.4),
        1,
    )
    # Demo story bearings (tri_service plan): Air ~135.2, Army ~195.4 when sites are Jurong-facing.
    # With current Changi-east sites the geometric bearings differ; we still emit both geometry
    # and explicit demo story LOBs for the C2 triangulation engine.
    return {
        "air_ew_story": [
            {
                "sensor_id": "RSAF_EW_01",
                "timestamp": "14:30:06",
                "emitter_id": "RF-027",
                "detected": True,
                "bearing_deg": 135.2,
                "freq_mhz": 2437.0,
                "protocol": "FHSS_TACTICAL",
                "classification": "suspected_uas_link",
                "confidence": 0.88,
                "story_lob": True,
            }
        ],
        "army_ew_story": [
            {
                "sensor_id": "ARMY_EW_01",
                "timestamp": "14:30:06",
                "emitter_id": "RF-027",
                "detected": True,
                "bearing_deg": 195.4,
                "remote_id": False,
                "classification": "suspected_uas_link",
                "confidence": 0.86,
                "story_lob": True,
            }
        ],
        "geometry_note": {
            "air_site_bearing_to_mothership_deg": air_brg,
            "army_site_bearing_to_mothership_deg": army_brg,
        },
    }


def main() -> None:
    ais = generate_ais()
    radar = generate_coastal_radar()
    glint = generate_glint()
    pois = generate_pois()
    ew = generate_ew_overlay()

    config = {
        "seed": 42,
        "scenario_start": "14:30:00",
        "scenario_end": "15:00:00",
        "mothership": MOTHERSHIP,
        "uas_track": UAS_TRACK,
        "related_object_id": "UAS-01",
    }

    all_events: list[dict[str, Any]] = []
    for row in ais:
        all_events.append({**row, "channel": "ais"})
    for row in radar:
        all_events.append({**row, "channel": "coastal_radar"})
    for row in glint:
        all_events.append({**row, "channel": "glint_sar"})
    for row in ew["air_ew_story"] + ew["army_ew_story"]:
        all_events.append({**row, "channel": "ew_story"})
    all_events.sort(key=lambda e: e["timestamp"])

    save_json("scenario_config.json", config)
    save_json("ais.json", ais)
    save_json("coastal_radar.json", radar)
    save_json("glint_sar.json", glint)
    save_json("pois.json", pois)
    save_json("ew_story_overlay.json", ew)
    save_json("all_overlay_events.json", all_events)
    print(f"Wrote maritime overlay to {OUTPUT_DIR} ({len(all_events)} events)")


if __name__ == "__main__":
    main()
