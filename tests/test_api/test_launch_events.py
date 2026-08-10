"""Assembling the change feed from rows.

Kept pure, like the materiality rule it calls: the ordering and the merging of
two different event kinds is where a feed quietly becomes wrong, and that should
not need a database to check.
"""

from datetime import UTC, datetime, timedelta

from api.launch_events import NewRow, SnapshotRow, build_events

NOW = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)


def _new(name, seen_hours_ago, price=6_000_000.0):
    return NewRow(
        project_id=f"id-{name}",
        name=name,
        developer="TMG",
        zone="Al Dabaa",
        source="nawy",
        first_seen_at=NOW - timedelta(hours=seen_hours_ago),
        min_price=price,
    )


def _snap(name, hours_ago, price):
    return SnapshotRow(
        project_id=f"id-{name}",
        name=name,
        developer="TMG",
        zone="Al Dabaa",
        source="nawy",
        snapshot_at=NOW - timedelta(hours=hours_ago),
        min_price=price,
    )


def test_a_new_project_becomes_a_new_event():
    events = build_events([_new("Southmed", 2)], [], min_change_pct=5)

    assert len(events) == 1
    assert events[0].kind == "new"
    assert events[0].name == "Southmed"
    assert events[0].min_price == 6_000_000.0


def test_a_material_move_becomes_a_price_change_event():
    snapshots = [_snap("Perla", 3, 6_000_000.0), _snap("Perla", 1, 7_200_000.0)]

    events = build_events([], snapshots, min_change_pct=5)

    assert len(events) == 1
    assert events[0].kind == "price_change"
    assert events[0].from_price == 6_000_000.0
    assert events[0].to_price == 7_200_000.0
    assert round(events[0].change_pct) == 20


def test_drift_produces_no_event_at_all():
    """Not an event with a small number — no row, so the feed stays readable."""
    snapshots = [_snap("Perla", 3, 6_000_000.0), _snap("Perla", 1, 6_050_000.0)]

    assert build_events([], snapshots, min_change_pct=5) == []


def test_snapshots_are_grouped_per_project():
    snapshots = [
        _snap("Perla", 3, 6_000_000.0),
        _snap("Salt", 3, 10_000_000.0),
        _snap("Perla", 1, 7_200_000.0),
        _snap("Salt", 1, 10_050_000.0),
    ]

    events = build_events([], snapshots, min_change_pct=5)

    assert [e.name for e in events] == ["Perla"]


def test_both_kinds_appear_in_one_feed_newest_first():
    events = build_events(
        [_new("Southmed", 1)],
        [_snap("Perla", 5, 6_000_000.0), _snap("Perla", 3, 7_200_000.0)],
        min_change_pct=5,
    )

    assert [e.kind for e in events] == ["new", "price_change"]


def test_a_project_that_is_both_new_and_moved_reports_only_as_new():
    """Its first price is not a change from anything, and two rows for one
    project reads as two events."""
    events = build_events(
        [_new("Southmed", 5)],
        [_snap("Southmed", 4, 6_000_000.0), _snap("Southmed", 1, 7_200_000.0)],
        min_change_pct=5,
    )

    assert [e.kind for e in events] == ["new"]


def test_an_empty_window_is_an_empty_feed():
    assert build_events([], [], min_change_pct=5) == []


def test_events_carry_what_the_reader_needs_to_act():
    events = build_events([_new("Southmed", 2)], [], min_change_pct=5)

    event = events[0]
    assert event.project_id == "id-Southmed"
    assert event.developer == "TMG"
    assert event.zone == "Al Dabaa"
    assert event.source == "nawy"
