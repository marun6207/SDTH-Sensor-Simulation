from __future__ import annotations

import json
from pathlib import Path

from .models import MobilityProfile


PROFILE_CATALOG_VERSION = "civil-mobility-v1"


def _profile(name: str, domain: str, speeds: tuple[float, float], acceleration: float,
             turn: float, climb: float = 0, descent: float = 0) -> MobilityProfile:
    return MobilityProfile(name=name, domain=domain, min_speed_mps=speeds[0], max_speed_mps=speeds[1],
                           max_acceleration_mps2=acceleration, max_turn_rate_deg_s=turn,
                           max_climb_rate_mps=climb, max_descent_rate_mps=descent)


DEFAULT_PROFILES = {
    "air_slow": _profile("air_slow", "air", (0, 80), 8, 12, 15, 15),
    "air_rotary": _profile("air_rotary", "air", (0, 110), 10, 18, 20, 20),
    "air_fixed_wing": _profile("air_fixed_wing", "air", (30, 300), 15, 8, 35, 35),
    "air_high_speed": _profile("air_high_speed", "air", (80, 600), 30, 5, 80, 80),
    "surface_maritime_slow": _profile("surface_maritime_slow", "surface", (0, 15), 1, 3),
    "surface_maritime_fast": _profile("surface_maritime_fast", "surface", (0, 40), 3, 8),
    "unknown_air": _profile("unknown_air", "air", (0, 350), 20, 12, 50, 50),
    "unknown_surface": _profile("unknown_surface", "surface", (0, 45), 4, 10),
}


def load_type_mapping(path: str | Path | None) -> dict[str, str]:
    if path is None:
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or any(not isinstance(key, str) or not isinstance(value, str)
                                         for key, value in data.items()):
        raise ValueError("type mapping must be a JSON object of string tokens to profile names")
    unknown = sorted(set(data.values()) - set(DEFAULT_PROFILES))
    if unknown:
        raise ValueError(f"type mapping references unknown profiles: {', '.join(unknown)}")
    return data


def resolve_profile(reported_type: str | None, domain: str, mapping: dict[str, str]) -> tuple[MobilityProfile, str]:
    if reported_type is not None and reported_type in mapping:
        profile = DEFAULT_PROFILES[mapping[reported_type]]
        if profile.domain != domain:
            return DEFAULT_PROFILES[f"unknown_{domain}"], "domain_mismatch"
        return profile, "mapped"
    return DEFAULT_PROFILES[f"unknown_{domain}"], "unknown" if reported_type else "not_reported"
