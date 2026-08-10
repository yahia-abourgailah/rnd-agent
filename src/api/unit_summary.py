"""Rolling a project's units up for the detail view.

Pure, so the arithmetic is checkable without a database. Every field treats
absence as absence: a project with no published price has no price, not a price
of zero, and a zero would sort to the top of any cheapest-first view.
"""

from collections import Counter
from dataclasses import dataclass, field


@dataclass(frozen=True)
class UnitRow:
    price: float | None
    area_sqm: float | None
    bedrooms: int | None
    property_type: str | None
    finishing: str | None


@dataclass
class UnitSummary:
    count: int = 0
    min_price: float | None = None
    max_price: float | None = None
    price_per_sqm_min: float | None = None
    price_per_sqm_max: float | None = None
    bedrooms: dict[int, int] = field(default_factory=dict)
    property_types: dict[str, int] = field(default_factory=dict)
    finishing: dict[str, int] = field(default_factory=dict)


def summarise_units(rows: list[UnitRow]) -> UnitSummary:
    """Roll units up, skipping the values a source has not published."""
    prices = [r.price for r in rows if r.price]
    per_sqm = [r.price / r.area_sqm for r in rows if r.price and r.area_sqm]

    return UnitSummary(
        count=len(rows),
        min_price=min(prices) if prices else None,
        max_price=max(prices) if prices else None,
        price_per_sqm_min=round(min(per_sqm), 2) if per_sqm else None,
        price_per_sqm_max=round(max(per_sqm), 2) if per_sqm else None,
        # Bedrooms count from zero: a studio is zero bedrooms, not a missing
        # value, so this tests against None rather than falsiness.
        bedrooms=dict(
            sorted(Counter(r.bedrooms for r in rows if r.bedrooms is not None).items())
        ),
        property_types=dict(
            Counter(r.property_type for r in rows if r.property_type).most_common()
        ),
        finishing=dict(Counter(r.finishing for r in rows if r.finishing).most_common()),
    )
