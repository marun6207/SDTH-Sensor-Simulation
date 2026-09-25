from __future__ import annotations

import pytest
from pydantic import ValidationError

from hazard_forecast.models import infer_domain, parse_track


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
