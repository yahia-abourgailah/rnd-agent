import json
import re
from collections import defaultdict

from launch_intel.models import Candidate, ContentType, RawPage
from launch_intel.watch.base import BaseAdapter
from launch_intel.watch.change_detector import hash_content

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
_NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)

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
# JSON API. One query can cover many compounds at once, so enrichment costs a
# handful of requests rather than one per launch.
_PROPERTIES_API = "https://listing-api.nawy.com/v1/search/properties"
_MAX_PAGE_SIZE = 50  # the API rejects anything larger
_MAX_PAGES = 40  # safety stop so a pagination bug can't crawl forever
# Compound ids go in the query string, and the API 400s once the URL grows too
# long (20 ids pass, 24 fail), so ask about a limited number at a time.
_IDS_PER_REQUEST = 12

#: Internal bookkeeping keys, stripped before the record reaches the LLM.
_INTERNAL_KEYS = ("compound_id",)


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
        """Aggregate unit-level facts per compound from Nawy's listing API."""
        ids = [i for i in compound_ids if i is not None]
        if not ids:
            return {}

        units: list[dict] = []
        for start in range(0, len(ids), _IDS_PER_REQUEST):
            chunk = ids[start : start + _IDS_PER_REQUEST]
            collected = 0
            for page_number in range(1, _MAX_PAGES + 1):
                params = [("page", page_number), ("pageSize", _MAX_PAGE_SIZE)]
                params += [("compoundsIds[]", i) for i in chunk]
                response = await self.fetcher.fetch_json(_PROPERTIES_API, params=params)
                try:
                    body = json.loads(response.content)
                except json.JSONDecodeError:
                    break
                batch = body.get("results") or []
                units.extend(batch)
                collected += len(batch)
                if len(batch) < _MAX_PAGE_SIZE or collected >= body.get("total", 0):
                    break

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
            areas = [u["unitArea"] for u in compound_units if u.get("unitArea")]
            types = sorted({u["propertyType"] for u in compound_units if u.get("propertyType")})
            years = sorted({u["readyBy"][:4] for u in compound_units if u.get("readyBy")})

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
