from datetime import UTC, datetime

from collect.base import CollectionResult, merge_by_source_id
from models import Area, Developer, Project


def _result(**overrides) -> CollectionResult:
    base = {
        "source": "nawy",
        "developers": [Developer(source="nawy", source_id="1", name="SODIC")],
        "areas": [Area(source="nawy", source_id="2", name="New Cairo")],
        "projects": [
            Project(source="nawy", source_id="3", name="Eastown", min_price=100.0),
            Project(source="nawy", source_id="4", name="Villette"),
        ],
        "units": [],
        "fetched_at": datetime.now(UTC),
    }
    return CollectionResult(**{**base, **overrides})


def test_counts_reports_every_entity():
    assert _result().counts() == {
        "developers": 1,
        "areas": 1,
        "projects": 2,
        "units": 0,
    }


def test_field_coverage_is_the_share_of_rows_with_a_value():
    """A collector can return the right number of records with every field
    empty; coverage is what catches that."""
    coverage = _result().field_coverage("projects")

    assert coverage["name"] == 1.0
    assert coverage["min_price"] == 0.5


def test_field_coverage_of_no_rows_is_empty_not_a_crash():
    assert _result(projects=[]).field_coverage("projects") == {}


def test_merge_keeps_the_richer_record():
    """The same developer arrives twice: once from the developer endpoint with a
    slug, once derived from a compound with only a name."""
    from_endpoint = Developer(source="nawy", source_id="55", name="Misr Italia", slug="55-misr")
    from_compound = Developer(source="nawy", source_id="55", name="Misr Italia Properties")

    merged = merge_by_source_id([from_endpoint, from_compound])

    assert len(merged) == 1
    assert merged[0].slug == "55-misr"
    assert merged[0].name == "Misr Italia Properties"


def test_merge_leaves_distinct_entities_alone():
    entities = [
        Developer(source="nawy", source_id="1", name="A"),
        Developer(source="nawy", source_id="2", name="B"),
    ]

    assert len(merge_by_source_id(entities)) == 2


def test_merge_does_not_let_an_empty_value_erase_a_filled_one():
    rich = Developer(source="nawy", source_id="9", name="X", slug="x-slug")
    sparse = Developer(source="nawy", source_id="9", name="X")

    assert merge_by_source_id([rich, sparse])[0].slug == "x-slug"
