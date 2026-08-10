"""Turning catalogue rows into a feed of things that moved.

Pure, like the materiality rule it calls. Ordering and the merging of two event
kinds is where a feed quietly becomes wrong, and checking that should not need a
database.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from api.changes import detect_price_change


@dataclass(frozen=True)
class NewRow:
    project_id: str
    name: str
    developer: str | None
    zone: str | None
    source: str
    first_seen_at: datetime
    min_price: float | None


@dataclass(frozen=True)
class SnapshotRow:
    project_id: str
    name: str
    developer: str | None
    zone: str | None
    source: str
    snapshot_at: datetime
    min_price: float | None


@dataclass(frozen=True)
class LaunchEvent:
    kind: str
    project_id: str
    name: str
    developer: str | None
    zone: str | None
    source: str
    occurred_at: datetime
    min_price: float | None = None
    from_price: float | None = None
    to_price: float | None = None
    change_pct: float | None = None


def build_events(
    new_rows: list[NewRow],
    snapshot_rows: list[SnapshotRow],
    min_change_pct: float,
) -> list[LaunchEvent]:
    """The feed for one window, newest first.

    A project that appeared inside the window reports only as new: its first
    observed price is not a change from anything, and two rows for one project
    read as two separate things happening.
    """
    events = [
        LaunchEvent(
            kind="new",
            project_id=row.project_id,
            name=row.name,
            developer=row.developer,
            zone=row.zone,
            source=row.source,
            occurred_at=row.first_seen_at,
            min_price=row.min_price,
        )
        for row in new_rows
    ]
    already_reported = {row.project_id for row in new_rows}

    by_project: dict[str, list[SnapshotRow]] = defaultdict(list)
    for row in snapshot_rows:
        if row.project_id not in already_reported:
            by_project[row.project_id].append(row)

    for rows in by_project.values():
        rows.sort(key=lambda r: r.snapshot_at)
        change = detect_price_change(
            [(r.snapshot_at, r.min_price) for r in rows], min_change_pct
        )
        if change is None:
            continue
        latest = rows[-1]
        events.append(
            LaunchEvent(
                kind="price_change",
                project_id=latest.project_id,
                name=latest.name,
                developer=latest.developer,
                zone=latest.zone,
                source=latest.source,
                occurred_at=change.observed_at,
                from_price=change.from_price,
                to_price=change.to_price,
                change_pct=change.change_pct,
            )
        )

    events.sort(key=lambda e: e.occurred_at, reverse=True)
    return events
