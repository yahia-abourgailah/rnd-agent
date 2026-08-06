"""History only accrues forward, so every source snapshots every run — filling
what it knows and leaving the rest NULL."""

from datetime import UTC, datetime

from collect.base import CollectionResult
from collect.snapshot import snapshots_for
from models import Project, Unit


def _result(projects, units, source="property_finder"):
    return CollectionResult(
        source=source,
        developers=[],
        areas=[],
        projects=projects,
        units=units,
        fetched_at=datetime(2026, 8, 6, 12, 0, tzinfo=UTC),
    )


def test_a_source_without_units_still_snapshots_price():
    projects = [
        Project(source="property_finder", source_id="7", name="X", min_price=5_000_000.0)
    ]

    snapshots = snapshots_for(_result(projects, []))

    assert len(snapshots) == 1
    assert snapshots[0].min_price == 5_000_000.0
    assert snapshots[0].total_units is None


def test_a_source_with_units_snapshots_the_unit_rollup():
    projects = [Project(source="nawy", source_id="1198", name="Southmed")]
    units = [
        Unit(source="nawy", source_id="a", project_source_id="1198", price=100.0,
             unit_area_sqm=10.0, property_type="villa"),
        Unit(source="nawy", source_id="b", project_source_id="1198", price=300.0,
             unit_area_sqm=10.0, property_type="chalet"),
    ]

    snapshots = snapshots_for(_result(projects, units, source="nawy"))

    rollup = next(s for s in snapshots if s.project_source_id == "1198")
    assert rollup.total_units == 2
    assert rollup.min_price == 100.0
    assert rollup.max_price == 300.0


def test_every_project_gets_a_snapshot_not_only_those_with_units():
    """The old path snapshotted 877 of 1,835 Nawy projects, so the ones without
    unit rows had no history at all."""
    projects = [
        Project(source="nawy", source_id="1", name="HasUnits"),
        Project(source="nawy", source_id="2", name="NoUnits", min_price=99.0),
    ]
    units = [Unit(source="nawy", source_id="a", project_source_id="1", price=50.0)]

    snapshots = snapshots_for(_result(projects, units, source="nawy"))

    assert {s.project_source_id for s in snapshots} == {"1", "2"}


def test_every_snapshot_in_a_run_shares_one_timestamp():
    """One timestamp per run is what makes a retry idempotent against the
    unique constraint."""
    projects = [
        Project(source="property_finder", source_id=str(i), name=f"P{i}")
        for i in range(3)
    ]

    stamps = {s.snapshot_at for s in snapshots_for(_result(projects, []))}

    assert len(stamps) == 1


def test_projects_with_no_price_and_no_units_are_still_recorded():
    """Absence at a point in time is itself a data point for trends."""
    projects = [Project(source="property_finder", source_id="9", name="Y")]

    assert len(snapshots_for(_result(projects, []))) == 1


def test_snapshots_carry_the_collecting_source():
    projects = [Project(source="property_finder", source_id="9", name="Y")]

    assert snapshots_for(_result(projects, []))[0].source == "property_finder"
