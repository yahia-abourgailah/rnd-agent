from pydantic import BaseModel, Field

from models.clean import CleanStr


class Project(BaseModel):
    """Projects (compounds) — the hub entity, linked to a developer and an area.

    developer_source_id / area_source_id carry the source's own ids for the
    related entities. The db layer resolves those to our surrogate developer_id /
    area_id foreign keys once developers and areas are loaded.

    property_types are canonicalised through `canonical_property_type`, which
    maps known spellings onto the PropertyType vocabulary ("Twinhouse" ->
    "twin_house") and keeps unknown ones in the same lowercase/underscore shape
    rather than forcing them through the enum: a source's vocabulary is wider
    than the enum (Known Issue #5), and the backfill must never drop a real
    project over an unmapped type.
    """

    source: str
    source_id: str
    name: CleanStr
    slug: CleanStr | None = None

    developer_source_id: str | None = None
    area_source_id: str | None = None

    min_price: float | None = None
    currency: CleanStr | None = None
    property_types: list[str] = Field(default_factory=list)
    is_launch: bool = False
    delivery_date: CleanStr | None = None
    image_url: str | None = None
    description: CleanStr | None = None
    raw: dict | None = None
