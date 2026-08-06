"""Backfill client for Property Finder Egypt (propertyfinder.eg).

Like Nawy, Property Finder is a Next.js app that server-renders its data into a
`__NEXT_DATA__` <script> tag — so we read structured JSON directly, no LLM. The
new-projects listing is paginated (?page=N); each project record carries its
developer and location inline, so developers and areas are derived from the
projects rather than fetched separately (Property Finder exposes no standalone
developer/area feed on this page).

Shape (per project, from searchResult.data.projects):
    id (uuid), title, developer{id,name,logoUrl}, location{id,fullName,...},
    startingPrice, priceRange{min,max}, propertyTypes[], deliveryDate,
    stockAvailability, images[]

Fails safe: a shape change yields no records rather than a crash.
"""

import json
import logging
import re
from datetime import UTC, datetime

from collect.base import CollectionResult, merge_by_source_id
from models import (
    Area,
    Developer,
    Project,
    delivery_year,
    normalize_property_types,
)
from watch.fetcher import Fetcher

logger = logging.getLogger(__name__)

SOURCE = "property_finder"

_LISTING_URL = "https://www.propertyfinder.eg/en/new-projects"
_NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)
_MAX_PAGES = 80  # safety stop; the feed reports ~56 pages
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(text: str) -> str:
    return _SLUG_RE.sub("-", text.strip().lower()).strip("-")


def _district_and_city(location: dict) -> tuple[str | None, str | None]:
    """Property Finder's location.fullName is a comma-separated hierarchy,
    e.g. "Giza,Sheikh Zayed City,Sheikh Zayed Compounds,Lake West". We group
    projects at DISTRICT level (2nd segment) to match Nawy's zone granularity —
    the specific location ids go too deep (down to the compound) to be useful
    zones. city is the top (governorate) segment."""
    parts = [p.strip() for p in (location.get("fullName") or "").split(",") if p.strip()]
    if not parts:
        return None, None
    city = parts[0]
    district = parts[1] if len(parts) >= 2 else parts[0]
    return district, city


# --------------------------------------------------------------------------- #
# Fetching (paginated __NEXT_DATA__)
# --------------------------------------------------------------------------- #
def _extract_projects(html: str) -> tuple[list[dict], int]:
    """Return (projects, total_pages) from one listing page's __NEXT_DATA__."""
    match = _NEXT_DATA_RE.search(html)
    if not match:
        return [], 0
    try:
        page_props = json.loads(match.group(1))["props"]["pageProps"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return [], 0
    search = page_props.get("searchResult") or {}
    projects = ((search.get("data") or {}).get("projects")) or []
    total_pages = ((search.get("meta") or {}).get("pagination") or {}).get("total") or 0
    return projects, total_pages


async def fetch_projects(fetcher: Fetcher, limit: int | None = None) -> list[dict]:
    """Walk the new-projects listing page by page, collecting raw project dicts.

    Uses fetcher.fetch_json purely as an HTTP GET (it returns the response text
    on `.content`); the page is HTML with embedded JSON, not a JSON endpoint.
    """
    collected: list[dict] = []
    for page_number in range(1, _MAX_PAGES + 1):
        resp = await fetcher.fetch_json(f"{_LISTING_URL}?page={page_number}")
        projects, total_pages = _extract_projects(resp.content)
        if not projects:
            break
        collected.extend(projects)
        if limit is not None and len(collected) >= limit:
            return collected[:limit]
        if total_pages and page_number >= total_pages:
            break
    return collected


# --------------------------------------------------------------------------- #
# Mapping (pure — unit-testable without network)
# --------------------------------------------------------------------------- #
#: constructionPhase values that mean the project is still coming to market.
_LAUNCH_PHASES = {"pre_launch", "launch", "under_construction", "off_plan"}


def _is_launch(raw: dict) -> bool:
    """Whether this project still counts as a launch.

    The feed is called "new-projects" but carries completed developments too —
    Mountain View Hyde Park sits there with constructionPhase "completed" and a
    2023 delivery date. Flagging the whole feed as launches inflated every
    launch count with projects that came to market years ago.
    """
    phase = (raw.get("constructionPhase") or "").strip().lower()
    if phase:
        return phase in _LAUNCH_PHASES
    return raw.get("salesPhase") is not None


def _slug_from_share_url(share_url: str | None) -> str | None:
    """The trailing slug of a share URL, matching what other sources store.

    shareUrl is a path ("/en/new-projects/palm-hills/palm-hills-phase-5"); the
    slug column holds a slug everywhere else, so store the last segment.
    """
    if not share_url:
        return None
    return share_url.rstrip("/").rsplit("/", 1)[-1] or None


def map_project(raw: dict) -> Project | None:
    if not raw.get("id") or not raw.get("title"):
        return None
    developer = raw.get("developer") or {}
    location = raw.get("location") or {}
    district, _city = _district_and_city(location)
    price_range = raw.get("priceRange") or {}
    price = raw.get("startingPrice") or price_range.get("min")
    images = raw.get("images") or []
    delivery = raw.get("deliveryDate") or ""
    return Project(
        source=SOURCE,
        source_id=str(raw["id"]),
        name=raw["title"],
        slug=_slug_from_share_url(raw.get("shareUrl")),
        developer_source_id=str(developer["id"]) if developer.get("id") else None,
        area_source_id=_slug(district) if district else None,
        min_price=float(price) if price else None,
        currency="EGP",  # Property Finder Egypt prices; no currency field in payload
        property_types=normalize_property_types(raw.get("propertyTypes") or []),
        is_launch=_is_launch(raw),
        delivery_date=delivery_year(delivery),
        image_url=images[0] if images else None,
        description=location.get("fullName"),
        raw=raw,
    )


def developers_from_projects(raws: list[dict]) -> list[Developer]:
    """Developer rows derived from the developer object inlined on each project."""
    seen: dict[str, Developer] = {}
    for raw in raws:
        dev = raw.get("developer") or {}
        dev_id = dev.get("id")
        if dev_id and str(dev_id) not in seen:
            seen[str(dev_id)] = Developer(
                source=SOURCE,
                source_id=str(dev_id),
                name=dev.get("name") or f"developer {dev_id}",
                logo_url=dev.get("logoUrl"),
            )
    return list(seen.values())


def areas_from_projects(raws: list[dict]) -> list[Area]:
    """Area rows derived from each project's location, grouped by district."""
    seen: dict[str, Area] = {}
    for raw in raws:
        district, city = _district_and_city(raw.get("location") or {})
        if not district:
            continue
        key = _slug(district)
        if key not in seen:
            seen[key] = Area(
                source=SOURCE,
                source_id=key,
                name=district,
                city=city if city and city != district else None,
            )
    return list(seen.values())


class PropertyFinderCollector:
    """Property Finder: developers and areas are derived from the projects,
    which is all the new-projects listing exposes."""

    name = SOURCE
    min_projects = 1000

    def __init__(self, fetcher: Fetcher, limit: int | None = None):
        self.fetcher = fetcher
        self.limit = limit

    async def collect(self) -> CollectionResult:
        raws = await fetch_projects(self.fetcher, self.limit)

        return CollectionResult(
            source=self.name,
            developers=merge_by_source_id(developers_from_projects(raws)),
            areas=merge_by_source_id(areas_from_projects(raws)),
            projects=merge_by_source_id(p for p in (map_project(r) for r in raws) if p),
            units=[],
            fetched_at=datetime.now(UTC),
        )
