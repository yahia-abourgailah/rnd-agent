from bs4 import BeautifulSoup

from launch_intel.models import Candidate, ContentType, RawPage
from launch_intel.watch.base import BaseAdapter
from launch_intel.watch.change_detector import hash_content

# Generic, configurable selector for "one candidate launch item" on a
# developer site. Real developer sites vary wildly — this covers common
# news/launches listing markup as a starting point. Site-specific adapters
# (see nawy.py etc. for the stubbed pattern) should override
# candidate_selector or reimplement parse_candidates for unusual markup.
DEFAULT_CANDIDATE_SELECTOR = "article, .news-item, .launch-card, .press-release"


class GenericDeveloperSiteAdapter(BaseAdapter):
    """
    Working example adapter: a JS-rendered developer news/launches listing
    page where each item (article/card) is one candidate launch.
    """

    adapter_name = "generic_developer_site"
    candidate_selector: str = DEFAULT_CANDIDATE_SELECTOR

    async def fetch_pages(self) -> list[RawPage]:
        return [await self.fetcher.fetch_rendered_html(url) for url in self.source.urls]

    def parse_candidates(self, page: RawPage) -> list[Candidate]:
        if page.content_type != ContentType.HTML:
            return []

        soup = BeautifulSoup(page.content, "html.parser")
        candidates = []
        for item in soup.select(self.candidate_selector):
            text = item.get_text(separator=" ", strip=True)
            if not text:
                continue
            candidates.append(
                Candidate(
                    source_url=page.url,
                    source_name=self.source.name,
                    source_type=self.source.source_type,
                    content_type=page.content_type,
                    text=text,
                    raw_content_hash=hash_content(text),
                )
            )
        return candidates
