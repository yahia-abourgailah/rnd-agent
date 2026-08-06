from datetime import UTC, datetime

from collect.base import CollectionResult
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
