"""Finding a project, and everything known about one.

The drill-down the change feed points at: something moved, now show me what it
is, what it contains, how its price has behaved, and who else lists it.
"""

import uuid as uuidlib

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.dependencies import get_session
from api.queries import canonical_area_name, join_areas, scoped
from api.schemas import (
    PriceSnapshot,
    ProjectDetail,
    ProjectRow,
    ProjectsResponse,
    UnitSummaryOut,
)
from api.unit_summary import UnitRow, summarise_units
from db.tables import Availability, Developer, Project, Source, Unit

router = APIRouter(prefix="/projects", tags=["projects"])

_SORTS = {
    "newest": Project.first_seen_at.desc(),
    "price": Project.min_price.desc().nullslast(),
    "name": Project.name.asc(),
}


def _described(stmt):
    return join_areas(stmt).outerjoin(
        Developer, Developer.id == Project.developer_id
    ).join(Source, Source.id == Project.source_id, isouter=True)


def _row_columns():
    return (
        Project.id,
        Project.name,
        Developer.name,
        canonical_area_name(),
        Source.name,
        Project.min_price,
        Project.currency,
        Project.property_types,
        Project.is_launch,
        Project.delivery_date,
        Project.first_seen_at,
    )


def _to_row(record) -> ProjectRow:
    pid, name, dev, zone, src, price, currency, types, launch, delivery, seen = record
    return ProjectRow(
        project_id=str(pid),
        name=name,
        developer=dev,
        zone=zone,
        source=src,
        min_price=price,
        currency=currency,
        property_types=list(types or []),
        is_launch=launch,
        delivery_date=delivery,
        first_seen_at=seen,
    )


@router.get("", response_model=ProjectsResponse)
def search_projects(
    q: str | None = Query(None, description="Match on project name"),
    developer: str | None = Query(None),
    zone: str | None = Query(None),
    source: str | None = Query(None),
    is_launch: bool | None = Query(None),
    min_price: float | None = Query(None, ge=0),
    max_price: float | None = Query(None, ge=0),
    delivery_year: str | None = Query(None, pattern=r"^\d{4}$"),
    sort: str = Query("newest", pattern="^(newest|price|name)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
) -> ProjectsResponse:
    """Find projects. Deduplicated by default, so one project appears once even
    when several sources report it."""
    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"min_price {min_price} is above max_price {max_price}",
        )

    def filtered(stmt):
        stmt = scoped(_described(stmt.select_from(Project)), source, zone, areas_joined=True)
        if q:
            stmt = stmt.where(Project.name.ilike(f"%{q}%"))
        if developer:
            stmt = stmt.where(func.lower(Developer.name) == developer.lower())
        if is_launch is not None:
            stmt = stmt.where(Project.is_launch.is_(is_launch))
        if min_price is not None:
            stmt = stmt.where(Project.min_price >= min_price)
        if max_price is not None:
            stmt = stmt.where(Project.min_price <= max_price)
        if delivery_year:
            stmt = stmt.where(Project.delivery_date == delivery_year)
        return stmt

    total = session.scalar(filtered(select(func.count(Project.id)))) or 0
    rows = session.execute(
        filtered(select(*_row_columns())).order_by(_SORTS[sort]).limit(limit).offset(offset)
    ).all()

    return ProjectsResponse(
        total=total, limit=limit, offset=offset, results=[_to_row(r) for r in rows]
    )


@router.get("/{project_id}", response_model=ProjectDetail)
def project_detail(
    project_id: str, session: Session = Depends(get_session)
) -> ProjectDetail:
    """One project in full. A duplicate's id resolves to its canonical row, so a
    link built from any source lands somewhere useful."""
    try:
        wanted = uuidlib.UUID(project_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{project_id!r} is not a project id",
        ) from None

    canonical_id = session.scalar(
        select(func.coalesce(Project.canonical_id, Project.id)).where(
            Project.id == wanted
        )
    )
    if canonical_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No project {project_id}"
        )

    record = session.execute(
        _described(select(*_row_columns()).select_from(Project)).where(
            Project.id == canonical_id
        )
    ).first()
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No project {project_id}"
        )

    unit_records = session.execute(
        select(
            Unit.price, Unit.unit_area_sqm, Unit.bedrooms, Unit.property_type, Unit.finishing
        ).where(Unit.project_id == canonical_id)
    ).all()
    units = summarise_units([UnitRow(*r) for r in unit_records])

    unit_sources = session.scalars(
        select(func.distinct(Source.name))
        .select_from(Unit)
        .join(Source, Source.id == Unit.source_id)
        .where(Unit.project_id == canonical_id)
    ).all()

    history = session.execute(
        select(
            Availability.snapshot_at,
            Availability.min_price,
            Availability.max_price,
            Availability.total_units,
        )
        .where(Availability.project_id == canonical_id)
        .order_by(Availability.snapshot_at)
    ).all()

    also = session.scalars(
        select(func.distinct(Source.name))
        .select_from(Project)
        .join(Source, Source.id == Project.source_id)
        .where(Project.canonical_id == canonical_id)
    ).all()

    return ProjectDetail(
        project=_to_row(record),
        requested_id=project_id if str(canonical_id) != project_id else None,
        units_available_from=list(unit_sources),
        units=UnitSummaryOut(**units.__dict__),
        price_history=[
            PriceSnapshot(snapshot_at=at, min_price=lo, max_price=hi, total_units=n)
            for at, lo, hi, n in history
        ],
        also_listed_on=list(also),
    )
