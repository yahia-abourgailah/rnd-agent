"""The change feed: what moved since the caller last looked.

Two kinds of movement, from two sources of truth. A project appearing is exact,
taken from first_seen_at. A price moving is a judgement, because the sources
report a minimum that shifts as inventory sells — see api/changes.py for the
rule that decides which of those is worth reporting.
"""

import re
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.dependencies import get_session
from api.launch_events import NewRow, SnapshotRow, build_events
from api.queries import canonical_area_name, join_areas, scoped
from api.schemas import LaunchesResponse
from db.tables import Availability, Developer, Project, Source

router = APIRouter(prefix="/launches", tags=["launches"])

_RELATIVE = re.compile(r"^(\d+)d$")


def _window_start(since: str) -> datetime:
    """`7d` or an ISO date. Rejected loudly rather than silently defaulted —
    a window quietly wider than asked for makes the feed look wrong."""
    relative = _RELATIVE.match(since.strip())
    if relative:
        return datetime.now(UTC) - timedelta(days=int(relative.group(1)))
    try:
        parsed = datetime.fromisoformat(since)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"since must be like '7d' or an ISO date, got {since!r}",
        ) from None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


@router.get("", response_model=LaunchesResponse)
def launches(
    since: str = Query("7d", description="Window: '7d', '30d', or an ISO date"),
    min_change_pct: float = Query(5.0, ge=0, le=100),
    source: str | None = Query(None),
    zone: str | None = Query(None),
    developer: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
) -> LaunchesResponse:
    """What changed in the window: projects that appeared, and prices that moved
    enough to mean something."""
    start = _window_start(since)

    def described(stmt):
        stmt = join_areas(stmt).outerjoin(
            Developer, Developer.id == Project.developer_id
        )
        return scoped(stmt, source, zone).join(
            Source, Source.id == Project.source_id, isouter=True
        )

    new_stmt = described(
        select(
            Project.id,
            Project.name,
            Developer.name,
            canonical_area_name(),
            Source.name,
            Project.first_seen_at,
            Project.min_price,
        ).select_from(Project)
    ).where(Project.first_seen_at >= start)
    if developer:
        new_stmt = new_stmt.where(func.lower(Developer.name) == developer.lower())

    new_rows = [
        NewRow(str(pid), name, dev, area, src, seen, price)
        for pid, name, dev, area, src, seen, price in session.execute(new_stmt).all()
    ]

    snapshot_stmt = described(
        select(
            Project.id,
            Project.name,
            Developer.name,
            canonical_area_name(),
            Source.name,
            Availability.snapshot_at,
            Availability.min_price,
        ).select_from(Project)
    ).join(Availability, Availability.project_id == Project.id).where(
        Availability.snapshot_at >= start
    )
    if developer:
        snapshot_stmt = snapshot_stmt.where(
            func.lower(Developer.name) == developer.lower()
        )

    snapshot_rows = [
        SnapshotRow(str(pid), name, dev, area, src, at, price)
        for pid, name, dev, area, src, at, price in session.execute(snapshot_stmt).all()
    ]

    runs = session.scalar(
        select(func.count(func.distinct(Availability.snapshot_at))).where(
            Availability.snapshot_at >= start
        )
    )

    events = build_events(new_rows, snapshot_rows, min_change_pct)
    page = events[offset : offset + limit]

    return LaunchesResponse(
        since=start,
        min_change_pct=min_change_pct,
        snapshot_runs_in_window=runs or 0,
        total=len(events),
        results=[event.__dict__ for event in page],
    )
