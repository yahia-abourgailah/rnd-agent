"""Request/response models for the read/insights API (the shapes the CRM consumes)."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints


class MarketShareRow(BaseModel):
    developer_id: str
    developer: str
    projects: int
    market_share_pct: float


class MarketShareResponse(BaseModel):
    source: str | None
    zone: str | None
    total_projects: int
    developer_count: int
    results: list[MarketShareRow]


class ZoneRow(BaseModel):
    zone: str
    city: str | None
    projects: int
    developers: int
    launches: int
    min_price: float | None
    median_price: float | None
    max_price: float | None


class ZonesResponse(BaseModel):
    source: str | None
    results: list[ZoneRow]


class PriceBracketRow(BaseModel):
    bracket: str
    projects: int
    pct: float


class PriceDistributionResponse(BaseModel):
    source: str | None
    total_projects: int
    results: list[PriceBracketRow]


class PropertyTypeRow(BaseModel):
    property_type: str
    projects: int


class PropertyMixResponse(BaseModel):
    source: str | None
    results: list[PropertyTypeRow]


class DeliveryYearRow(BaseModel):
    year: str
    projects: int


class DeliveryPipelineResponse(BaseModel):
    source: str | None
    results: list[DeliveryYearRow]


class WhitespaceRow(BaseModel):
    zone: str
    city: str | None
    projects: int
    developers: int
    median_price: float | None
    competition: str  # "low" | "medium" | "high"
    opportunity_score: float  # 0..1 — higher = more value, less competition


class WhitespaceResponse(BaseModel):
    source: str | None
    note: str
    results: list[WhitespaceRow]


class PaymentTermsRow(BaseModel):
    developer: str
    projects: int
    avg_down_payment_pct: float | None
    avg_installment_years: float | None


class PaymentTermsResponse(BaseModel):
    source: str | None
    market_avg_down_payment_pct: float | None
    market_avg_installment_years: float | None
    results: list[PaymentTermsRow]


class DuplicateStat(BaseModel):
    total: int
    unique: int
    duplicates: int
    duplicate_rate_pct: float


class SourceCoverageRow(BaseModel):
    source: str
    projects: int
    shared_with_other_source: int
    unique_to_source: int


class CompletenessStat(BaseModel):
    projects: int
    with_price_pct: float
    with_developer_pct: float
    with_area_pct: float
    with_delivery_date_pct: float


class SourceOverlapRow(BaseModel):
    """How much of a source's catalogue another source also reports. Both sides
    of a duplicate pair count, so the source that wins canonical does not look
    as though it contributes everything alone."""

    source: str
    projects: int
    shared: int
    unique: int


class QualityResponse(BaseModel):
    developers: DuplicateStat
    projects: DuplicateStat
    source_coverage: list[SourceCoverageRow]
    source_overlap: list[SourceOverlapRow]
    completeness: CompletenessStat
    note: str


class ChatRequest(BaseModel):
    message: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=2000),
    ]
    conversation_id: str | None = Field(
        default=None,
        description="Omit to start a new conversation; echo back to continue one.",
    )


class ChatResponse(BaseModel):
    reply: str
    conversation_id: str


class LaunchEventRow(BaseModel):
    """One thing that changed. `kind` decides which optional fields are set."""

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


class LaunchesResponse(BaseModel):
    since: datetime
    min_change_pct: float
    #: How many collection runs the window covers. Price movement needs at
    #: least two, so this tells a caller whether an empty feed means "nothing
    #: moved" or "not enough history yet".
    snapshot_runs_in_window: int
    total: int
    results: list[LaunchEventRow]
