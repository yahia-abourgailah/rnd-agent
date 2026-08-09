"""The flow is the only place that writes, so this is where "refuses to persist
a bad run" is proven."""

from datetime import UTC, datetime

import pytest

from collect.base import CollectionResult
from collect.report import StopReason
from models import Project
from pipeline.flows import collect_source


class StubCollector:
    name = "stub"
    min_projects = 5
    rate_limit_seconds = 7

    def __init__(self, project_count, **kwargs):
        self.project_count = project_count
        self.kwargs = kwargs

    async def collect(self):
        return CollectionResult(
            source=self.name,
            developers=[],
            areas=[],
            projects=[
                Project(source="stub", source_id=str(i), name=f"P{i}", min_price=1.0)
                for i in range(self.project_count)
            ],
            units=[],
            fetched_at=datetime.now(UTC),
        )


@pytest.fixture
def writes(monkeypatch):
    recorded = []
    for name in (
        "upsert_developers",
        "upsert_areas",
        "upsert_projects",
        "upsert_units",
        "save_availability",
    ):
        monkeypatch.setattr(
            f"pipeline.flows.repo.{name}",
            lambda *a, _n=name, **k: recorded.append(_n) or {},
        )
    return recorded


@pytest.fixture
def register(monkeypatch):
    built = {}

    def _register(project_count, collector_class=StubCollector):
        def factory(**kwargs):
            built["kwargs"] = kwargs
            return collector_class(project_count, **kwargs)

        factory.name = collector_class.name
        factory.min_projects = collector_class.min_projects
        factory.rate_limit_seconds = collector_class.rate_limit_seconds
        monkeypatch.setattr("pipeline.flows.get_collector_class", lambda name: factory)
        return built

    return _register


async def test_a_healthy_run_persists(register, writes):
    register(10)

    report = await collect_source("stub")

    assert report.stop_reason is StopReason.COMPLETE
    assert "upsert_projects" in writes
    assert "save_availability" in writes


async def test_a_run_below_the_floor_writes_nothing(register, writes):
    """A truncated scrape that persists is worse than one that raises."""
    register(2)

    report = await collect_source("stub")

    assert report.stop_reason is StopReason.BELOW_FLOOR
    assert writes == []


async def test_dry_run_writes_nothing_even_when_healthy(register, writes):
    register(10)

    report = await collect_source("stub", dry_run=True)

    assert report.stop_reason is StopReason.COMPLETE
    assert writes == []


async def test_a_fetch_error_is_reported_not_raised(register, writes):
    """One source failing must not take down the others."""

    class Broken(StubCollector):
        async def collect(self):
            raise TimeoutError("upstream gone")

    register(0, collector_class=Broken)

    report = await collect_source("stub")

    assert report.stop_reason is StopReason.FETCH_ERROR
    assert "TimeoutError" in report.message
    assert writes == []


async def test_the_collector_sets_the_crawl_rate(register, writes):
    """Nawy is crawled at 3s between requests and Property Finder at 2s. A flow
    that built a default Fetcher would silently crawl a competitor's site 50%
    faster than before."""
    built = register(10)

    await collect_source("stub")

    assert built["kwargs"]["fetcher"].rate_limit_seconds == 7
