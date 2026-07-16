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


def test_parse_candidates_skips_empty_articles(source_config, raw_page):
    adapter = GenericDeveloperSiteAdapter(source_config)
    candidates = adapter.parse_candidates(raw_page)

    # Fixture has 3 <article class="news-item">, one is empty -> 2 candidates
    assert len(candidates) == 2


def test_parse_candidates_carries_source_metadata_through(source_config, raw_page):
    adapter = GenericDeveloperSiteAdapter(source_config)
    candidates = adapter.parse_candidates(raw_page)

    for candidate in candidates:
        assert candidate.source_url == raw_page.url
        assert candidate.source_name == source_config.name
        assert candidate.source_type == source_config.source_type
        assert candidate.content_type == ContentType.HTML
        assert candidate.raw_content_hash


def test_parse_candidates_handles_mixed_arabic_english(source_config, raw_page):
    adapter = GenericDeveloperSiteAdapter(source_config)
    candidates = adapter.parse_candidates(raw_page)

    texts = [c.text for c in candidates]
    assert any("Marina Heights" in t for t in texts)
    assert any("الواحة الذهبية" in t for t in texts)


def test_parse_candidates_ignores_non_matching_content(source_config, raw_page):
    adapter = GenericDeveloperSiteAdapter(source_config)
    candidates = adapter.parse_candidates(raw_page)

    combined = " ".join(c.text for c in candidates).lower()
    assert "newsletter" not in combined


def test_parse_candidates_returns_empty_for_non_html_page(source_config):
    json_page = RawPage(
        url="https://example.com/api",
        content="{}",
        content_type=ContentType.JSON,
        fetched_at=datetime.now(timezone.utc),
    )
    adapter = GenericDeveloperSiteAdapter(source_config)
    assert adapter.parse_candidates(json_page) == []
