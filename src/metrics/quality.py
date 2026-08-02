"""Data-quality metrics for monitoring the catalogue: cross-source duplicate
rate, per-source coverage, and field completeness. All read-only aggregates,
suitable for a dashboard tile or a periodic health check.

Note on *precision*: measuring extraction precision needs a labelled ground-truth
set (the eval-set task) — it can't be computed from the data alone, so it's not
here yet."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from db.tables import Developer, Project, Source


def _dup_stat(session: Session, table) -> dict:
    total = session.scalar(select(func.count()).select_from(table)) or 0
    unique = session.scalar(
        select(func.count()).select_from(table).where(table.canonical_id.is_(None))
    ) or 0
    duplicates = total - unique
    return {
        "total": total,
        "unique": unique,
        "duplicates": duplicates,
        "duplicate_rate_pct": round(100 * duplicates / total, 1) if total else 0.0,
    }


def duplicate_rates(session: Session) -> dict[str, dict]:
    """How much of each entity is cross-source duplication (canonical_id set)."""
    return {
        "developers": _dup_stat(session, Developer),
        "projects": _dup_stat(session, Project),
    }


def source_coverage(session: Session) -> list[dict]:
    """Rows contributed per source, plus how many are shared (duplicated) vs
    unique to that source."""
    rows = session.execute(
        select(
            Source.name,
            func.count(Project.id).label("projects"),
            func.count(Project.id).filter(Project.canonical_id.isnot(None)).label("shared"),
        )
        .join(Project, Project.source_id == Source.id)
        .group_by(Source.name)
        .order_by(func.count(Project.id).desc())
    ).all()
    return [
        {"source": name, "projects": projects, "shared_with_other_source": shared,
         "unique_to_source": projects - shared}
        for name, projects, shared in rows
    ]


def completeness(session: Session) -> dict:
    """Field fill-rate over the *canonical* projects (the deduped market)."""
    base = select(func.count()).select_from(Project).where(Project.canonical_id.is_(None))
    total = session.scalar(base) or 0

    def pct(column) -> float:
        n = session.scalar(base.where(column.isnot(None))) or 0
        return round(100 * n / total, 1) if total else 0.0

    return {
        "projects": total,
        "with_price_pct": pct(Project.min_price),
        "with_developer_pct": pct(Project.developer_id),
        "with_area_pct": pct(Project.area_id),
        "with_delivery_date_pct": pct(Project.delivery_date),
    }
