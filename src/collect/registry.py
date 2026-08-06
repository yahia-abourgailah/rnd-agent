"""Source name -> collector class. Adding a source is one line here.

Keyed on each collector's own `name` rather than a literal, so the registry key
and the collector cannot drift apart — a mismatch would run one source under
another's sanity floor.
"""

from collect.nawy import NawyCollector
from collect.property_finder import PropertyFinderCollector

COLLECTOR_REGISTRY: dict[str, type] = {
    NawyCollector.name: NawyCollector,
    PropertyFinderCollector.name: PropertyFinderCollector,
}


def get_collector_class(name: str) -> type:
    try:
        return COLLECTOR_REGISTRY[name]
    except KeyError:
        raise ValueError(
            f"No collector registered for {name!r}. "
            f"Known sources: {sorted(COLLECTOR_REGISTRY)}"
        ) from None
