from pydantic import BaseModel


class Area(BaseModel):
    """A zone / area (e.g. New Cairo, North Coast)."""

    source: str
    source_id: str
    name: str
    slug: str | None = None
    city: str | None = None
    raw: dict | None = None
