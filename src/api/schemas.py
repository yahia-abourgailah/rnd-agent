"""Response models for the read/insights API (the shapes the CRM consumes)."""

from pydantic import BaseModel


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


class QualityResponse(BaseModel):
    developers: DuplicateStat
    projects: DuplicateStat
    source_coverage: list[SourceCoverageRow]
    completeness: CompletenessStat
    note: str
