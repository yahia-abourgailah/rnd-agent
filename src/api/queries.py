"""Scoping shared by every endpoint that reads the catalogue.

One definition of "the deduped market" and one definition of "a zone", so two
endpoints cannot drift into disagreeing about what they mean.
"""

from sqlalchemy import case, func, or_
from sqlalchemy.orm import aliased

from db.tables import Area, Project, Source

#: The canonical side of an area's self-link. A duplicate area points at the row
#: another source's spelling was merged into.
CanonicalArea = aliased(Area, name="canonical_area")


def canonical_area_name():
    """The zone's real name, whichever source's spelling a project is filed
    under.

    Areas are deduplicated across sources but nothing resolved that at read
    time, so "New Cairo" and "New Cairo City" counted as two zones and every
    zone figure was split between them.
    """
    return func.coalesce(CanonicalArea.name, Area.name)


def canonical_area_city():
    """The zone's city, taken from the canonical row even when that is NULL.

    Not COALESCE: a canonical area with no city is a real answer, not a missing
    one, so falling back to the duplicate's city splits the zone again. Nawy's
    "New Cairo" carries no city while Property Finder's "New Cairo City" says
    "Cairo", which produced two "New Cairo" rows of 383 and 140.
    """
    return case(
        (Area.canonical_id.isnot(None), CanonicalArea.city),
        else_=Area.city,
    )


def join_areas(stmt):
    """Join a Project-based statement to its area and that area's canonical."""
    return stmt.join(Area, Area.id == Project.area_id).outerjoin(
        CanonicalArea, CanonicalArea.id == Area.canonical_id
    )


def scoped(stmt, source: str | None, zone: str | None, dedup: bool = True):
    """Apply the shared dedup, source and zone filters to a Project query.

    `dedup=True` counts only canonical projects, so cross-source duplicates are
    not double-counted. A zone matches on the canonical name, and also on the
    area's own name so a caller holding an older spelling still finds rows
    rather than an empty result.
    """
    if dedup:
        stmt = stmt.where(Project.canonical_id.is_(None))
    if source:
        stmt = stmt.join(Source, Source.id == Project.source_id).where(
            Source.name == source
        )
    if zone:
        stmt = join_areas(stmt).where(
            or_(
                func.lower(canonical_area_name()) == zone.lower(),
                func.lower(Area.name) == zone.lower(),
            )
        )
    return stmt
