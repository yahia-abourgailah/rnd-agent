"""Rolling a project's units up for the detail view.

Kept pure so the arithmetic can be checked without a database. The awkward
cases are all about absence: Property Finder contributes no units at all, and
Nawy leaves price and area unpublished on projects that have not launched.
"""

from api.unit_summary import UnitRow, summarise_units


def _unit(price=None, area=None, beds=None, ptype=None, finishing=None):
    return UnitRow(
        price=price, area_sqm=area, bedrooms=beds, property_type=ptype, finishing=finishing
    )


def test_no_units_summarises_to_nothing_rather_than_zeroes():
    """Zeroes would read as 'this project has no space and costs nothing'."""
    summary = summarise_units([])

    assert summary.count == 0
    assert summary.min_price is None
    assert summary.max_price is None
    assert summary.bedrooms == {}


def test_price_range_spans_the_units():
    summary = summarise_units([_unit(price=1_000_000), _unit(price=3_000_000)])

    assert summary.min_price == 1_000_000
    assert summary.max_price == 3_000_000


def test_unpublished_prices_are_skipped_not_counted_as_zero():
    """Nawy sends no price for unlaunched compounds; a zero would sort to the
    top of any cheapest-first view."""
    summary = summarise_units([_unit(price=None), _unit(price=2_000_000)])

    assert summary.count == 2
    assert summary.min_price == 2_000_000


def test_price_per_sqm_uses_only_units_that_have_both_numbers():
    summary = summarise_units(
        [_unit(price=1_000_000, area=100), _unit(price=5_000_000, area=None)]
    )

    assert summary.price_per_sqm_min == 10_000
    assert summary.price_per_sqm_max == 10_000


def test_a_zero_area_does_not_divide_by_zero():
    summary = summarise_units([_unit(price=1_000_000, area=0)])

    assert summary.price_per_sqm_min is None


def test_bedroom_mix_is_counted():
    summary = summarise_units([_unit(beds=2), _unit(beds=2), _unit(beds=3)])

    assert summary.bedrooms == {2: 2, 3: 1}


def test_a_studio_counts_as_zero_bedrooms_not_as_missing():
    summary = summarise_units([_unit(beds=0), _unit(beds=2)])

    assert summary.bedrooms == {0: 1, 2: 1}


def test_property_types_and_finishing_are_counted():
    summary = summarise_units(
        [
            _unit(ptype="villa", finishing="finished"),
            _unit(ptype="villa", finishing="not_finished"),
            _unit(ptype="chalet", finishing="finished"),
        ]
    )

    assert summary.property_types == {"villa": 2, "chalet": 1}
    assert summary.finishing == {"finished": 2, "not_finished": 1}


def test_missing_labels_are_left_out_rather_than_bucketed_as_none():
    summary = summarise_units([_unit(ptype=None), _unit(ptype="villa")])

    assert summary.property_types == {"villa": 1}
