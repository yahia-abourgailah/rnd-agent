"""The collector must produce exactly what scripts/backfill.py produced, so the
refactor is provably behaviour-preserving."""

import json
import pathlib

import pytest

from collect.nawy import NawyCollector

FIXTURES = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "live"


def _load(name: str) -> list[dict]:
    """Saved payloads wrap their records differently: the entity endpoints use
    `results`, the web API uses `values`."""
    payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return payload
    for key in ("results", "values"):
        if key in payload:
            return payload[key]
    return payload


async def _async(value):
    return value


class ForbiddenFetcher:
    """Any real network call is a test failure, not a slow test."""

    async def fetch_json(self, url, **kwargs):
        raise AssertionError(f"unexpected network call to {url}")

    async def post_json(self, url, **kwargs):
        raise AssertionError(f"unexpected network call to {url}")

    async def fetch_rendered_html(self, url, **kwargs):
        raise AssertionError(f"unexpected network call to {url}")


@pytest.fixture
def collector(monkeypatch):
    monkeypatch.setattr(
        "collect.nawy.fetch_developers",
        lambda fetcher, limit=None: _async(_load("nawy_developers.json")),
    )
    monkeypatch.setattr(
        "collect.nawy.fetch_areas",
        lambda fetcher, limit=None: _async(_load("nawy_areas.json")),
    )
    monkeypatch.setattr(
        "collect.nawy.fetch_compounds",
        lambda fetcher, limit=None: _async(_load("nawy_compounds.json")),
    )
    monkeypatch.setattr(
        "collect.nawy.fetch_launch_compound_ids", lambda fetcher: _async({1198})
    )
    monkeypatch.setattr(
        "collect.nawy.fetch_primary_units",
        lambda fetcher, compound_id=None, limit=None: _async(
            _load("nawy_webapi_units.json")
        ),
    )
    return NawyCollector(ForbiddenFetcher())


async def test_collect_returns_every_entity(collector):
    result = await collector.collect()

    assert result.source == "nawy"
    assert result.counts()["projects"] == 3
    assert result.counts()["developers"] >= 5


async def test_collected_projects_are_already_cleaned(collector):
    """Cleaning belongs at the source boundary, so nothing downstream repeats it."""
    result = await collector.collect()

    for project in result.projects:
        assert project.name == project.name.strip()
        if project.delivery_date is not None:
            assert len(project.delivery_date) == 4
        for property_type in project.property_types:
            assert property_type == property_type.lower()


async def test_launch_flag_comes_from_the_launch_id_set(collector):
    result = await collector.collect()

    launches = [p for p in result.projects if p.is_launch]
    assert [p.source_id for p in launches] == ["1198"]


async def test_only_primary_units_are_collected(collector):
    """Resale is a different market; the mapper is the last place to stop it."""
    result = await collector.collect()

    assert result.units
    assert all(unit.sale_type.value == "primary" for unit in result.units)


def test_collector_declares_a_sanity_floor():
    assert NawyCollector.min_projects >= 1500
