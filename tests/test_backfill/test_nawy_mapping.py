"""Mapping regressions, asserted against the saved live payloads in
tests/fixtures/live/ rather than hand-written dicts — these bugs all came from
the real payload shape differing from what the mapper assumed."""

import json
import pathlib

import pytest

from backfill import nawy_client as nc

FIXTURES = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "live"


def _load(name: str) -> list[dict]:
    payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return payload.get("results", payload) if isinstance(payload, dict) else payload


@pytest.fixture
def compounds():
    return _load("nawy_compounds.json")


def test_delivery_date_falls_back_to_the_resale_plan(compounds):
    """Nawy sends a developerPlan carrying the price but a null readyBy, while
    the resalePlan carries the delivery date. Selecting a whole plan dict lost
    the date on every compound shaped like this."""
    southmed = next(c for c in compounds if c["name"] == "Southmed")
    assert (southmed["developerPlan"] or {}).get("readyBy") is None
    assert (southmed["resalePlan"] or {}).get("readyBy") == 20291230

    project = nc.map_compound(southmed, set())

    assert project.delivery_date == "2029"


def test_price_still_prefers_the_developer_plan(compounds):
    """Per-field fallback must not silently start quoting resale prices."""
    southmed = next(c for c in compounds if c["name"] == "Southmed")

    project = nc.map_compound(southmed, set())

    assert project.min_price == southmed["developerPlan"]["minPrice"]
    assert project.min_price != southmed["resalePlan"]["minPrice"]


def test_delivery_date_is_a_year_not_a_full_date(compounds):
    for raw in compounds:
        project = nc.map_compound(raw, set())
        if project.delivery_date is not None:
            assert len(project.delivery_date) == 4, project.delivery_date
            assert project.delivery_date.isdigit()


def test_property_types_are_canonical(compounds):
    for raw in compounds:
        project = nc.map_compound(raw, set())
        for property_type in project.property_types:
            assert property_type == property_type.lower()
            assert " " not in property_type
    southmed = nc.map_compound(next(c for c in compounds if c["name"] == "Southmed"), set())
    assert "twin_house" in southmed.property_types
    assert "Twinhouse" not in southmed.property_types


def test_developer_names_are_trimmed():
    modon = next(d for d in _load("nawy_developers.json") if d["name"].strip() == "Modon")
    assert modon["name"] != modon["name"].strip()

    assert nc.map_developer(modon).name == "Modon"


def test_areas_endpoint_supplies_no_city_so_compounds_must():
    """/v1/areas carries no parentAreaName at all; the city can only come from
    the compound records, which is why the two must merge rather than overwrite."""
    for raw in _load("nawy_areas.json"):
        assert "parentAreaName" not in raw
        assert nc.map_area(raw).city is None

    from_compounds = nc.areas_from_compounds(_load("nawy_compounds.json"))
    assert any(area.city for area in from_compounds)
