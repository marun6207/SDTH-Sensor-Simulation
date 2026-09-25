"""Optional browser acceptance test.

Install ``requirements-dev.txt`` and a Chromium runtime, then run this file with
``pytest tests/e2e`` while the app is available at ``DASH_BASE_URL`` (defaults
to the local development URL).
"""

from __future__ import annotations

import os

import pytest

playwright = pytest.importorskip("playwright.sync_api")


def test_author_generate_and_persist(page) -> None:
    page.goto(os.getenv("DASH_BASE_URL", "http://127.0.0.1:8050"))
    page.get_by_text("JOINT SENSOR SIMULATOR").wait_for()
    page.get_by_role("button", name="Generate outputs").click()
    page.get_by_text("Generated", exact=False).wait_for()
    assert page.get_by_text("GIRAFFE_AIRBASE_01", exact=False).is_visible()
    assert page.get_by_text("CCTV_COASTAL_01", exact=False).is_visible()
    cctv_row = page.locator(".export-row").filter(has_text="CCTV_COASTAL_01")
    assert "cctv0" not in cctv_row.inner_text().replace(" ", "")
    assert cctv_row.get_by_role("button", name="Download").is_enabled()

    page.get_by_role("button", name="Hostile Air").click()
    tactical_map = page.locator("#tactical-map")
    box = tactical_map.bounding_box()
    assert box is not None
    tactical_map.click(position={"x": box["width"] * .55, "y": box["height"] * .45})
    page.get_by_text("Placed HOSTILE_AIR", exact=False).wait_for()

    entity_select = page.locator("#entity-select input")
    entity_select.fill("Hostile Air 2")
    entity_select.press("Enter")
    page.locator("#add-waypoint").click()
    tactical_map.click(position={"x": box["width"] * .68, "y": box["height"] * .62})
    page.get_by_text("Added waypoint", exact=False).wait_for()

    page.reload()
    page.get_by_text("JOINT SENSOR SIMULATOR").wait_for()
    assert page.locator("#entity-select").is_visible()
