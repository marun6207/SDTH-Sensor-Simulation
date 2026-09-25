from __future__ import annotations

import pytest
from pydantic import ValidationError

from hazard_forecast.models import infer_domain, interpolate_track, parse_track


def point(timestamp: str = "2026-09-25T12:00:00Z", **changes):
    value = {"timestamp": timestamp, "lat": 1.3, "long": 103.8, "altitude": 1000.0,
             "speed": None, "type": None}
    value.update(changes)
    return value


def test_parse_contract_and_domain_inference() -> None:
    observations = parse_track([point()])
    assert observations[0].longitude == 103.8
    assert infer_domain(observations).value == "air"
    surface = parse_track([point(altitude=5)])
    assert infer_domain(surface).value == "surface"
    assert infer_domain(surface, "air").source == "override"


@pytest.mark.parametrize("document", [
    {}, [], [point(timestamp="2026-09-25T12:00:00+00:00")],
    [point(speed=-1)], [point(type="")], [point(extra=True)], [point(lat="1.3")],
])
def test_invalid_contracts_are_rejected(document) -> None:
    with pytest.raises((ValueError, ValidationError)):
        parse_track(document)


def test_timestamps_must_be_strictly_increasing() -> None:
    with pytest.raises(ValueError, match="strictly increasing"):
        parse_track([point(), point()])


def test_track_interpolation_uses_fixed_cadence_and_retains_endpoint() -> None:
    observations = parse_track([
        point(type="fixed-wing"),
        point(timestamp="2026-09-25T12:00:25Z", lat=1.325, long=103.825, altitude=750, speed=50),
    ])
    result = interpolate_track(observations, 10)
    assert [item.timestamp.second for item in result] == [0, 10, 20, 25]
    assert result[1].lat == pytest.approx(1.31)
    assert result[1].altitude == pytest.approx(900)
    assert all(item.vehicle_type == "fixed-wing" for item in result)


def test_track_interpolation_rejects_non_positive_step() -> None:
    with pytest.raises(ValueError, match="at least 1 second"):
        interpolate_track(parse_track([point()]), 0)


def test_osm_catalog_excludes_military_sites_and_contents() -> None:
    from hazard_forecast.snapshot import build_overpass_query, normalize_osm

    query = build_overpass_query("(1,103,2,104)")
    assert "military" not in query
    raw = {"elements": [
        {"type": "node", "id": 1, "lat": 1.3, "lon": 103.8,
         "tags": {"landuse": "military", "amenity": "hospital", "name": "Excluded Site"}},
        {"type": "node", "id": 2, "lat": 1.31, "lon": 103.81,
         "tags": {"amenity": "hospital", "name": "Civil Hospital"}},
    ]}
    features = normalize_osm(raw)
    assert [item.display_name for item in features] == ["Civil Hospital"]
