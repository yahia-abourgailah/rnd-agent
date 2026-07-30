from launch_intel.models import Candidate, RawPage
from launch_intel.watch.base import BaseAdapter

# TODO(phase-later): PropertyFinder — check for a sitemap/JSON-LD feed of
# new-project listings before resorting to full DOM scraping.


class PropertyFinderAdapter(BaseAdapter):
    adapter_name = "property_finder"

    async def fetch_pages(self) -> list[RawPage]:
        raise NotImplementedError("TODO(phase-later): implement PropertyFinder crawl")

    def parse_candidates(self, page: RawPage) -> list[Candidate]:
        raise NotImplementedError("TODO(phase-later): implement PropertyFinder candidate parsing")
