from launch_intel.models import Candidate, RawPage
from launch_intel.watch.base import BaseAdapter

# TODO(phase-later): Nawy renders listings client-side and paginates via an
# internal API — inspect network tab for the JSON endpoint before falling
# back to fetch_rendered_html + DOM scraping.


class NawyAdapter(BaseAdapter):
    adapter_name = "nawy"

    async def fetch_pages(self) -> list[RawPage]:
        raise NotImplementedError("TODO(phase-later): implement Nawy crawl")

    def parse_candidates(self, page: RawPage) -> list[Candidate]:
        raise NotImplementedError("TODO(phase-later): implement Nawy candidate parsing")
