import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


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

    developer: Mapped[str | None] = mapped_column(String(255))
    project_name: Mapped[str] = mapped_column(String(255), nullable=False)
    launch_type: Mapped[str] = mapped_column(String(32), nullable=False)
    location_raw: Mapped[str | None] = mapped_column(Text)
    zone: Mapped[str | None] = mapped_column(String(255))
    property_types: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    unit_sizes: Mapped[dict | None] = mapped_column(JSONB)
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