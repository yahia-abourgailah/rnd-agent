from datetime import datetime
from unittest.mock import MagicMock

from launch_intel.extract.extractor import ExtractedFields, extract_launch
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


def _fake_client(extracted: ExtractedFields) -> MagicMock:
    client = MagicMock()
    client.chat.completions.create.return_value = extracted
    return client


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

    launch = extract_launch(candidate, client=_fake_client(extracted))

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

    launch = extract_launch(candidate, client=_fake_client(extracted))

    assert launch.developer == "Some New Developer"
    assert launch.zone == "Some Unlisted Zone"


def test_extract_launch_low_confidence_is_still_returned_not_dropped():
    extracted = ExtractedFields(
        project_name="Ambiguous Mention",
        launch_type=LaunchType.REPRICING,
        confidence=0.05,
    )
    candidate = _make_candidate()

    launch = extract_launch(candidate, client=_fake_client(extracted))

    assert launch.confidence == 0.05
    assert launch.project_name == "Ambiguous Mention"
