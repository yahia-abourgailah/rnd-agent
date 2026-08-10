"""Deciding whether a price move is worth reporting.

Nawy's minPrice depends on live inventory, so it shifts between crawls when
nothing has launched. A feed built on raw deltas would fire constantly and be
ignored within a week, so a move must clear a threshold *and* still be heading
the same way at the latest observation — a spike that has already reverted is
inventory noise, not a repricing.

Pure on purpose: no session, no ORM. The rule that decides whether the feed is
trustworthy is testable with hand-built inputs.
"""

from dataclasses import dataclass
from datetime import datetime

Snapshot = tuple[datetime, float | None]


@dataclass(frozen=True)
class PriceChange:
    from_price: float
    to_price: float
    change_pct: float
    observed_at: datetime


def detect_price_change(
    snapshots: list[Snapshot], min_change_pct: float
) -> PriceChange | None:
    """The material move across `snapshots`, oldest first, or None.

    Snapshots carrying no price are ignored rather than treated as zero: an
    unpublished price is absent, and a price appearing for the first time is a
    new entrant, which the feed reports separately.
    """
    priced = [(at, price) for at, price in snapshots if price]
    if len(priced) < 2:
        return None

    (_, first), (observed_at, last) = priced[0], priced[-1]
    if not first:
        return None

    change_pct = (last - first) / first * 100
    if abs(change_pct) < min_change_pct:
        return None

    # The most recent step must agree with the overall direction, or the move
    # has already turned and the headline figure is stale.
    previous = priced[-2][1]
    if (last - previous) * (last - first) < 0:
        return None

    return PriceChange(
        from_price=first, to_price=last, change_pct=change_pct, observed_at=observed_at
    )
