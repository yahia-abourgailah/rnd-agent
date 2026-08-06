import json
import pathlib

import pytest

from collect.property_finder import PropertyFinderCollector

FIXTURE = (
    pathlib.Path(__file__).resolve().parents[1]
    / "fixtures"
    / "live"
    / "property_finder_new_projects.json"
)


async def _async(value):
    return value


class ForbiddenFetcher:
    async def fetch_json(self, url, **kwargs):
        raise AssertionError(f"unexpected network call to {url}")


@pytest.fixture
def projects_payload():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["projects"]


@pytest.fixture
def collector(monkeypatch, projects_payload):
    monkeypatch.setattr(
        "collect.property_finder.fetch_projects",
        lambda fetcher, limit=None: _async(projects_payload),
    )
    return PropertyFinderCollector(ForbiddenFetcher())


async def test_collect_derives_developers_and_areas_from_projects(collector):
    """Property Finder exposes no standalone developer or area feed."""
    result = await collector.collect()

    assert result.source == "property_finder"
    assert result.projects
    assert result.developers
    assert result.areas


async def test_property_finder_contributes_no_units(collector):
    """Its listing carries no per-unit rows; units must be empty, not invented."""
    result = await collector.collect()

    assert result.units == []


async def test_completed_developments_are_not_flagged_as_launches(collector):
    """The feed is called new-projects but carries finished developments."""
    result = await collector.collect()

    flags = [p.is_launch for p in result.projects]
    assert any(flags) and not all(flags)


async def test_entities_are_reported_once_each(collector):
    """A doubled entity list halves every coverage figure and makes the sanity
    floor describe a catalogue that does not exist."""
    result = await collector.collect()

    for entity in ("developers", "areas", "projects"):
        source_ids = [row.source_id for row in getattr(result, entity)]
        assert len(source_ids) == len(set(source_ids)), entity


async def test_collected_projects_are_already_cleaned(collector):
    result = await collector.collect()

    for project in result.projects:
        assert project.name == project.name.strip()
        if project.delivery_date is not None:
            assert len(project.delivery_date) == 4
        if project.slug is not None:
            assert "/" not in project.slug
        for property_type in project.property_types:
            assert property_type == property_type.lower()


def test_collector_declares_a_sanity_floor():
    assert PropertyFinderCollector.min_projects >= 1000
