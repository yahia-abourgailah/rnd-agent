from pydantic import BaseModel, Field


class Project(BaseModel):
    """Projects (compounds) — the hub entity, linked to a developer and an area.

    developer_source_id / area_source_id carry the source's own ids for the
    related entities. The db layer resolves those to our surrogate developer_id /
    area_id foreign keys once developers and areas are loaded.

    property_types are stored as the source's own labels ("Twinhouse",
    "Administrative", ...) rather than forced through the PropertyType enum:
    Nawy's vocabulary is wider than the enum (Known Issue #5), and the backfill
    must never drop a real project over an unmapped type.
    """

    source: str
    source_id: str
    name: str
    slug: str | None = None

    developer_source_id: str | None = None
    area_source_id: str | None = None

    min_price: float | None = None
    currency: str | None = None
    property_types: list[str] = Field(default_factory=list)
    is_launch: bool = False
    delivery_date: str | None = None
    image_url: str | None = None
    description: str | None = None
    raw: dict | None = None
