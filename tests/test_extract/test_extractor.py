from datetime import datetime
from unittest.mock import MagicMock

from launch_intel.extract.extractor import ExtractedFields, ExtractedLaunches, extract_launches
from launch_intel.models import Candidate, ContentType, LaunchType, SourceType


def _make_candidate() -> Candidate:
    return Candidate(
        source_url="https://example-developer.com/launches",
        source_name="generic_developer_demo",
        source_type=SourceType.DEVELOPER_SITE,
        content_type=ContentType.HTML,
        text="Marina Heights new phase, apartments 120-220 sqm, from 4,500,000 EGP, Q4 2028.",
        raw_content_hash="deadbeef",
    )


def _fake_scraper(*extracted: ExtractedFields) -> MagicMock:
    """Stands in for ScrapeGraphAI's SmartScraperGraph — returns a plain dict
    like the real one does, so validation is exercised too."""
    scraper = MagicMock()
    scraper.run.return_value = ExtractedLaunches(launches=list(extracted)).model_dump()
    return scraper


def test_extract_launch_maps_fields_and_fills_context():
    extracted = ExtractedFields(
        developer="sodic",  # lowercase on purpose - normalize.py should alias-fix casing
        project_name="Marina Heights",
        launch_type=LaunchType.NEW_PHASE,
        zone="new cairo",
        price_from=4_500_000,
        delivery_date="Q4 2028",
        confidence=0.9,
    )
    candidate = _make_candidate()

    launches = extract_launches(candidate, scraper=_fake_scraper(extracted))
    assert len(launches) == 1
    launch = launches[0]

    assert launch.project_name == "Marina Heights"
    assert launch.launch_type == LaunchType.NEW_PHASE
    assert launch.developer == "SODIC"
    assert launch.zone == "New Cairo"
    assert launch.price_from == 4_500_000
    assert launch.delivery_date == "Q4 2028"
    assert launch.confidence == 0.9

    # Context filled in by extract_launch itself, not the LLM
    assert launch.source_url == candidate.source_url
    assert launch.source_type == candidate.source_type
    assert launch.raw_content == candidate.text
    assert isinstance(launch.first_seen_at, datetime)


def test_extract_launch_leaves_unlisted_developer_and_zone_untouched():
    extracted = ExtractedFields(
        developer="Some New Developer",
        project_name="X Towers",
        launch_type=LaunchType.NEW_PROJECT,
        zone="Some Unlisted Zone",
        confidence=0.5,
    )
    candidate = _make_candidate()

    launches = extract_launches(candidate, scraper=_fake_scraper(extracted))
    assert len(launches) == 1
    launch = launches[0]

    assert launch.developer == "Some New Developer"
    assert launch.zone == "Some Unlisted Zone"


def test_extract_launch_low_confidence_is_still_returned_not_dropped():
    extracted = ExtractedFields(
        project_name="Ambiguous Mention",
        launch_type=LaunchType.REPRICING,
        confidence=0.05,
    )
    candidate = _make_candidate()

    launches = extract_launches(candidate, scraper=_fake_scraper(extracted))
    assert len(launches) == 1
    launch = launches[0]

    assert launch.confidence == 0.05
    assert launch.project_name == "Ambiguous Mention"


def test_extract_launch_is_fed_local_content_not_a_url(monkeypatch):
    """Cost-control guard: ScrapeGraphAI must receive the already-fetched text,
    never the URL — otherwise it re-fetches and bypasses change detection."""
    captured = {}

    class FakeGraph:
        def __init__(self, prompt, source, config, schema):
            captured["source"] = source

        def run(self):
            return ExtractedLaunches(
                launches=[
                    ExtractedFields(
                        project_name="X", launch_type=LaunchType.NEW_PROJECT, confidence=0.5
                    )
                ]
            ).model_dump()

    import scrapegraphai.graphs

    monkeypatch.setattr(scrapegraphai.graphs, "SmartScraperGraph", FakeGraph)

    candidate = _make_candidate()
    extract_launches(candidate)

    assert captured["source"] == candidate.text
    assert not captured["source"].startswith("http")


def test_one_page_yields_multiple_launches():
    """A developer homepage typically advertises several projects at once."""
    candidate = _make_candidate()
    launches = extract_launches(
        candidate,
        scraper=_fake_scraper(
            ExtractedFields(
                project_name="Hacienda Blue", launch_type=LaunchType.NEW_PROJECT, confidence=0.8
            ),
            ExtractedFields(
                project_name="Palm Hills One", launch_type=LaunchType.NEW_PHASE, confidence=0.7
            ),
        ),
    )

    assert [launch.project_name for launch in launches] == ["Hacienda Blue", "Palm Hills One"]
    # Every launch keeps the same source context and its own identity
    assert {launch.source_url for launch in launches} == {candidate.source_url}
    assert launches[0].id != launches[1].id


def test_page_with_no_launches_returns_empty_list():
    launches = extract_launches(_make_candidate(), scraper=_fake_scraper())
    assert launches == []


def test_null_property_types_from_llm_becomes_empty_list():
    """Real models (gemma-4) emit `null` for absent lists rather than [].
    Found against live Nawy data — one null must not fail a whole page."""
    raw = {
        "launches": [
            {
                "project_name": "Southmed",
                "launch_type": "new_project",
                "property_types": None,
                "confidence": 1.0,
            }
        ]
    }
    scraper = MagicMock()
    scraper.run.return_value = raw

    launches = extract_launches(_make_candidate(), scraper=scraper)

    assert len(launches) == 1
    assert launches[0].property_types == []


def test_missing_confidence_defaults_rather_than_dropping_launch():
    raw = {"launches": [{"project_name": "Salt Marina", "launch_type": "new_project"}]}
    scraper = MagicMock()
    scraper.run.return_value = raw

    launches = extract_launches(_make_candidate(), scraper=scraper)

    assert launches[0].confidence == 0.5
