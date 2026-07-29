"""Insights endpoints — aggregate views over the relational catalogue for the
CRM dashboard and ad-hoc R&D analysis. Read-only."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Float, case, cast, func, select
from sqlalchemy.orm import Session

from launch_intel.api.dependencies import get_session
from launch_intel.api.schemas import (
    DeliveryPipelineResponse,
    DeliveryYearRow,
    MarketShareResponse,
    MarketShareRow,
    PaymentTermsResponse,
    PaymentTermsRow,
    PriceBracketRow,
    PriceDistributionResponse,
    PropertyMixResponse,
    PropertyTypeRow,
    WhitespaceResponse,
    WhitespaceRow,
    ZoneRow,
    ZonesResponse,
)
from launch_intel.db.tables import Area, Developer, Project, Source


def _round(value: float | None) -> float | None:
    return round(value) if value is not None else None

router = APIRouter(prefix="/insights", tags=["insights"])


def _scoped(stmt, source: str | None, zone: str | None, dedup: bool = True):
    """Apply optional dedup/source/zone filters to any Project-based query, so
    every aggregate in an endpoint shares the exact same scope.

    dedup=True counts only canonical projects (canonical_id IS NULL) — the
    unique deduped market — so cross-source duplicates aren't double-counted.
    """
    if dedup:
        stmt = stmt.where(Project.canonical_id.is_(None))
    if source:
        stmt = stmt.join(Source, Source.id == Project.source_id).where(Source.name == source)
    if zone:
        stmt = stmt.join(Area, Area.id == Project.area_id).where(func.lower(Area.name) == zone.lower())
    return stmt


@router.get("/market-share", response_model=MarketShareResponse)
def market_share(
    source: str | None = Query(None, description="Filter by source name, e.g. 'nawy'"),
    zone: str | None = Query(None, description="Filter by area/zone name"),
    dedup: bool = Query(True, description="Count unique (deduped) projects only"),
    limit: int = Query(15, ge=1, le=100),
    session: Session = Depends(get_session),
) -> MarketShareResponse:
    """Developer market share by number of projects.

    With dedup=True (default) the same real developer/project seen by both
    sources is counted once — projects were repointed to the canonical developer
    and duplicate projects are excluded. Set dedup=False for raw per-source rows.
    """
    per_dev = _scoped(
        select(Developer.id, Developer.name, func.count(Project.id).label("projects"))
        .join(Project, Project.developer_id == Developer.id)
        .group_by(Developer.id, Developer.name)
        .order_by(func.count(Project.id).desc()),
        source,
        zone,
        dedup,
    ).limit(limit)

    total = session.scalar(_scoped(select(func.count(Project.id)), source, zone, dedup)) or 0
    dev_count = (
        session.scalar(
            _scoped(select(func.count(func.distinct(Project.developer_id))), source, zone, dedup)
        )
        or 0
    )

    results = [
        MarketShareRow(
            developer_id=str(dev_id),
            developer=name,
            projects=n,
            market_share_pct=round(100 * n / total, 2) if total else 0.0,
        )
        for dev_id, name, n in session.execute(per_dev).all()
    ]
    return MarketShareResponse(
        source=source,
        zone=zone,
        total_projects=total,
        developer_count=dev_count,
        results=results,
    )


@router.get("/zones", response_model=ZonesResponse)
def zones(
    source: str | None = Query(None, description="Filter by source name"),
    dedup: bool = Query(True, description="Count unique (deduped) projects only"),
    limit: int = Query(20, ge=1, le=100),
    session: Session = Depends(get_session),
) -> ZonesResponse:
    """Per-zone summary: activity (projects), competition (distinct developers),
    launches, and the price range. Reveals hotspots vs. open zones at a glance."""
    median = func.percentile_cont(0.5).within_group(Project.min_price.asc())
    stmt = _scoped(
        select(
            Area.name,
            Area.city,
            func.count(Project.id).label("projects"),
            func.count(func.distinct(Project.developer_id)).label("developers"),
            func.count(Project.id).filter(Project.is_launch.is_(True)).label("launches"),
            func.min(Project.min_price),
            median,
            func.max(Project.min_price),
        )
        .join(Project, Project.area_id == Area.id)
        .group_by(Area.id, Area.name, Area.city)
        .order_by(func.count(Project.id).desc()),
        source,
        None,
        dedup,
    ).limit(limit)

    results = [
        ZoneRow(
            zone=name,
            city=city,
            projects=projects,
            developers=developers,
            launches=launches,
            min_price=_round(minp),
            median_price=_round(med),
            max_price=_round(maxp),
        )
        for name, city, projects, developers, launches, minp, med, maxp in session.execute(stmt).all()
    ]
    return ZonesResponse(source=source, results=results)


_PRICE_BRACKETS = ["under 5M", "5M–10M", "10M–20M", "20M–50M", "50M+"]


@router.get("/price-distribution", response_model=PriceDistributionResponse)
def price_distribution(
    source: str | None = Query(None, description="Filter by source name"),
    dedup: bool = Query(True, description="Count unique (deduped) projects only"),
    session: Session = Depends(get_session),
) -> PriceDistributionResponse:
    """How the market splits across price brackets (starting price, EGP)."""
    bracket = case(
        (Project.min_price < 5_000_000, "under 5M"),
        (Project.min_price < 10_000_000, "5M–10M"),
        (Project.min_price < 20_000_000, "10M–20M"),
        (Project.min_price < 50_000_000, "20M–50M"),
        else_="50M+",
    ).label("bracket")
    stmt = _scoped(
        select(bracket, func.count(Project.id))
        .where(Project.min_price.isnot(None))
        .group_by(bracket),
        source,
        None,
        dedup,
    )
    counts = {b: n for b, n in session.execute(stmt).all()}
    total = sum(counts.values())
    results = [
        PriceBracketRow(
            bracket=b,
            projects=counts.get(b, 0),
            pct=round(100 * counts.get(b, 0) / total, 2) if total else 0.0,
        )
        for b in _PRICE_BRACKETS
    ]
    return PriceDistributionResponse(source=source, total_projects=total, results=results)


@router.get("/property-mix", response_model=PropertyMixResponse)
def property_mix(
    source: str | None = Query(None, description="Filter by source name"),
    dedup: bool = Query(True, description="Count unique (deduped) projects only"),
    session: Session = Depends(get_session),
) -> PropertyMixResponse:
    """Project counts by property type (a project can offer several)."""
    base = _scoped(select(func.unnest(Project.property_types).label("ptype")), source, None, dedup)
    sub = base.subquery()
    stmt = (
        select(sub.c.ptype, func.count().label("n"))
        .group_by(sub.c.ptype)
        .order_by(func.count().desc())
    )
    results = [
        PropertyTypeRow(property_type=ptype, projects=n)
        for ptype, n in session.execute(stmt).all()
        if ptype
    ]
    return PropertyMixResponse(source=source, results=results)


@router.get("/delivery-pipeline", response_model=DeliveryPipelineResponse)
def delivery_pipeline(
    source: str | None = Query(None, description="Filter by source name"),
    dedup: bool = Query(True, description="Count unique (deduped) projects only"),
    session: Session = Depends(get_session),
) -> DeliveryPipelineResponse:
    """Projects by delivery year — the supply pipeline coming online."""
    year = func.substr(Project.delivery_date, 1, 4).label("year")
    stmt = _scoped(
        select(year, func.count(Project.id))
        .where(Project.delivery_date.op("~")(r"^[0-9]{4}"))
        .group_by(year)
        .order_by(year),
        source,
        None,
        dedup,
    )
    results = [DeliveryYearRow(year=y, projects=n) for y, n in session.execute(stmt).all()]
    return DeliveryPipelineResponse(source=source, results=results)


def _norm(value: float, low: float, high: float) -> float:
    """Min-max normalise into 0..1; 0.5 when the range is flat."""
    return (value - low) / (high - low) if high > low else 0.5


@router.get("/whitespace", response_model=WhitespaceResponse)
def whitespace(
    source: str | None = Query(None, description="Filter by source name"),
    min_projects: int = Query(5, ge=1, description="Ignore thinly-covered zones"),
    dedup: bool = Query(True, description="Count unique (deduped) projects only"),
    limit: int = Query(15, ge=1, le=100),
    session: Session = Depends(get_session),
) -> WhitespaceResponse:
    """Rank zones by opportunity: high value (median price) + low competition
    (few developers). A directional proxy — true whitespace also needs a demand
    signal (absorption velocity), which arrives once snapshot history exists."""
    median = func.percentile_cont(0.5).within_group(Project.min_price.asc())
    stmt = _scoped(
        select(
            Area.name,
            Area.city,
            func.count(Project.id).label("projects"),
            func.count(func.distinct(Project.developer_id)).label("developers"),
            median.label("median_price"),
        )
        .join(Project, Project.area_id == Area.id)
        .group_by(Area.id, Area.name, Area.city)
        .having(func.count(Project.id) >= min_projects),
        source,
        None,
        dedup,
    )
    rows = session.execute(stmt).all()
    if not rows:
        return WhitespaceResponse(source=source, note="No zones met the threshold.", results=[])

    dev_vals = [r.developers for r in rows]
    price_vals = [float(r.median_price or 0) for r in rows]
    d_lo, d_hi = min(dev_vals), max(dev_vals)
    p_lo, p_hi = min(price_vals), max(price_vals)

    scored: list[WhitespaceRow] = []
    for name, city, projects, developers, median_price in rows:
        crowd = _norm(developers, d_lo, d_hi)          # 0 = fewest rivals
        value = _norm(float(median_price or 0), p_lo, p_hi)  # 1 = priciest
        # Weight competition more than value — whitespace is about open lanes.
        score = round(0.6 * (1 - crowd) + 0.4 * value, 2)
        label = "low" if crowd < 0.33 else "medium" if crowd < 0.66 else "high"
        scored.append(
            WhitespaceRow(
                zone=name,
                city=city,
                projects=projects,
                developers=developers,
                median_price=_round(median_price),
                competition=label,
                opportunity_score=score,
            )
        )

    scored.sort(key=lambda r: r.opportunity_score, reverse=True)
    return WhitespaceResponse(
        source=source,
        note="opportunity_score blends low competition (60%) + price level (40%); directional, not a demand guarantee.",
        results=scored[:limit],
    )


# Down-payment % lives in different places per source: Nawy nests it under
# developerPlan, Property Finder puts it at the top level. Coalesce both.
def _down_payment():
    return func.coalesce(
        cast(Project.raw["developerPlan"]["downPaymentPercentage"].astext, Float),
        cast(Project.raw["downPaymentPercentage"].astext, Float),
    )


def _installment_years():
    # Only Nawy exposes installment years on the listing.
    return cast(Project.raw["developerPlan"]["numberOfInstallmentYears"].astext, Float)


@router.get("/payment-terms", response_model=PaymentTermsResponse)
def payment_terms(
    source: str | None = Query(None, description="Filter by source name"),
    min_projects: int = Query(3, ge=1, description="Ignore developers with few priced projects"),
    dedup: bool = Query(True, description="Count unique (deduped) projects only"),
    limit: int = Query(20, ge=1, le=100),
    session: Session = Depends(get_session),
) -> PaymentTermsResponse:
    """Financing benchmark per developer — average down-payment % and
    installment years. Ordered easiest-first (lowest down payment)."""
    down_payment = _down_payment()
    years = _installment_years()

    stmt = _scoped(
        select(
            Developer.name,
            func.count(Project.id).label("projects"),
            func.avg(down_payment).label("avg_dp"),
            func.avg(years).label("avg_yrs"),
        )
        .join(Project, Project.developer_id == Developer.id)
        .where(down_payment.isnot(None))
        .group_by(Developer.id, Developer.name)
        .having(func.count(Project.id) >= min_projects)
        .order_by(func.avg(down_payment).asc()),
        source,
        None,
        dedup,
    ).limit(limit)

    results = [
        PaymentTermsRow(
            developer=name,
            projects=projects,
            avg_down_payment_pct=round(float(dp), 1) if dp is not None else None,
            avg_installment_years=round(float(yr), 1) if yr is not None else None,
        )
        for name, projects, dp, yr in session.execute(stmt).all()
    ]

    market = _scoped(
        select(func.avg(down_payment), func.avg(years)).where(down_payment.isnot(None)),
        source,
        None,
        dedup,
    )
    mdp, myr = session.execute(market).one()
    return PaymentTermsResponse(
        source=source,
        market_avg_down_payment_pct=round(float(mdp), 1) if mdp is not None else None,
        market_avg_installment_years=round(float(myr), 1) if myr is not None else None,
        results=results,
    )
