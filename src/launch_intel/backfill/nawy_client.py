"""Backfill client for Nawy's public listing API.

Unlike the watch/ adapters (which carve pages into launch candidates for the
LLM), this module reads Nawy's *structured* entity endpoints directly and maps
them onto our relational contract models. No LLM involved — the data is already
structured, so we copy it as-is.

Endpoints (undocumented, public):
    /v1/developers          -> Developer   (paginated, NO total field)
    /v1/areas               -> Area        (paginated, has total)
    /v1/search/compounds    -> Project     (paginated, has total, ~1830)
    /v1/search/properties   -> Unit        (per-compound, has total)

Every fetch fails safe: if a payload's shape changes, mapping skips the record
rather than crashing the whole backfill.
"""

import json
import logging
from collections import defaultdict
from datetime import datetime

from launch_intel.models import Area, Availability, Developer, Project, Unit
from launch_intel.watch.adapters.nawy import (
    NawyAdapter,
    _IDS_PER_REQUEST,
    _MAX_PAGE_SIZE,
    _MAX_PAGES,
    _PROPERTIES_API,
)
from launch_intel.watch.fetcher import Fetcher

logger = logging.getLogger(__name__)

SOURCE = "nawy"

_DEVELOPERS_API = "https://listing-api.nawy.com/v1/developers"
_AREAS_API = "https://listing-api.nawy.com/v1/areas"
_COMPOUNDS_API = "https://listing-api.nawy.com/v1/search/compounds"
_NEW_LAUNCHES_URL = "https://www.nawy.com/new-launches"

_PAGE_SIZE = 50  # entity endpoints accept up to 50; larger is rejected
_MAX_ENTITY_PAGES = 200  # safety stop for the total-less developers endpoint


# --------------------------------------------------------------------------- #
# Fetching (paginated)
# --------------------------------------------------------------------------- #
async def _fetch_all_pages(
    fetcher: Fetcher, url: str, limit: int | None = None
) -> list[dict]:
    """Walk a paginated `{results: [...]}` endpoint until it runs dry.

    Stops on the FIRST empty page rather than trusting a requested pageSize —
    the developers endpoint reports no `total` and may cap page size, so
    "empty results" is the only reliable end signal.
    """
    collected: list[dict] = []
    for page_number in range(1, _MAX_ENTITY_PAGES + 1):
        params = [("page", page_number), ("pageSize", _PAGE_SIZE)]
        response = await fetcher.fetch_json(url, params=params)
        try:
            body = json.loads(response.content)
        except json.JSONDecodeError:
            logger.warning("Non-JSON response from %s page %s", url, page_number)
            break
        results = body.get("results") or []
        if not results:
            break
        collected.extend(results)
        if limit is not None and len(collected) >= limit:
            return collected[:limit]
        total = body.get("total")
        if total is not None and len(collected) >= total:
            break
    return collected


async def fetch_developers(fetcher: Fetcher, limit: int | None = None) -> list[dict]:
    return await _fetch_all_pages(fetcher, _DEVELOPERS_API, limit)


async def fetch_areas(fetcher: Fetcher, limit: int | None = None) -> list[dict]:
    return await _fetch_all_pages(fetcher, _AREAS_API, limit)


async def fetch_compounds(fetcher: Fetcher, limit: int | None = None) -> list[dict]:
    return await _fetch_all_pages(fetcher, _COMPOUNDS_API, limit)


async def fetch_units_for_compounds(
    fetcher: Fetcher, compound_ids: list[int]
) -> list[dict]:
    """Fetch every unit record for the given compounds.

    Mirrors NawyAdapter's chunking: compound ids ride in the query string and
    the API 400s once the URL grows too long, so ask about a handful at a time
    and paginate each chunk.
    """
    ids = [i for i in compound_ids if i is not None]
    units: list[dict] = []
    for start in range(0, len(ids), _IDS_PER_REQUEST):
        chunk = ids[start : start + _IDS_PER_REQUEST]
        collected = 0
        for page_number in range(1, _MAX_PAGES + 1):
            params = [("page", page_number), ("pageSize", _MAX_PAGE_SIZE)]
            params += [("compoundsIds[]", i) for i in chunk]
            response = await fetcher.fetch_json(_PROPERTIES_API, params=params)
            try:
                body = json.loads(response.content)
            except json.JSONDecodeError:
                break
            batch = body.get("results") or []
            units.extend(batch)
            collected += len(batch)
            if len(batch) < _MAX_PAGE_SIZE or collected >= body.get("total", 0):
                break
    return units


async def fetch_launch_compound_ids(fetcher: Fetcher) -> set[int]:
    """The compound ids currently featured on Nawy's new-launches page.

    Reuses the proven NawyAdapter parser rather than inventing a second way to
    identify launches. Fails safe to an empty set (nothing flagged) if the page
    shape changes.
    """
    try:
        page = await fetcher.fetch_rendered_html(_NEW_LAUNCHES_URL)
    except Exception as exc:  # network/render failure shouldn't sink the backfill
        logger.warning("Could not fetch new-launches page: %s", exc)
        return set()
    records = NawyAdapter.extract_launch_records(page.content)
    return {r["compound_id"] for r in records if r.get("compound_id") is not None}


# --------------------------------------------------------------------------- #
# Mapping (pure — unit-testable without network)
# --------------------------------------------------------------------------- #
def _year_from_compound_readyby(ready_by) -> str | None:
    """Compound plans report readyBy as an int YYYYMMDD (e.g. 20291230)."""
    if not ready_by:
        return None
    text = str(ready_by)
    return text[:4] if len(text) >= 4 else None


def _date_from_unit_readyby(ready_by) -> str | None:
    """Unit records report readyBy as an ISO datetime ("2030-07-06T...")."""
    if not ready_by:
        return None
    return str(ready_by)[:10]


def map_developer(raw: dict) -> Developer | None:
    if raw.get("id") is None or not raw.get("name"):
        return None
    return Developer(
        source=SOURCE,
        source_id=str(raw["id"]),
        name=raw["name"],
        slug=raw.get("slug"),
        logo_url=raw.get("image"),
        projects_count=raw.get("compoundsCount"),
        raw=raw,
    )


def map_area(raw: dict) -> Area | None:
    if raw.get("id") is None or not raw.get("name"):
        return None
    return Area(
        source=SOURCE,
        source_id=str(raw["id"]),
        name=raw["name"],
        slug=raw.get("slug"),
        city=raw.get("parentAreaName"),
        raw=raw,
    )


def map_compound(raw: dict, launch_ids: set[int]) -> Project | None:
    if raw.get("id") is None or not raw.get("name"):
        return None
    plan = raw.get("developerPlan") or raw.get("resalePlan") or {}
    property_types = [
        pt["name"] for pt in (raw.get("propertyTypes") or []) if pt.get("name")
    ]
    return Project(
        source=SOURCE,
        source_id=str(raw["id"]),
        name=raw["name"],
        slug=raw.get("slug"),
        developer_source_id=str(raw["developerId"]) if raw.get("developerId") else None,
        area_source_id=str(raw["areaId"]) if raw.get("areaId") else None,
        min_price=plan.get("minPrice") or None,
        currency=plan.get("currency"),
        property_types=property_types,
        is_launch=raw.get("id") in launch_ids,
        delivery_date=_year_from_compound_readyby(plan.get("readyBy")),
        image_url=raw.get("imageUrl"),
        description=raw.get("subtitle"),
        raw=raw,
    )


def map_unit(raw: dict) -> Unit | None:
    if raw.get("id") is None:
        return None
    pay = raw.get("paymentPlan") or {}
    compound = raw.get("compound") or {}
    return Unit(
        source=SOURCE,
        source_id=str(raw["id"]),
        project_source_id=str(compound["id"]) if compound.get("id") else None,
        property_type=raw.get("propertyType"),
        unit_area_sqm=raw.get("unitArea"),
        bedrooms=raw.get("numberOfBedrooms"),
        bathrooms=raw.get("numberOfBathrooms"),
        price=pay.get("minPrice") or None,
        currency=pay.get("currency"),
        ready_by=_date_from_unit_readyby(raw.get("readyBy")),
        finishing=raw.get("finishing"),
        raw=raw,
    )


def developers_from_compounds(compounds: list[dict]) -> list[Developer]:
    """Minimal developer rows for developerIds that appear on compounds but were
    not returned by /v1/developers — so every project's FK resolves."""
    seen: dict[str, Developer] = {}
    for raw in compounds:
        dev_id = raw.get("developerId")
        if dev_id is None:
            continue
        key = str(dev_id)
        if key not in seen:
            seen[key] = Developer(
                source=SOURCE,
                source_id=key,
                name=raw.get("developerName") or f"developer {key}",
                logo_url=raw.get("developerLogoUrl"),
            )
    return list(seen.values())


def compute_availability(units: list[Unit], snapshot_at: datetime) -> list[Availability]:
    """Roll units up to one availability snapshot per project.

    Nawy has no availability endpoint — this summary is derived from the unit
    rows we already hold. available_units == total_units because every unit Nawy
    returns is a currently-listed (available) unit.
    """
    grouped: dict[str, list[Unit]] = defaultdict(list)
    for unit in units:
        if unit.project_source_id:
            grouped[unit.project_source_id].append(unit)

    snapshots: list[Availability] = []
    for project_source_id, group in grouped.items():
        prices = [u.price for u in group if u.price]
        per_sqm = [
            u.price / u.unit_area_sqm for u in group if u.price and u.unit_area_sqm
        ]
        unit_types = sorted({u.property_type for u in group if u.property_type})
        years = sorted({u.ready_by[:4] for u in group if u.ready_by})
        delivery_range = None
        if years:
            delivery_range = years[0] if len(years) == 1 else f"{years[0]}-{years[-1]}"

        snapshots.append(
            Availability(
                project_source_id=project_source_id,
                snapshot_at=snapshot_at,
                total_units=len(group),
                available_units=len(group),
                min_price=min(prices) if prices else None,
                max_price=max(prices) if prices else None,
                price_per_sqm_min=round(min(per_sqm), 2) if per_sqm else None,
                price_per_sqm_max=round(max(per_sqm), 2) if per_sqm else None,
                unit_types=unit_types,
                delivery_range=delivery_range,
            )
        )
    return snapshots


def areas_from_compounds(compounds: list[dict]) -> list[Area]:
    """Minimal area rows for areaIds that appear on compounds but were not
    returned by /v1/areas (e.g. leaf areas under a parent)."""
    seen: dict[str, Area] = {}
    for raw in compounds:
        area_id = raw.get("areaId")
        if area_id is None:
            continue
        key = str(area_id)
        if key not in seen:
            seen[key] = Area(
                source=SOURCE,
                source_id=key,
                name=raw.get("areaName") or f"area {key}",
                city=raw.get("parentAreaName"),
            )
    return list(seen.values())
