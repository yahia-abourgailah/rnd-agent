import re
import uuid
from collections.abc import Iterable
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from models.source import SourceType


class LaunchType(str, Enum):
    NEW_PROJECT = "new_project"
    NEW_PHASE = "new_phase"
    NEW_UNIT_TYPE = "new_unit_type"
    REPRICING = "repricing"


class PropertyType(str, Enum):
    """The single vocabulary for property types across every write path.

    Sources spell these their own way ("Twinhouse", "Twin House", "twin_house").
    Anything writing a property type must go through `from_source` so the
    relational catalogue and the extracted launches stay groupable together.
    """

    APARTMENT = "apartment"
    DUPLEX = "duplex"
    PENTHOUSE = "penthouse"
    TOWNHOUSE = "townhouse"
    TWIN_HOUSE = "twin_house"
    VILLA = "villa"
    CHALET = "chalet"
    COMMERCIAL = "commercial"
    STUDIO = "studio"
    LOFT = "loft"
    CABIN = "cabin"

    @classmethod
    def from_source(cls, raw: str | None) -> "PropertyType | None":
        """Map a source's spelling onto the canonical value, or None if unknown."""
        if not raw:
            return None
        key = re.sub(r"[\s\-_]+", "", str(raw).strip().lower())
        return _PROPERTY_TYPE_BY_KEY.get(key)


_PROPERTY_TYPE_BY_KEY = {
    re.sub(r"[\s\-_]+", "", member.value): member for member in PropertyType
} | {
    "twinhouse": PropertyType.TWIN_HOUSE,
    "twinvilla": PropertyType.TWIN_HOUSE,
    "standalonevilla": PropertyType.VILLA,
    "standalone": PropertyType.VILLA,
    "serviced apartment".replace(" ", ""): PropertyType.APARTMENT,
    "office": PropertyType.COMMERCIAL,
    "retail": PropertyType.COMMERCIAL,
    "clinic": PropertyType.COMMERCIAL,
    "shop": PropertyType.COMMERCIAL,
}


def canonical_property_type(raw: str | None) -> str | None:
    """Canonical spelling for one property type.

    Known types map onto the enum's value. Unknown ones are kept in the same
    shape (lowercase, underscore-separated) rather than dropped — a source's
    vocabulary is wider than the enum, and losing a real project over an
    unmapped type is worse than carrying a value the enum doesn't name yet.
    """
    if not raw:
        return None
    known = PropertyType.from_source(raw)
    if known is not None:
        return known.value
    return re.sub(r"[\s\-]+", "_", str(raw).strip().lower()) or None


def normalize_property_types(raw_types: Iterable[str | None]) -> list[str]:
    """Canonicalise and de-duplicate a source's property-type list."""
    seen: dict[str, None] = {}
    for raw in raw_types:
        canonical = canonical_property_type(raw)
        if canonical is not None:
            seen.setdefault(canonical, None)
    return sorted(seen)


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

    # Set by the Phase 2 backfill once this launch is matched to a canonical
    # project row (our generated UUID). None before then — the flat pipeline
    # produces launches without needing a project to exist yet.
    project_id: uuid.UUID | None = None

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
