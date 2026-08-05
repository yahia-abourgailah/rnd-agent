"""The catalogue tracks primary/off-plan stock only.

Resale was being ingested because nothing read the source's flag. Nawy's API
does filter server-side, but its contract is undocumented — it returns
non-resale results whatever value the key is given — so the exclusion is also
enforced in the mapper, and both layers are tested here.
"""

import json
import pathlib

import pytest

from backfill import nawy_client as nc
from models import SaleType
from watch.adapters.nawy import is_primary

FIXTURE = (
    pathlib.Path(__file__).resolve().parents[1]
    / "fixtures"
    / "live"
    / "nawy_webapi_units.json"
)


@pytest.fixture
def units():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["values"]


def test_the_saved_payload_is_primary_only(units):
    assert units
    for unit in units:
        assert unit["resale"] is False


def test_resale_units_are_dropped_by_the_mapper(units):
    """Belt and braces: if the server-side filter ever stops working, a resale
    record must still not reach the catalogue."""
    resale = dict(units[0], resale=True)

    assert nc.map_unit(resale) is None


def test_primary_units_are_mapped_and_tagged(units):
    unit = nc.map_unit(units[0])

    assert unit is not None
    assert unit.sale_type is SaleType.PRIMARY


def test_mapper_reads_the_web_api_field_names(units):
    """The endpoint changed from listing-api to webapi; the field names differ
    (min_unit_area vs unitArea, property_type object vs string)."""
    raw = next(u for u in units if u["min_price"])
    unit = nc.map_unit(raw)

    assert unit.unit_area_sqm == raw["min_unit_area"]
    assert unit.price == raw["min_price"]
    assert unit.ready_by == str(raw["min_ready_by"])[:10]
    assert unit.property_type == raw["property_type"]["name"].lower()


def test_unpublished_price_and_area_become_null_not_zero(units):
    """Nawy sends 0 for unlaunched compounds. Stored as 0 it reads as free, and
    sorts to the top of any cheapest-first view."""
    raw = next(u for u in units if not u["min_price"])
    unit = nc.map_unit(raw)

    assert unit.price is None
    assert unit.unit_area_sqm is None


def test_is_primary_treats_a_missing_flag_as_primary():
    """A payload change that drops the field should not silently discard the
    whole catalogue."""
    assert is_primary({}) is True
    assert is_primary({"resale": False}) is True
    assert is_primary({"resale": True}) is False


def test_project_price_never_comes_from_the_resale_plan():
    """30% of compounds have no developerPlan price; quoting the resale plan
    there reported a secondary-market price as the project's asking price."""
    compound = {
        "id": 1,
        "name": "Somewhere",
        "developerPlan": {"readyBy": None, "minPrice": None, "currency": "EGP"},
        "resalePlan": {"readyBy": 20291230, "minPrice": 7800000, "currency": "EGP"},
    }

    project = nc.map_compound(compound, set())

    assert project.min_price is None
    # Delivery still falls back: when the building completes is a fact about the
    # building, not about who is selling it.
    assert project.delivery_date == "2029"
