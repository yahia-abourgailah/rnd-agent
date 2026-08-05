import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Without none_as_null, SQLAlchemy writes Python None into a JSONB column as
# JSON `null` rather than SQL NULL. That makes `raw IS NULL` never match, and it
# defeats the COALESCE in the entity upsert, which can then blank a stored
# payload with an incoming "no opinion".
_Json = JSONB(none_as_null=True)


class Base(DeclarativeBase):
    pass


class RawContent(Base):
    """Content-addressed page storage: identical content is stored once.

    This is what makes re-running extraction after a prompt change possible —
    competitor sites overwrite their pages, so uncaptured content is gone
    permanently.
    """

    __tablename__ = "raw_content"

    content_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(String(16), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    first_stored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FetchLog(Base):
    """One row per fetch, whether or not the content changed."""

    __tablename__ = "fetch_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_name: Mapped[str] = mapped_column(String(100), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(
        ForeignKey("raw_content.content_hash"), nullable=False
    )
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    changed: Mapped[bool] = mapped_column(nullable=False)

    # change detection asks "latest hash for this url" on every crawl
    __table_args__ = (Index("ix_fetch_log_url_fetched_at", "url", "fetched_at"),)


class LaunchRow(Base):
    """Mirrors models/launch.py. Keep the two in step — the Pydantic model is
    the contract; this is just how it's persisted."""

    __tablename__ = "launches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)

    # Links this launch to its canonical project (Phase 2 backfill fills it in).
    # Nullable so the existing flat pipeline keeps working before any project
    # rows exist — a launch is still valid without a resolved project.
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"))

    developer: Mapped[str | None] = mapped_column(String(255))
    project_name: Mapped[str] = mapped_column(String(255), nullable=False)
    launch_type: Mapped[str] = mapped_column(String(32), nullable=False)
    location_raw: Mapped[str | None] = mapped_column(Text)
    zone: Mapped[str | None] = mapped_column(String(255))
    property_types: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    unit_sizes: Mapped[dict | None] = mapped_column(_Json)
    price_from: Mapped[float | None] = mapped_column(Float)
    price_per_sqm: Mapped[float | None] = mapped_column(Float)
    payment_plan: Mapped[str | None] = mapped_column(Text)
    delivery_date: Mapped[str | None] = mapped_column(String(64))
    availability: Mapped[str | None] = mapped_column(String(255))

    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    # Reference, not a copy: the payload lives once in raw_content.
    raw_content_hash: Mapped[str] = mapped_column(
        ForeignKey("raw_content.content_hash"), nullable=False
    )

    __table_args__ = (Index("ix_launches_project_developer", "project_name", "developer"),)


# ---------------------------------------------------------------------------
# Relational model (the mentor's ask: Developers Profile, Projects, Units,
# Current Launches, Availability — connected by foreign keys).
#
# IDENTITY: the primary key `id` is a UUID WE generate — it is our own,
# independent of any source. Foreign keys reference these UUIDs.
#
# `external_ref` holds the ORIGIN's identifier in "source:source_id" form
# (e.g. "nawy:1198"). It is a reference only — never the identity — and exists
# so a re-sync can recognise a record it has already stored and UPDATE it
# instead of inserting a duplicate. Uniqueness is enforced on `external_ref`.
#
# PROVENANCE: which origin a row came from is normalised into the `sources`
# registry (nawy = 1, property_finder = 2, ...). Every entity references it via
# `source_id` FK rather than repeating the source name as a string.
# ---------------------------------------------------------------------------


class Source(Base):
    """Registry of data sources — one row per origin site, with a small,
    human-friendly id assigned by us (nawy = 1, property_finder = 2, ...).
    `is_active` marks which sources are actually being ingested today."""

    __tablename__ = "sources"

    # Deliberately not autoincrement: the registry is small and hand-curated,
    # so ids are assigned explicitly and stay stable/readable.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)  # machine slug, e.g. "nawy"
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    base_url: Mapped[str | None] = mapped_column(Text)
    source_type: Mapped[str | None] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (UniqueConstraint("name", name="uq_sources_name"),)


class Developer(Base):
    """Developers Profile — one real-estate developer/company."""

    __tablename__ = "developers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), nullable=False)
    external_ref: Mapped[str] = mapped_column(String(128), nullable=False)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str | None] = mapped_column(String(255))
    logo_url: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    projects_count: Mapped[int | None] = mapped_column(Integer)

    # Full source payload, kept verbatim so we can re-derive fields later.
    raw: Mapped[dict | None] = mapped_column(_Json)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Dedup: when this row is a duplicate of another (e.g. "Sodic" from Property
    # Finder ≡ "SODIC" from Nawy), points at the canonical developer. NULL means
    # this row IS canonical / standalone. Set by dedup/resolver.py.
    canonical_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("developers.id"))

    __table_args__ = (
        UniqueConstraint("external_ref", name="uq_developers_ref"),
        Index("ix_developers_canonical_id", "canonical_id"),
    )


class Area(Base):
    """A zone / area (e.g. New Cairo, North Coast)."""

    __tablename__ = "areas"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), nullable=False)
    external_ref: Mapped[str] = mapped_column(String(128), nullable=False)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(255))

    raw: Mapped[dict | None] = mapped_column(_Json)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    canonical_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("areas.id"))

    __table_args__ = (
        UniqueConstraint("external_ref", name="uq_areas_ref"),
        Index("ix_areas_canonical_id", "canonical_id"),
    )


class Project(Base):
    """Projects (compounds) — the hub table. Belongs to one developer and one
    area; owns many units, launches and availability snapshots."""

    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), nullable=False)
    external_ref: Mapped[str] = mapped_column(String(128), nullable=False)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str | None] = mapped_column(String(255))

    # Nullable FKs: a source may list a project before we've ingested its
    # developer/area, and we'd rather store the project than drop it.
    developer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("developers.id"))
    area_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("areas.id"))

    min_price: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str | None] = mapped_column(String(8))
    property_types: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    # True when this project is currently a "launch" (recently on market).
    is_launch: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    delivery_date: Mapped[str | None] = mapped_column(String(64))
    image_url: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)

    raw: Mapped[dict | None] = mapped_column(_Json)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Dedup: points at the canonical project when this row is the same real
    # project reported by another source. NULL = canonical / standalone.
    canonical_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"))

    __table_args__ = (
        UniqueConstraint("external_ref", name="uq_projects_ref"),
        Index("ix_projects_developer_id", "developer_id"),
        Index("ix_projects_area_id", "area_id"),
        Index("ix_projects_is_launch", "is_launch"),
        Index("ix_projects_source_id", "source_id"),
        Index("ix_projects_canonical_id", "canonical_id"),
    )


class Unit(Base):
    """Units — an individual unit/property type within a project."""

    __tablename__ = "units"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), nullable=False)
    external_ref: Mapped[str] = mapped_column(String(128), nullable=False)

    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"))

    property_type: Mapped[str | None] = mapped_column(String(64))
    unit_area_sqm: Mapped[float | None] = mapped_column(Float)
    bedrooms: Mapped[int | None] = mapped_column(Integer)
    bathrooms: Mapped[int | None] = mapped_column(Integer)
    price: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str | None] = mapped_column(String(8))
    ready_by: Mapped[str | None] = mapped_column(String(32))
    finishing: Mapped[str | None] = mapped_column(String(64))
    sale_type: Mapped[str | None] = mapped_column(String(16))

    raw: Mapped[dict | None] = mapped_column(_Json)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("external_ref", name="uq_units_ref"),
        Index("ix_units_project_id", "project_id"),
        Index("ix_units_source_id", "source_id"),
    )


class Availability(Base):
    """Availability on overall projects — a time-stamped inventory rollup per
    project, so R&D can track how availability/pricing moves over time."""

    __tablename__ = "availability"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), nullable=False)

    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    total_units: Mapped[int | None] = mapped_column(Integer)
    available_units: Mapped[int | None] = mapped_column(Integer)
    min_price: Mapped[float | None] = mapped_column(Float)
    max_price: Mapped[float | None] = mapped_column(Float)
    price_per_sqm_min: Mapped[float | None] = mapped_column(Float)
    price_per_sqm_max: Mapped[float | None] = mapped_column(Float)
    unit_types: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    delivery_range: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (Index("ix_availability_project_snapshot", "project_id", "snapshot_at"),)
