import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from launch_intel.models import ContentType, RawPage, SourceConfig, SourceTier, SourceType
from launch_intel.watch.adapters.nawy import NawyAdapter

FIXTURE = (
    Path(__file__).resolve().parent.parent.parent / "fixtures" / "live" / "nawy_new_launches.html"
)


@pytest.fixture
def source() -> SourceConfig:
    return SourceConfig(
        name="nawy",
        tier=SourceTier.TIER_2,
        source_type=SourceType.AGGREGATOR,
        urls=["https://www.nawy.com/new-launches"],
        crawl_frequency="1h",
        adapter_name="nawy",
    )


@pytest.fixture
def page() -> RawPage:
    return RawPage(
        url="https://www.nawy.com/new-launches",
        content=FIXTURE.read_text(encoding="utf-8"),
        content_type=ContentType.HTML,
        fetched_at=datetime.now(timezone.utc),
    )


def test_reads_launches_from_embedded_json(source, page):
    records = NawyAdapter.extract_launch_records(page.content)
    assert len(records) == 24


def test_fields_are_renamed_to_the_launch_contract(source, page):
    """The model leaves `zone` null when handed Nawy's own `areaName` key, so
    the adapter renames fields to match our schema before extraction."""
    first = NawyAdapter.extract_launch_records(page.content)[0]

    assert first["project_name"] == "Southmed"
    assert first["developer"] == "Talaat Moustafa Group (TMG) Holding"
    assert first["zone"] == "Al Dabaa"
    assert first["price_from"] == 6000000
    assert "areaName" not in first and "minPrice" not in first


def test_zones_come_from_json_not_positional_guessing(source, page):
    """Regression guard: reading rendered text mis-assigned zones to the
    neighbouring project (Southmed got Perla's zone). JSON is unambiguous."""
    by_name = {r["project_name"]: r for r in NawyAdapter.extract_launch_records(page.content)}

    assert by_name["Southmed"]["zone"] == "Al Dabaa"
    assert by_name["Salt Marina"]["zone"] == "Ras El Hekma"
    assert by_name["Perla"]["zone"] == "Al Dabaa"
    assert by_name["Bloom Island - Ogami"]["zone"] == "Ras El Hekma"


def test_candidate_is_one_json_document(source, page):
    candidates = NawyAdapter(source).parse_candidates(page)

    assert len(candidates) == 1
    payload = json.loads(candidates[0].text)
    assert len(payload) == 24
    assert candidates[0].source_name == "nawy"
    assert candidates[0].source_type == SourceType.AGGREGATOR


def test_missing_next_data_yields_nothing_rather_than_bad_data(source):
    """If Nawy changes its markup we want zero output, not a silent fallback
    to lossy text scraping."""
    page = RawPage(
        url="https://www.nawy.com/new-launches",
        content="<html><body><p>no embedded json here</p></body></html>",
        content_type=ContentType.HTML,
        fetched_at=datetime.now(timezone.utc),
    )
    assert NawyAdapter(source).parse_candidates(page) == []


def test_non_html_page_is_ignored(source):
    page = RawPage(
        url="https://www.nawy.com/api",
        content="{}",
        content_type=ContentType.JSON,
        fetched_at=datetime.now(timezone.utc),
    )
    assert NawyAdapter(source).parse_candidates(page) == []
