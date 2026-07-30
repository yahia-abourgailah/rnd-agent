import re

from bs4 import BeautifulSoup

from launch_intel.models import Candidate, ContentType, RawPage
from launch_intel.watch.base import BaseAdapter
from launch_intel.watch.change_detector import hash_content

# Elements that never carry launch information — dropped before the LLM sees
# the page so we don't pay tokens for scripts, styles and chrome.
_NOISE_TAGS = ("script", "style", "noscript", "svg", "iframe", "header", "footer", "nav")


class GenericDeveloperSiteAdapter(BaseAdapter):
    """
    Default adapter for developer sites: fetch the rendered page and hand its
    visible text to extraction as a single candidate.

    Deliberately does NOT hand-pick launch cards with CSS selectors. Real
    developer sites (Palm Hills, SODIC) are Angular/React apps whose class
    names are build-generated (`ng-star-inserted`, `ng-tns-c47-5`) and change
    on every redeploy, so selector-based slicing is unmaintainable. Feeding
    clean page text to the LLM survives redesigns; the extractor returns a
    list because one page usually advertises several projects.
    """

    adapter_name = "generic_developer_site"

    #: Pages shorter than this after cleaning are almost certainly an error
    #: page or a JS shell that failed to render — not worth an LLM call.
    min_text_length: int = 200

    async def fetch_pages(self) -> list[RawPage]:
        return [await self.fetcher.fetch_rendered_html(url) for url in self.source.urls]

    @staticmethod
    def extract_visible_text(html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(_NOISE_TAGS):
            tag.decompose()
        text = soup.get_text("\n", strip=True)
        # Collapse the long runs of blank lines that JS-rendered markup leaves
        # behind, so the LLM gets dense content rather than whitespace.
        return re.sub(r"\n{2,}", "\n", text)

    def parse_candidates(self, page: RawPage) -> list[Candidate]:
        if page.content_type != ContentType.HTML:
            return []

        text = self.extract_visible_text(page.content)
        if len(text) < self.min_text_length:
            return []

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
