import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from launch_intel.models.source import SourceType


class LaunchType(str, Enum):
    NEW_PROJECT = "new_project"
    NEW_PHASE = "new_phase"
    NEW_UNIT_TYPE = "new_unit_type"
    REPRICING = "repricing"


class PropertyType(str, Enum):
    APARTMENT = "apartment"
    DUPLEX = "duplex"
    PENTHOUSE = "penthouse"
    TOWNHOUSE = "townhouse"
    TWIN_HOUSE = "twin_house"
    VILLA = "villa"
    CHALET = "chalet"
    COMMERCIAL = "commercial"
    STUDO = "studio"
    LOFT = "loft"
    CABIN = "cabin"


class SizeRange(BaseModel):
    """Unit size range in square meters, as reported by the source."""

    min_sqm: float | None = None
    max_sqm: float | None = None


class Launch(BaseModel):
    """
    The shared contract for a single detected competitor launch.

    Produced by extract/extractor.py from raw_content. Consumed downstream by
    dedup (Phase 2), notify (Phase 3), and the API/dashboard layer.

    Fields are nullable wherever a source may plausibly omit that data —
    only the fields we cannot function without (project_name, launch_type,
    source_url, source_type, raw_content, first_seen_at, confidence) are required.
    """

    # Generated client-side at extraction time (no DB row exists yet in this
    # phase). SourceEvidence.launch_id must be set to this same value by
    # whatever code constructs both objects together.
    id: uuid.UUID = Field(default_factory=uuid.uuid4)

    developer: str | None = None
    project_name: str
    launch_type: LaunchType
    location_raw: str | None = None
    zone: str | None = None
    property_types: list[PropertyType] = Field(default_factory=list)
    unit_sizes: SizeRange | None = None
    price_from: float | None = None
    price_per_sqm: float | None = None
    payment_plan: str | None = None
    # Kept as raw text on purpose — sources report deadlines inconsistently
    # ("Q4 2027", "2028", "under construction"). TODO(phase2+): consider a
    # structured delivery_year/delivery_quarter if downstream needs sorting.
    delivery_date: str | None = None
    availability: str | None = None

    source_url: str
    # Copied through from the SourceConfig that produced this launch, so a
    # Launch record is self-describing without a join back to SourceConfig.
    source_type: SourceType
    first_seen_at: datetime

    confidence: float = Field(ge=0.0, le=1.0)
    raw_content: str  # retained verbatim so extraction can be re-run later
