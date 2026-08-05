from pydantic import BaseModel

from models.clean import CleanStr


class Area(BaseModel):
    """A zone / area (e.g. New Cairo, North Coast)."""

    source: str
    source_id: str
    name: CleanStr
    slug: CleanStr | None = None
    city: CleanStr | None = None
    raw: dict | None = None
