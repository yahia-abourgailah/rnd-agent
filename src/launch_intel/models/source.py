from enum import IntEnum, StrEnum

from pydantic import BaseModel, Field


class SourceTier(IntEnum):
    """Crawl priority / trust weighting for a source, not its content category."""

    TIER_1 = 1  # official developer sites — highest trust
    TIER_2 = 2  # major aggregators (Nawy, PropertyFinder, ...)
    TIER_3 = 3  # social media, forums, low-trust secondary sources


class SourceType(StrEnum):
    """What kind of site this is — independent of `tier` (trust/priority)."""

    DEVELOPER_SITE = "developer_site"
    AGGREGATOR = "aggregator"
    NEWS = "news"
    SOCIAL = "social"


class SourceConfig(BaseModel):
    """A single entry in config/sources.yaml — one adapter's crawl configuration."""

    name: str
    tier: SourceTier
    source_type: SourceType
    urls: list[str] = Field(min_length=1)
    crawl_frequency: str  # e.g. "*/30 * * * *" (cron) or "30m" (interval shorthand)
    adapter_name: str  # must match a BaseAdapter registered under watch/adapters/
