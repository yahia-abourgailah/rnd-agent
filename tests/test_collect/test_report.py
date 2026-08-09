"""Whether a run may be persisted.

A run that writes a truncated catalogue is worse than one that raises: the
partial data looks like a real result and nothing downstream can tell.
"""

from datetime import UTC, datetime

import pytest

from collect.base import CollectionResult
from collect.report import StopReason, evaluate
from models import Project


def _projects(count, with_price=True, offset=0):
    return [
        Project(
            source="aqarmap",
            source_id=str(offset + i),
            name=f"P{offset + i}",
            min_price=100.0 if with_price else None,
        )
        for i in range(count)
    ]


def _result(projects):
    return CollectionResult(
        source="aqarmap",
        developers=[],
        areas=[],
        projects=projects,
        units=[],
        fetched_at=datetime.now(UTC),
    )


def test_a_full_run_is_complete():
    report = evaluate(_result(_projects(10)), min_projects=5, coverage_floors={})

    assert report.stop_reason is StopReason.COMPLETE
    assert report.ok


def test_a_truncated_run_is_below_floor():
    """A scrape returning 12 of ~1988 means the markup changed. Writing that
    would silently gut the catalogue."""
    report = evaluate(_result(_projects(2)), min_projects=5, coverage_floors={})

    assert report.stop_reason is StopReason.BELOW_FLOOR
    assert not report.ok
    assert "2" in report.message and "5" in report.message


def test_an_empty_run_is_distinguishable_from_a_truncated_one():
    """Different causes: an empty fetch is usually an outage, a short one is
    usually a markup change."""
    report = evaluate(_result([]), min_projects=5, coverage_floors={})

    assert report.stop_reason is StopReason.NO_RECORDS


def test_collapsed_field_coverage_fails_even_at_full_count():
    """An HTML parser fails by returning the right number of rows with every
    field empty."""
    report = evaluate(
        _result(_projects(10, with_price=False)),
        min_projects=5,
        coverage_floors={"min_price": 0.8},
    )

    assert report.stop_reason is StopReason.BELOW_FLOOR
    assert "min_price" in report.message


@pytest.mark.parametrize("share", [0.8, 1.0])
def test_coverage_at_or_above_the_floor_passes(share):
    priced = int(10 * share)
    projects = _projects(priced) + _projects(10 - priced, with_price=False, offset=priced)

    report = evaluate(
        _result(projects), min_projects=5, coverage_floors={"min_price": 0.8}
    )

    assert report.stop_reason is StopReason.COMPLETE


def test_the_report_carries_the_numbers_not_just_a_verdict():
    """The CLI prints this; a bare pass/fail would send someone back to the logs."""
    report = evaluate(_result(_projects(10)), min_projects=5, coverage_floors={})

    assert report.counts["projects"] == 10
    assert report.coverage["name"] == 1.0
    assert report.source == "aqarmap"


def test_a_floor_naming_a_field_that_does_not_exist_aborts_rather_than_passes():
    """A typo in the floors config must not read as 'coverage fine'. It aborts,
    which is noisy and safe, rather than silently disabling the guard."""
    report = evaluate(
        _result(_projects(10)), min_projects=5, coverage_floors={"mn_price": 0.8}
    )

    assert report.stop_reason is StopReason.BELOW_FLOOR
    assert "mn_price" in report.message
