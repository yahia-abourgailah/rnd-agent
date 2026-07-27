from datetime import datetime

from pydantic import BaseModel, Field


class Availability(BaseModel):
    """Availability on overall projects — a point-in-time inventory rollup for
    one project, computed by aggregating its units."""

    project_source_id: str  # the source's id for the project this rolls up
    snapshot_at: datetime
    total_units: int | None = None
    available_units: int | None = None
    min_price: float | None = None
    max_price: float | None = None
    price_per_sqm_min: float | None = None
    price_per_sqm_max: float | None = None
    unit_types: list[str] = Field(default_factory=list)
    delivery_range: str | None = None
