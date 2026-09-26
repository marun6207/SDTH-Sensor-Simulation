#!/usr/bin/env python3
"""Emit Nexus-shape JSONL for Pillar 1: S2_osint_swarm.

Source of truth for synthetic airborne passenger OSINT / clutter radar /
acoustic / RF-silent events. Distinct from legacy scenario_02_conflicting
(5-UAS fusion bench).

Timestamps use relative ``t_offset_sec`` so Nexus re-stamps against demo clock.

Regenerate::

  python generate_s2_osint_swarm_export.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent
EXPORT = ROOT / "exports"

_CUE_LAT, _CUE_LON = 1.3510, 103.9900
_RADAR_LAT, _RADAR_LON = 1.3618, 103.9900

_INTEL_TEXT = (
    "In-flight passenger OSINT (commercial flight bound for Japan): smartphone video/photos "
    "of ~50 unknown delta-wing drones / Shahed-class airframes flying low below the aircraft. "
    "No coordinates or destination stated. Estimated vector bearing 248° at ~105 kt. "
    "#ufo #drones"
)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(row, ensure_ascii=False, separators=(",", ":")) for row in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {path} ({len(rows)} rows)")


def s2_osint_swarm_rows() -> list[dict[str, Any]]:
    return [
        {
            "source_id": "CIVILIAN_SOCIAL_RECON",
            "entity_id": "OSINT-SWARM-CLAIM",
            "latitude": _CUE_LAT,
            "longitude": _CUE_LON,
            "speed_kt": 0.0,
            "confidence": 0.55,
            "t_offset_sec": -45,
            "modality": "social",
            "note": "airborne_passenger_swarm_sighting",
            "intel_text": _INTEL_TEXT,
            "objective": "unknown_ingress",
            "vendor_track": "OSINT-SWARM-CLAIM",
        },
        {
            "source_id": "ADS_B_SECTOR_EMPTY",
            "entity_id": "ADSB-NULL-SECTOR",
            "latitude": _CUE_LAT,
            "longitude": _CUE_LON,
            "speed_kt": 0.0,
            "confidence": 0.4,
            "t_offset_sec": -20,
            "modality": "adsb",
            "note": "no_cooperative_squawk",
            "vendor_track": "ADSB-NULL",
            "empty_sector": True,
        },
        {
            "source_id": "EO_SKY_WATCH",
            "entity_id": "EO-DELTA-WING-BRAVO",
            "latitude": _CUE_LAT,
            "longitude": _CUE_LON,
            "speed_kt": 100.0,
            "heading_deg": 248.0,
            "confidence": 0.42,
            "t_offset_sec": -8,
            "modality": "optical",
            "note": "delta_wing_thermal_silhouette",
            "altitude_m_est": 160,
            "blur": True,
            "vendor_track": "EO-DELTA-WING-BRAVO",
        },
        {
            "source_id": "GAP_FILLER_RADAR",
            "entity_id": "RADAR-AIR-551",
            "latitude": _RADAR_LAT,
            "longitude": _RADAR_LON,
            "speed_kt": 105.0,
            "heading_deg": 248.0,
            "confidence": 0.84,
            "t_offset_sec": 0,
            "modality": "radar",
            "note": "intermittent_low_rcs_clutter_contacts",
            "altitude_m_est": 200,
            "contact_count": 4,
            "vendor_track": "RADAR-AIR-551",
        },
        {
            "source_id": "COASTAL_ACOUSTIC_ARRAY",
            "entity_id": "ACOUSTIC-SHADED-HARMONIC",
            "latitude": (_CUE_LAT + _RADAR_LAT) / 2,
            "longitude": _CUE_LON,
            "speed_kt": 0.0,
            "confidence": 0.72,
            "t_offset_sec": -6,
            "modality": "acoustic",
            "note": "two_stroke_moped_harmonic_shahed",
            "engine_signature": "2stroke_moped",
            "vendor_track": "ACOUSTIC-SHADED-HARMONIC",
        },
        {
            "source_id": "RF_PASSIVE_ARRAY",
            "entity_id": "RF-SILENT-SCAN",
            "latitude": (_CUE_LAT + _RADAR_LAT) / 2,
            "longitude": _CUE_LON,
            "speed_kt": 0.0,
            "confidence": 0.7,
            "t_offset_sec": -2,
            "modality": "rf",
            "note": "no_emitter_detected_autonomous_gps_ins",
            "rf_silent": True,
            "control_mode": "GPS_INS_WAYPOINT",
            "vendor_track": "RF-SILENT-SCAN",
        },
    ]


def main() -> None:
    _write_jsonl(EXPORT / "s2_osint_swarm_scenario.jsonl", s2_osint_swarm_rows())


if __name__ == "__main__":
    main()
