import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from launch_intel.models import ContentType, RawPage, SourceConfig, SourceTier, SourceType
from launch_intel.watch.adapters.nawy import NawyAdapter

FIXTURES = Path(__file__).resolve().parent.parent.parent / "fixtures"
LISTING = FIXTURES / "live" / "nawy_new_launches.html"


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


def _json_page(records: list[dict]) -> RawPage:
    """fetch_pages emits enriched records as a JSON page, not raw HTML."""
    return RawPage(
        url="https://www.nawy.com/new-launches",
        content=json.dumps(records),
        content_type=ContentType.JSON,
        fetched_at=datetime.now(timezone.utc),
    )


# --- reading the launch list out of the page -------------------------------


def test_reads_launches_from_embedded_json():
    records = NawyAdapter.extract_launch_records(LISTING.read_text(encoding="utf-8"))
    assert len(records) == 24


def test_fields_are_renamed_to_the_launch_contract():
    """The model leaves `zone` null when handed Nawy's own `areaName` key, so
    the adapter renames fields to match our schema before extraction."""
    first = NawyAdapter.extract_launch_records(LISTING.read_text(encoding="utf-8"))[0]

    assert first["project_name"] == "Southmed"
    assert first["developer"] == "Talaat Moustafa Group (TMG) Holding"
    assert first["zone"] == "Al Dabaa"
    assert first["price_from"] == 6000000
    assert "areaName" not in first and "minPrice" not in first


def test_zones_come_from_json_not_positional_guessing():
    """Regression guard: reading rendered text mis-assigned zones to the
    neighbouring project (Southmed got Perla's zone). JSON is unambiguous."""
    by_name = {
        r["project_name"]: r
        for r in NawyAdapter.extract_launch_records(LISTING.read_text(encoding="utf-8"))
    }

    assert by_name["Southmed"]["zone"] == "Al Dabaa"
    assert by_name["Salt Marina"]["zone"] == "Ras El Hekma"
    assert by_name["Perla"]["zone"] == "Al Dabaa"
    assert by_name["Bloom Island - Ogami"]["zone"] == "Ras El Hekma"


def test_compound_id_is_captured_for_enrichment():
    first = NawyAdapter.extract_launch_records(LISTING.read_text(encoding="utf-8"))[0]
    assert first["compound_id"] == 1198


# --- aggregating unit-level facts ------------------------------------------


def test_aggregate_unit_facts_builds_size_range_and_types():
    """unit_sizes is a range in the Launch contract, so it can only come from
    looking across every unit in a compound."""
    units = [
        {"compound": {"id": 2458}, "unitArea": 100, "propertyType": "Chalet",
         "readyBy": "2030-07-04T00:00:00.000Z"},
        {"compound": {"id": 2458}, "unitArea": 575, "propertyType": "Villa",
         "readyBy": "2030-01-01T00:00:00.000Z"},
        {"compound": {"id": 2458}, "unitArea": 300, "propertyType": "Chalet",
         "readyBy": "2030-01-01T00:00:00.000Z"},
    ]
    facts = NawyAdapter.aggregate_unit_facts(units)[2458]

    assert facts["unit_sizes"] == {"min_sqm": 100, "max_sqm": 575}
    assert facts["property_types"] == ["Chalet", "Villa"]  # de-duplicated, sorted
    assert facts["delivery_date"] == "2030"  # single year -> not a span


def test_delivery_spanning_years_is_reported_as_a_range():
    units = [
        {"compound": {"id": 1}, "readyBy": "2025-05-01T00:00:00.000Z"},
        {"compound": {"id": 1}, "readyBy": "2031-05-01T00:00:00.000Z"},
    ]
    assert NawyAdapter.aggregate_unit_facts(units)[1]["delivery_date"] == "2025-2031"


def test_units_without_facts_do_not_invent_fields():
    facts = NawyAdapter.aggregate_unit_facts([{"compound": {"id": 7}}])[7]
    assert facts == {}


def test_units_with_no_compound_are_skipped():
    assert NawyAdapter.aggregate_unit_facts([{"unitArea": 100}]) == {}


# --- turning records into a candidate --------------------------------------


def test_candidate_is_one_json_document(source):
    records = NawyAdapter.extract_launch_records(LISTING.read_text(encoding="utf-8"))
    candidates = NawyAdapter(source).parse_candidates(_json_page(records))

    assert len(candidates) == 1
    payload = json.loads(candidates[0].text)
    assert len(payload) == 24
    assert candidates[0].source_name == "nawy"
    assert candidates[0].source_type == SourceType.AGGREGATOR


def test_internal_ids_are_not_sent_to_the_llm(source):
    records = NawyAdapter.extract_launch_records(LISTING.read_text(encoding="utf-8"))
    candidate = NawyAdapter(source).parse_candidates(_json_page(records))[0]

    assert all("compound_id" not in record for record in json.loads(candidate.text))


def test_empty_or_unparseable_payload_yields_nothing(source):
    """If Nawy changes its markup we want zero output, not a silent fallback
    to lossy text scraping."""
    adapter = NawyAdapter(source)
    assert adapter.parse_candidates(_json_page([])) == []

    broken = RawPage(
        url="https://www.nawy.com/new-launches",
        content="not json",
        content_type=ContentType.JSON,
        fetched_at=datetime.now(timezone.utc),
    )
    assert adapter.parse_candidates(broken) == []


def test_missing_next_data_yields_no_records():
    assert NawyAdapter.extract_launch_records("<html><body>nothing</body></html>") == []
