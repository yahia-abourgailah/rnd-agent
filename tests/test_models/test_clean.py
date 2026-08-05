"""Cleaning is enforced at the model boundary, so these assert on the models
rather than on the mappers — any future write path inherits the same behaviour."""

import pytest

from models import Area, Developer, Project
from models.clean import clean_text, delivery_year
from models.launch import PropertyType, canonical_property_type, normalize_property_types


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Modon ", "Modon"),
        ("  Palm  Hills  ", "Palm Hills"),
        ("New\tCairo", "New Cairo"),
        ("Sodic", "Sodic"),
    ],
)
def test_clean_text_trims_and_collapses(raw, expected):
    assert clean_text(raw) == expected


def test_blank_text_becomes_none_not_empty_string():
    assert clean_text("   ") is None


def test_developer_names_are_cleaned_on_construction():
    """'Modon ' and 'Modon' arriving from different endpoints must not become
    two developers."""
    assert Developer(source="nawy", source_id="1", name="Modon ").name == "Modon"


def test_area_city_is_cleaned():
    assert Area(source="nawy", source_id="2", name="New Cairo", city=" Cairo ").city == "Cairo"


@pytest.mark.parametrize(
    "raw,expected",
    [
        (20291230, "2029"),
        ("2029-12-30", "2029"),
        ("Q4 2029", "2029"),
        ("2029", "2029"),
        (None, None),
        ("", None),
        ("under construction", None),
    ],
)
def test_delivery_year_is_one_format_regardless_of_source(raw, expected):
    assert delivery_year(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Twinhouse", "twin_house"),
        ("Twin House", "twin_house"),
        ("twin-house", "twin_house"),
        ("Apartment", "apartment"),
        ("STUDIO", "studio"),
        ("Standalone Villa", "villa"),
        ("Office", "commercial"),
    ],
)
def test_source_spellings_map_onto_one_vocabulary(raw, expected):
    assert canonical_property_type(raw) == expected


def test_unknown_types_are_kept_in_canonical_shape_not_dropped():
    """A source's vocabulary is wider than the enum; losing a project over an
    unmapped type would be worse than carrying an unnamed value."""
    assert canonical_property_type("Administrative Building") == "administrative_building"
    assert PropertyType.from_source("Administrative Building") is None


def test_normalize_property_types_dedupes_across_spellings():
    assert normalize_property_types(["Twinhouse", "Twin House", "Apartment"]) == [
        "apartment",
        "twin_house",
    ]


def test_project_and_launch_paths_agree_on_property_type_spelling():
    """The bug this guards: projects held 'Twinhouse' while launches held
    'twin_house', so any group-by split into duplicate buckets."""
    project = Project(
        source="nawy",
        source_id="1",
        name="X",
        property_types=normalize_property_types(["Twinhouse"]),
    )
    assert project.property_types == [PropertyType.TWIN_HOUSE.value]
