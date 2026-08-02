from models import Candidate, RawPage
from watch.base import BaseAdapter

# TODO(phase-later): Palm Hills Developments — same note as sodic.py, try
# subclassing GenericDeveloperSiteAdapter first.


class PalmHillsAdapter(BaseAdapter):
    adapter_name = "palm_hills"

    async def fetch_pages(self) -> list[RawPage]:
        raise NotImplementedError("TODO(phase-later): implement Palm Hills crawl")

    def parse_candidates(self, page: RawPage) -> list[Candidate]:
        raise NotImplementedError("TODO(phase-later): implement Palm Hills candidate parsing")
