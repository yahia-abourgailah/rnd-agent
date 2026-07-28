import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from launch_intel.db.engine import session_scope
from launch_intel.db.tables import (
    Area as AreaRow,
    Availability as AvailabilityRow,
    Developer as DeveloperRow,
    FetchLog,
    LaunchRow,
    Project as ProjectRow,
    RawContent,
    Source as SourceRow,
    Unit as UnitRow,
)
from launch_intel.models import (
    Area,
    Availability,
    ContentType,
    Developer,
    Launch,
    Project,
    RawPage,
    Unit,
)
from launch_intel.watch.change_detector import hash_content


def store_fetch(page: RawPage, source_name: str, content_hash: str, changed: bool) -> None:
    """Persist a fetched payload and log the fetch.

    Called for EVERY fetch, changed or not — an unchanged crawl costs one
    small log row, and the content itself is stored only once per hash.
    """
    with session_scope() as session:
        session.execute(
            insert(RawContent)
            .values(
                content_hash=content_hash,
                content=page.content,
                content_type=page.content_type.value,
                byte_size=len(page.content.encode("utf-8")),
                first_stored_at=datetime.now(timezone.utc),
            )
            .on_conflict_do_nothing(index_elements=["content_hash"])
        )
        session.add(
            FetchLog(
                source_name=source_name,
                url=page.url,
                content_hash=content_hash,
                fetched_at=page.fetched_at,
                changed=changed,
            )
        )


def latest_hash_for(url: str) -> str | None:
    """What change detection compares against — replaces the JSON state file."""
    with session_scope() as session:
        return session.scalar(
            select(FetchLog.content_hash)
            .where(FetchLog.url == url)
            .order_by(FetchLog.fetched_at.desc())
            .limit(1)
        )


def save_launches(launches: list[Launch]) -> int:
    """Persist extracted launches, storing each one's source text once.

    Every launch carries its full raw_content, and a page's worth of launches
    all share the same text — so the payload is upserted by hash and the rows
    reference it. 24 launches from one page cost one raw_content row, not 24
    copies of the same 6KB.
    """
    with session_scope() as session:
        for launch in launches:
            content_hash = hash_content(launch.raw_content)
            session.execute(
                insert(RawContent)
                .values(
                    content_hash=content_hash,
                    content=launch.raw_content,
                    content_type=ContentType.JSON.value
                    if launch.raw_content.lstrip().startswith(("{", "["))
                    else ContentType.HTML.value,
                    byte_size=len(launch.raw_content.encode("utf-8")),
                    first_stored_at=datetime.now(timezone.utc),
                )
                .on_conflict_do_nothing(index_elements=["content_hash"])
            )
            data = launch.model_dump(mode="json", exclude={"raw_content"})
            data["property_types"] = [str(t) for t in data["property_types"]]
            session.add(LaunchRow(**data, raw_content_hash=content_hash))
    return len(launches)


# --------------------------------------------------------------------------- #
# Relational backfill (developers, areas, projects, units, availability).
#
# IDENTITY: every row's `id` is a UUID WE generate. `external_ref` ("nawy:1198")
# is the ORIGIN's identifier, kept only so a re-sync can find a record it already
# stored. Each entity upserts on UNIQUE(external_ref) — re-running syncs in place
# instead of duplicating. Upserts RETURN (id, external_ref) so the caller can
# resolve foreign keys (our UUIDs) for the next stage.
# --------------------------------------------------------------------------- #
_UPSERT_CHUNK = 500


def external_ref(source: str, source_id: str) -> str:
    """The origin's identifier in "source:source_id" form (e.g. "nawy:1198")."""
    return f"{source}:{source_id}"


def source_id_map() -> dict[str, int]:
    """{source name -> registry id}, e.g. {"nawy": 1}. Used to resolve each
    entity's provenance to its sources.id foreign key."""
    with session_scope() as session:
        return dict(session.execute(select(SourceRow.name, SourceRow.id)).all())


def _upsert_entities(rows: list[dict], table, update_cols: list[str]) -> dict[str, uuid.UUID]:
    """Bulk upsert entity rows; return {external_ref: our generated UUID}.

    Each row is stamped with a fresh UUID for the INSERT case; on conflict the
    existing row keeps its UUID (id is not in update_cols) and RETURNING hands
    back whichever id actually persisted.
    """
    if not rows:
        return {}
    # Postgres refuses to update the same conflict target twice in one statement,
    # so collapse duplicate external_ref rows first (last one wins), and give
    # each a candidate id for the insert path.
    deduped: dict[str, dict] = {}
    for r in rows:
        r.setdefault("id", uuid.uuid4())
        deduped[r["external_ref"]] = r
    unique_rows = list(deduped.values())

    id_map: dict[str, uuid.UUID] = {}
    with session_scope() as session:
        for start in range(0, len(unique_rows), _UPSERT_CHUNK):
            chunk = unique_rows[start : start + _UPSERT_CHUNK]
            stmt = insert(table).values(chunk)
            stmt = stmt.on_conflict_do_update(
                index_elements=["external_ref"],
                set_={c: stmt.excluded[c] for c in update_cols},
            ).returning(table.id, table.external_ref)
            for row_id, ref in session.execute(stmt).all():
                id_map[ref] = row_id
    return id_map


def upsert_developers(developers: list[Developer]) -> dict[str, uuid.UUID]:
    now = datetime.now(timezone.utc)
    smap = source_id_map()
    rows = [
        {
            "source_id": smap[d.source],
            "external_ref": external_ref(d.source, d.source_id),
            "name": d.name,
            "slug": d.slug,
            "logo_url": d.logo_url,
            "description": d.description,
            "projects_count": d.projects_count,
            "raw": d.raw,
            "first_seen_at": now,
            "last_synced_at": now,
        }
        for d in developers
    ]
    return _upsert_entities(
        rows,
        DeveloperRow,
        ["name", "slug", "logo_url", "description", "projects_count", "raw", "last_synced_at"],
    )


def upsert_areas(areas: list[Area]) -> dict[str, uuid.UUID]:
    now = datetime.now(timezone.utc)
    smap = source_id_map()
    rows = [
        {
            "source_id": smap[a.source],
            "external_ref": external_ref(a.source, a.source_id),
            "name": a.name,
            "slug": a.slug,
            "city": a.city,
            "raw": a.raw,
            "last_synced_at": now,
        }
        for a in areas
    ]
    return _upsert_entities(
        rows, AreaRow, ["name", "slug", "city", "raw", "last_synced_at"]
    )


def upsert_projects(
    projects: list[Project],
    dev_map: dict[str, uuid.UUID],
    area_map: dict[str, uuid.UUID],
) -> dict[str, uuid.UUID]:
    now = datetime.now(timezone.utc)
    smap = source_id_map()
    rows = [
        {
            "source_id": smap[p.source],
            "external_ref": external_ref(p.source, p.source_id),
            "name": p.name,
            "slug": p.slug,
            "developer_id": dev_map.get(external_ref(p.source, p.developer_source_id))
            if p.developer_source_id
            else None,
            "area_id": area_map.get(external_ref(p.source, p.area_source_id))
            if p.area_source_id
            else None,
            "min_price": p.min_price,
            "currency": p.currency,
            "property_types": p.property_types,
            "is_launch": p.is_launch,
            "delivery_date": p.delivery_date,
            "image_url": p.image_url,
            "description": p.description,
            "raw": p.raw,
            "first_seen_at": now,
            "last_synced_at": now,
        }
        for p in projects
    ]
    return _upsert_entities(
        rows,
        ProjectRow,
        [
            "name",
            "slug",
            "developer_id",
            "area_id",
            "min_price",
            "currency",
            "property_types",
            "is_launch",
            "delivery_date",
            "image_url",
            "description",
            "raw",
            "last_synced_at",
        ],
    )


def upsert_units(units: list[Unit], project_map: dict[str, uuid.UUID]) -> int:
    now = datetime.now(timezone.utc)
    smap = source_id_map()
    rows = [
        {
            "source_id": smap[u.source],
            "external_ref": external_ref(u.source, u.source_id),
            "project_id": project_map.get(external_ref(u.source, u.project_source_id))
            if u.project_source_id
            else None,
            "property_type": u.property_type,
            "unit_area_sqm": u.unit_area_sqm,
            "bedrooms": u.bedrooms,
            "bathrooms": u.bathrooms,
            "price": u.price,
            "currency": u.currency,
            "ready_by": u.ready_by,
            "finishing": u.finishing,
            "raw": u.raw,
            "last_synced_at": now,
        }
        for u in units
    ]
    _upsert_entities(
        rows,
        UnitRow,
        [
            "project_id",
            "property_type",
            "unit_area_sqm",
            "bedrooms",
            "bathrooms",
            "price",
            "currency",
            "ready_by",
            "finishing",
            "raw",
            "last_synced_at",
        ],
    )
    return len({r["external_ref"] for r in rows})


def save_availability(
    snapshots: list[Availability], project_map: dict[str, uuid.UUID]
) -> int:
    """Insert availability snapshots (append-only — each is a point in time)."""
    smap = source_id_map()
    saved = 0
    with session_scope() as session:
        for snap in snapshots:
            project_id = project_map.get(external_ref(snap.source, snap.project_source_id))
            if project_id is None:
                continue
            session.add(
                AvailabilityRow(
                    project_id=project_id,
                    source_id=smap[snap.source],
                    snapshot_at=snap.snapshot_at,
                    total_units=snap.total_units,
                    available_units=snap.available_units,
                    min_price=snap.min_price,
                    max_price=snap.max_price,
                    price_per_sqm_min=snap.price_per_sqm_min,
                    price_per_sqm_max=snap.price_per_sqm_max,
                    unit_types=snap.unit_types,
                    delivery_range=snap.delivery_range,
                )
            )
            saved += 1
    return saved


def entity_counts() -> dict[str, int]:
    """Row counts for the relational tables — used by the backfill summary."""
    tables = {
        "sources": SourceRow,
        "developers": DeveloperRow,
        "areas": AreaRow,
        "projects": ProjectRow,
        "units": UnitRow,
        "availability": AvailabilityRow,
    }
    with session_scope() as session:
        return {
            name: session.scalar(select(func.count()).select_from(table))
            for name, table in tables.items()
        }