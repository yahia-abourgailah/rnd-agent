import json
import logging
import re
from collections import defaultdict

from models import Candidate, ContentType, RawPage
from watch.base import BaseAdapter
from watch.change_detector import hash_content

# Nawy is a Next.js app: every page embeds its server-side props as JSON in a
# __NEXT_DATA__ script tag. That payload is the same data the UI renders, but
# already structured — so we hand the LLM explicit key/value records instead of
# flattened screen text.
#
# This matters for accuracy, not just tidiness. On the rendered text the fields
# of one listing appear as a bare run of lines (LOCATION, NAME, DEVELOPER,
# PRICE) with nothing marking where one project ends and the next begins, and
# the model routinely attributed a project's zone to its neighbour. The JSON
# has no such ambiguity.
logger = logging.getLogger(__name__)

_NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)

#: Nawy's field name -> our Launch field name. Renaming here rather than
#: relying on the model to infer the mapping: given "areaName" it left `zone`
#: null on every record, given "zone" it fills it correctly.
_FIELD_MAP = {
    "name": "project_name",
    "developerName": "developer",
    "areaName": "zone",
    "minPrice": "price_from",
    "currency": "currency",
    "slug": "slug",
}

# The listing payload carries no unit sizes, property types or delivery dates —
# those live on individual unit records, which the site loads from this public
# JSON API. It takes its filters in a POST body, pages 500 at a time, and can
# filter server-side by compound and by sale type.
PROPERTIES_API = "https://webapi.nawy.com/api/properties/search"
NAWY_CLIENT_ID = "d7X2j6PjCG"
MAX_PAGE_SIZE = 500
MAX_PAGES = 60  # safety stop so a pagination bug can't crawl forever

# Primary/off-plan only: resale units are a different market and are not what
# this product tracks. The API filters on the PRESENCE of this key — it ignores
# the value, returning non-resale for both true and false — so the result is
# also asserted per record below rather than trusted.
_PRIMARY_ONLY_FILTER = {"resale": {"value": False}}

#: Unit record field names on the web API, named once so the mapper in
#: collect/nawy.py and the aggregation here cannot drift apart.
UNIT_AREA = "min_unit_area"
UNIT_TYPE = "property_type"
UNIT_READY_BY = "min_ready_by"
UNIT_PRICE = "min_price"

#: Internal bookkeeping keys, stripped before the record reaches the LLM.
_INTERNAL_KEYS = ("compound_id",)


def _webapi_headers() -> dict:
    """Nawy's web API rejects requests without its browser client headers."""
    return {
        "accept": "application/json, text/plain, */*",
        "accept-language": "en",
        "client-id": NAWY_CLIENT_ID,
        "content-type": "application/json",
        "origin": "https://www.nawy.com",
        "referer": "https://www.nawy.com/",
        "platform": "web",
    }


def is_primary(unit: dict) -> bool:
    """Whether a unit is sold by the developer rather than resold."""
    return unit.get("resale") is not True


async def fetch_primary_units(
    fetcher, compound_id: int | None = None, limit: int | None = None
) -> list[dict]:
    """Every primary/off-plan unit Nawy lists, optionally for one compound.

    Resale units are excluded server-side and the exclusion is then re-checked
    per record, because the filter's contract is undocumented: the API returns
    non-resale results for any value of the key, so a change in its behaviour
    would otherwise silently readmit resale stock.
    """
    units: list[dict] = []
    start = 1
    for _ in range(MAX_PAGES):
        body = {
            "show": "property",
            "start": start,
            "page_size": MAX_PAGE_SIZE,
            **_PRIMARY_ONLY_FILTER,
        }
        if compound_id is not None:
            body["compound_id"] = compound_id

        response = await fetcher.post_json(
            PROPERTIES_API, json=body, headers=_webapi_headers()
        )
        try:
            payload = json.loads(response.content)
        except json.JSONDecodeError:
            logger.warning("Non-JSON unit payload at start=%s", start)
            break

        batch = payload.get("values") or []
        primary = [unit for unit in batch if is_primary(unit)]
        if len(primary) != len(batch):
            logger.warning(
                "Server-side resale filter let %d resale unit(s) through at start=%s; "
                "dropped client-side",
                len(batch) - len(primary),
                start,
            )
        units.extend(primary)

        if limit is not None and len(units) >= limit:
            return units[:limit]
        if len(batch) < MAX_PAGE_SIZE:
            break
        start += MAX_PAGE_SIZE
    else:
        logger.warning("Hit the %s-page cap; unit data may be truncated", MAX_PAGES)
    return units


class NawyAdapter(BaseAdapter):
    """
    Aggregator adapter for Nawy's new-launches listing.

    Two-step: read the launch list from the page's embedded JSON, then enrich
    each launch with unit-level facts (sizes, property types, delivery) pulled
    from Nawy's own listing API.
    """

    adapter_name = "nawy"

    async def fetch_pages(self) -> list[RawPage]:
        pages: list[RawPage] = []
        for url in self.source.urls:
            page = await self.fetcher.fetch_rendered_html(url)
            records = self.extract_launch_records(page.content)
            if records:
                enrichment = await self._fetch_unit_facts([r["compound_id"] for r in records])
                for record in records:
                    record.update(enrichment.get(record["compound_id"], {}))
            # Emit the structured records as the page payload: everything
            # downstream (change detection, extraction) then works off the
            # enriched data rather than the raw HTML.
            pages.append(
                RawPage(
                    url=page.url,
                    content=json.dumps(records, ensure_ascii=False),
                    content_type=ContentType.JSON,
                    fetched_at=page.fetched_at,
                )
            )
        return pages

    @staticmethod
    def extract_launch_records(html: str) -> list[dict]:
        """Pull the launch list out of __NEXT_DATA__, keeping only useful fields."""
        match = _NEXT_DATA_RE.search(html)
        if not match:
            return []
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError:
            return []

        results = (
            payload.get("props", {})
            .get("pageProps", {})
            .get("launches", {})
            .get("results", [])
        )

        records = []
        for result in results:
            record = {
                ours: result[theirs]
                for theirs, ours in _FIELD_MAP.items()
                if result.get(theirs) is not None
            }
            # Nawy sends minPrice 0 for launches whose price is not published
            # yet. Passing that through would read as "free" and sort to the
            # top of any cheapest-first view, so drop it: absent, not zero.
            if not record.get("price_from"):
                record.pop("price_from", None)
                record.pop("currency", None)
            # The launch id doubles as the compound id in Nawy's API.
            record["compound_id"] = result.get("id")
            records.append(record)
        return records

    async def _fetch_unit_facts(self, compound_ids: list[int]) -> dict[int, dict]:
        """Aggregate primary unit facts per compound, one request per compound.

        The API filters by a single compound_id, and a launch page carries a
        handful of compounds, so this is a few requests rather than a scan of
        the whole catalogue.
        """
        units: list[dict] = []
        for compound_id in [i for i in compound_ids if i is not None]:
            units.extend(await fetch_primary_units(self.fetcher, compound_id=compound_id))
        return self.aggregate_unit_facts(units)

    @staticmethod
    def aggregate_unit_facts(units: list[dict]) -> dict[int, dict]:
        """
        Roll individual unit records up to the launch level.

        Launch.unit_sizes is a range, so it can only be derived by looking at
        every unit in a compound — hence the aggregation rather than reading a
        single field.
        """
        grouped: dict[int, list[dict]] = defaultdict(list)
        for unit in units:
            compound_id = (unit.get("compound") or {}).get("id")
            if compound_id is not None:
                grouped[compound_id].append(unit)

        facts: dict[int, dict] = {}
        for compound_id, compound_units in grouped.items():
            areas = [u[UNIT_AREA] for u in compound_units if u.get(UNIT_AREA)]
            types = sorted(
                {
                    name
                    for u in compound_units
                    if (name := (u.get(UNIT_TYPE) or {}).get("name"))
                }
            )
            years = sorted(
                {str(u[UNIT_READY_BY])[:4] for u in compound_units if u.get(UNIT_READY_BY)}
            )

            entry: dict = {}
            if types:
                entry["property_types"] = types
            if areas:
                entry["unit_sizes"] = {"min_sqm": min(areas), "max_sqm": max(areas)}
            if years:
                # Report the source's own granularity: a single year when every
                # unit lands in one, otherwise the span.
                entry["delivery_date"] = years[0] if len(years) == 1 else f"{years[0]}-{years[-1]}"
            facts[compound_id] = entry
        return facts

    def parse_candidates(self, page: RawPage) -> list[Candidate]:
        if page.content_type != ContentType.JSON:
            return []
        try:
            records = json.loads(page.content)
        except json.JSONDecodeError:
            return []
        if not records:
            # Nawy changed its markup, or the page failed to render. Better to
            # yield nothing than to silently fall back to lossy text scraping.
            return []

        for record in records:
            for key in _INTERNAL_KEYS:
                record.pop(key, None)

        # One candidate for the whole list: the records are self-delimiting, so
        # a single LLM call can read all of them without cross-contamination.
        text = json.dumps(records, ensure_ascii=False, indent=1)
        return [
            Candidate(
                source_url=page.url,
                source_name=self.source.name,
                source_type=self.source.source_type,
                content_type=page.content_type,
                text=text,
                raw_content_hash=hash_content(text),
            )
        ]
