from pydantic import BaseModel

from models.clean import CleanStr


class Developer(BaseModel):
    """Developers Profile — the shared contract for one developer/company.

    Source-facing: describes the data an adapter produces. Persistence bookkeeping
    (surrogate id, first_seen_at, last_synced_at) is added by the db layer.
    """

    source: str  # which site this came from, e.g. "nawy"
    source_id: str  # that site's own id for the developer
    name: CleanStr
    slug: CleanStr | None = None
    logo_url: str | None = None
    description: CleanStr | None = None
    projects_count: int | None = None
    raw: dict | None = None
