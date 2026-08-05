from pydantic import BaseModel

from models.clean import CleanStr


class Unit(BaseModel):
    """Units — an individual unit / property type within a project.

    project_source_id is the source's own id for the parent project; the db
    layer resolves it to our surrogate project_id foreign key. property_type is
    kept as the source's own label (see Project for why).
    """

    source: str
    source_id: str
    project_source_id: str | None = None

    property_type: CleanStr | None = None
    unit_area_sqm: float | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    price: float | None = None
    currency: CleanStr | None = None
    ready_by: str | None = None
    finishing: CleanStr | None = None
    raw: dict | None = None
