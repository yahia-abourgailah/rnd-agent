"""The contract between a source and the rest of the pipeline.

A collector fetches and maps. It returns cleaned contract models, so every
source lands in one vocabulary and downstream code never learns whether a JSON
API or an HTML parser produced a row.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from models import Area, Developer, Project, Unit

_ENTITIES = ("developers", "areas", "projects", "units")
_EMPTY = (None, "", [])


@dataclass
class CollectionResult:
    """One source's output for one run."""

    source: str
    developers: list[Developer]
    areas: list[Area]
    projects: list[Project]
    units: list[Unit]
    fetched_at: datetime

    def counts(self) -> dict[str, int]:
        return {entity: len(getattr(self, entity)) for entity in _ENTITIES}

    def field_coverage(self, entity: str) -> dict[str, float]:
        """Share of rows carrying a non-empty value, per field."""
        rows = getattr(self, entity)
        if not rows:
            return {}
        return {
            field: sum(1 for row in rows if getattr(row, field) not in _EMPTY) / len(rows)
            for field in type(rows[0]).model_fields
        }


class SourceCollector(Protocol):
    """What every source implements.

    `min_projects` is the sanity floor: a run returning fewer aborts without
    writing, because a truncated scrape that persists is worse than one that
    raises — the partial data looks like a real result and nothing downstream
    can tell.
    """

    name: str
    min_projects: int

    async def collect(self) -> CollectionResult: ...
