import json
import re

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
#: null on every record, given "zone" it fills it correctly. The rest of Nawy's
#: fields (image URLs, logos, internal ids) are noise that would only cost tokens.
_FIELD_MAP = {
    "name": "project_name",
    "developerName": "developer",
    "areaName": "zone",
    "minPrice": "price_from",
    "currency": "currency",
    "slug": "slug",
}


class NawyAdapter(BaseAdapter):
    """Aggregator adapter for Nawy's new-launches listing."""

    adapter_name = "nawy"

    async def fetch_pages(self) -> list[RawPage]:
        return [await self.fetcher.fetch_rendered_html(url) for url in self.source.urls]

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
        return [
            {ours: r[theirs] for theirs, ours in _FIELD_MAP.items() if r.get(theirs) is not None}
            for r in results
        ]

    def parse_candidates(self, page: RawPage) -> list[Candidate]:
        if page.content_type != ContentType.HTML:
            return []

        records = self.extract_launch_records(page.content)
        if not records:
            # Nawy changed its markup, or the page failed to render. Better to
            # yield nothing than to silently fall back to lossy text scraping.
            return []

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
