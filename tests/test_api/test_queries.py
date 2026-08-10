"""Scoping shared by every catalogue endpoint.

The zone rules matter most: areas are deduplicated across sources, and until now
nothing resolved them at read time. "New Cairo" (Nawy) and "New Cairo City"
(Property Finder) were reported as two zones, so /insights/zones showed New
Cairo at 383 projects where the real figure is 521.

These assert on the compiled SQL because the models use PostgreSQL types that
SQLite cannot host, and the suite must run with no database.
"""

from sqlalchemy import func, select

from api.queries import canonical_area_name, scoped
from db.tables import Project, Source


def _sql(stmt) -> str:
    return str(stmt.compile(compile_kwargs={"literal_binds": True})).lower()


def test_dedup_is_applied_by_default():
    sql = _sql(scoped(select(Project.id), source=None, zone=None))

    assert "canonical_id is null" in sql


def test_dedup_can_be_turned_off_to_count_raw_rows():
    sql = _sql(scoped(select(Project.id), source=None, zone=None, dedup=False))

    assert "canonical_id is null" not in sql


def test_a_zone_filter_resolves_through_the_canonical_area():
    """Filtering by a zone must reach projects filed under another source's
    spelling of it, which is the whole point of deduplicating areas."""
    sql = _sql(scoped(select(Project.id), source=None, zone="New Cairo"))

    assert "coalesce" in sql
    assert "new cairo" in sql


def test_a_zone_filter_also_accepts_the_duplicate_spelling():
    """A caller holding an old zone name should still find rows rather than an
    empty result, so the filter matches the area's own name as well as the
    canonical one."""
    sql = _sql(scoped(select(Project.id), source=None, zone="New Cairo City"))

    assert " or " in sql
    assert "coalesce" in sql
    assert "areas.name" in sql


def test_no_zone_means_no_area_join():
    """An unfiltered query should not pay for a self-join it does not use."""
    sql = _sql(scoped(select(Project.id), source=None, zone=None))

    assert "coalesce" not in sql


def test_a_source_filter_narrows_to_that_source():
    sql = _sql(scoped(select(Project.id), source="nawy", zone=None))

    assert "sources" in sql
    assert "nawy" in sql


def test_a_source_filter_composes_with_a_caller_that_already_joined_sources():
    """/projects and /launches select the source name, so they join sources
    themselves. A second join here made every source-filtered request 500 with
    "table name sources specified more than once"."""
    already_joined = select(Project.id, Source.name).join(
        Source, Source.id == Project.source_id
    )

    sql = _sql(scoped(already_joined, source="nawy", zone=None))

    assert sql.count("join sources") == 1
    assert "nawy" in sql


def test_canonical_area_name_prefers_the_canonical_over_the_duplicate():
    sql = _sql(select(canonical_area_name()))

    assert "coalesce" in sql


def test_grouping_by_canonical_name_collapses_duplicate_zones():
    """Two source spellings of one zone must group into a single row."""
    stmt = select(canonical_area_name(), func.count(Project.id)).group_by(
        canonical_area_name()
    )

    assert "coalesce" in _sql(stmt)
