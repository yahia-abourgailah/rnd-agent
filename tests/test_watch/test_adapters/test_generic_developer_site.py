from datetime import datetime, timezone
from pathlib import Path

import pytest

from launch_intel.models import ContentType, RawPage, SourceConfig, SourceTier, SourceType
from launch_intel.watch.adapters.generic_developer_site import GenericDeveloperSiteAdapter

FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent.parent / "fixtures" / "generic_developer_listing.html"
)


@pytest.fixture
def source_config() -> SourceConfig:
    return SourceConfig(
        name="generic_developer_demo",
        tier=SourceTier.TIER_1,
        source_type=SourceType.DEVELOPER_SITE,
        urls=["https://example-developer.com/launches"],
        crawl_frequency="30m",
        adapter_name="generic_developer_site",
    )


@pytest.fixture
def raw_page() -> RawPage:
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    return RawPage(
        url="https://example-developer.com/launches",
        content=html,
        content_type=ContentType.HTML,
        fetched_at=datetime.now(timezone.utc),
    )


def test_page_becomes_one_candidate(source_config, raw_page):
    """One page -> one candidate of visible text. The extractor is what splits
    it into multiple launches, not brittle CSS slicing."""
    candidates = GenericDeveloperSiteAdapter(source_config).parse_candidates(raw_page)
    assert len(candidates) == 1


def test_candidate_carries_source_metadata_through(source_config, raw_page):
    candidate = GenericDeveloperSiteAdapter(source_config).parse_candidates(raw_page)[0]

    assert candidate.source_url == raw_page.url
    assert candidate.source_name == source_config.name
    assert candidate.source_type == source_config.source_type
    assert candidate.content_type == ContentType.HTML
    assert candidate.raw_content_hash


def test_candidate_text_handles_mixed_arabic_english(source_config, raw_page):
    candidate = GenericDeveloperSiteAdapter(source_config).parse_candidates(raw_page)[0]

    assert "Marina Heights" in candidate.text
    assert "الواحة الذهبية" in candidate.text


def test_script_and_style_noise_is_stripped(source_config):
    html = """
        <html><body>
          <script>var trackingPixel = 'do not send this to the LLM';</script>
          <style>.launch-card { color: red; }</style>
          <nav>Home About Contact</nav>
          <main>Marina Heights launches its third phase in New Cairo, apartments
          from 120 sqm starting at 4,500,000 EGP with delivery in Q4 2028.
          The new phase adds townhouses and twin houses alongside the existing
          apartment buildings, with a payment plan of 10% down payment over
          eight years. Golden Oasis phase two is also now open for reservation
          in Sheikh Zayed with chalets starting at 3,200,000 EGP.</main>
        </body></html>
    """
    page = RawPage(
        url="https://example-developer.com/launches",
        content=html,
        content_type=ContentType.HTML,
        fetched_at=datetime.now(timezone.utc),
    )
    candidate = GenericDeveloperSiteAdapter(source_config).parse_candidates(page)[0]

    assert "Marina Heights" in candidate.text
    assert "trackingPixel" not in candidate.text
    assert "color: red" not in candidate.text
    # nav/footer chrome is dropped so we don't pay tokens for menus
    assert "Home About Contact" not in candidate.text


def test_near_empty_page_yields_no_candidate(source_config):
    """A JS shell that failed to render isn't worth an LLM call."""
    page = RawPage(
        url="https://example-developer.com/launches",
        content="<html><body><div>Loading...</div></body></html>",
        content_type=ContentType.HTML,
        fetched_at=datetime.now(timezone.utc),
    )
    assert GenericDeveloperSiteAdapter(source_config).parse_candidates(page) == []


def test_non_html_page_yields_no_candidate(source_config):
    json_page = RawPage(
        url="https://example.com/api",
        content="{}",
        content_type=ContentType.JSON,
        fetched_at=datetime.now(timezone.utc),
    )
    assert GenericDeveloperSiteAdapter(source_config).parse_candidates(json_page) == []
