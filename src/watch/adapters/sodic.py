from models import Candidate, RawPage
from watch.base import BaseAdapter

# TODO(phase-later): SODIC's news page is likely simple enough that
# GenericDeveloperSiteAdapter's default selector works with minor tweaks —
# try subclassing it before writing a fully custom parse_candidates.


class SodicAdapter(BaseAdapter):
    adapter_name = "sodic"

    async def fetch_pages(self) -> list[RawPage]:
        raise NotImplementedError("TODO(phase-later): implement SODIC crawl")

    def parse_candidates(self, page: RawPage) -> list[Candidate]:
        raise NotImplementedError("TODO(phase-later): implement SODIC candidate parsing")
