"""Canonicalisation for source-supplied values, applied at the model boundary.

Every write path — the LLM extractor and the no-LLM backfills, across every
source — goes through the same helpers here, so one column holds one format.
Cleaning used to live in each mapper, which is how "Modon " and "Modon" became
separate developers and how projects.delivery_date ended up holding both "2029"
(Nawy) and "2029-12-30" (Property Finder).
"""

import re
from typing import Annotated

from pydantic import BeforeValidator

_WHITESPACE = re.compile(r"\s+")
_YEAR = re.compile(r"(?:19|20)\d{2}")


def clean_text(value):
    """Collapse internal whitespace and trim; empty becomes None."""
    if not isinstance(value, str):
        return value
    cleaned = _WHITESPACE.sub(" ", value).strip()
    return cleaned or None


def delivery_year(value) -> str | None:
    """The canonical project-level delivery date: a 4-digit year.

    Sources report this as an int (20291230), an ISO date ("2029-12-30") or free
    text ("Q4 2029"). Year is the granularity every source can supply and the one
    the delivery-pipeline report reads; full precision stays in the row's `raw`.
    """
    if value in (None, ""):
        return None
    match = _YEAR.search(str(value))
    return match.group(0) if match else None


CleanStr = Annotated[str, BeforeValidator(clean_text)]
