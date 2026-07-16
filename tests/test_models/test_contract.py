"""
Contract tests for the shared models — the interface both developers build
against. If one of these breaks, dedup/notify code on the other side of the
contract probably breaks too.
"""

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from launch_intel.models import (
    Launch,
    LaunchType,
    PropertyType,
    SizeRange,
    SourceConfig,
    SourceEvidence,
    SourceType,
)

REQUIRED_LAUNCH_KWARGS = dict(
    project_name="Marina Heights",
    launch_type=LaunchType.NEW_PROJECT,
    source_url="https://example.com/launch",
    source_type=SourceType.DEVELOPER_SITE,
    first_seen_at=datetime.now(timezone.utc),
    confidence=0.9,
    raw_content="Marina Heights launching now",
)


def test_launch_minimal_required_fields():
    launch = Launch(**REQUIRED_LAUNCH_KWARGS)
    # Everything data-dependent defaults to absent, never to a guessed value
    assert launch.developer is None
    assert launch.zone is None
    assert launch.property_types == []
    assert launch.unit_sizes is None
    assert launch.price_from is None
    assert launch.delivery_date is None


def test_launch_generates_client_side_uuid():
    a = Launch(**REQUIRED_LAUNCH_KWARGS)
    b = Launch(**REQUIRED_LAUNCH_KWARGS)
    assert isinstance(a.id, uuid.UUID)
    assert a.id != b.id


@pytest.mark.parametrize("bad_confidence", [-0.1, 1.1])
def test_launch_confidence_must_be_within_bounds(bad_confidence):
    with pytest.raises(ValidationError):
        Launch(**{**REQUIRED_LAUNCH_KWARGS, "confidence": bad_confidence})


def test_launch_rejects_unknown_launch_type():
    with pytest.raises(ValidationError):
        Launch(**{**REQUIRED_LAUNCH_KWARGS, "launch_type": "price_drop"})


def test_launch_full_record_round_trips_through_json():
    launch = Launch(
        **REQUIRED_LAUNCH_KWARGS,
        developer="SODIC",
        zone="New Cairo",
        property_types=[PropertyType.APARTMENT, PropertyType.TWIN_HOUSE],
        unit_sizes=SizeRange(min_sqm=120, max_sqm=300),
        price_from=5_200_000,
        delivery_date="Q4 2027",
    )
    restored = Launch.model_validate_json(launch.model_dump_json())
    assert restored == launch


def test_source_config_requires_at_least_one_url():
    with pytest.raises(ValidationError):
        SourceConfig(
            name="empty",
            tier=1,
            source_type=SourceType.AGGREGATOR,
            urls=[],
            crawl_frequency="1h",
            adapter_name="nawy",
        )


def test_source_evidence_links_to_launch_id():
    launch = Launch(**REQUIRED_LAUNCH_KWARGS)
    evidence = SourceEvidence(
        launch_id=launch.id,
        source_url=launch.source_url,
        source_name="generic_developer_demo",
        observed_at=datetime.now(timezone.utc),
        raw_content_hash="abc123",
    )
    assert evidence.launch_id == launch.id
