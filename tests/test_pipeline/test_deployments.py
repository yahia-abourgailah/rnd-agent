"""Schedules are configuration, but a missing or mis-ordered one fails silently:
the API keeps answering, with stale or un-deduplicated numbers."""

from collect.registry import COLLECTOR_REGISTRY
from pipeline.deployments import DEDUP_DEPLOYMENT, SCHEDULES, deployment_specs


def test_every_registered_source_has_a_schedule():
    """A source that collects but is never scheduled looks healthy and serves
    stale data forever."""
    assert set(SCHEDULES) == set(COLLECTOR_REGISTRY)


def test_each_source_gets_its_own_deployment():
    """One deployment per source is what stops a failing source blocking the
    others."""
    specs = deployment_specs()
    source_specs = [s for s in specs if s["parameters"].get("source_name")]

    assert len(source_specs) == len(COLLECTOR_REGISTRY)
    assert len({s["name"] for s in specs}) == len(specs)


def test_dedup_is_scheduled_too():
    """Existing links now survive collection (upsert_projects resolves through
    canonical), but new duplicates only appear when dedup runs. Unscheduled, a
    newly collected duplicate is never linked to anything."""
    names = {spec["name"] for spec in deployment_specs()}

    assert DEDUP_DEPLOYMENT["name"] in names


def test_dedup_runs_after_any_daily_source():
    """So the day's new rows are linked the same day rather than waiting for the
    next run. Vacuous until a daily source is registered — it guards Aqarmap,
    which is scheduled daily because it is fetched page by page."""
    dedup_hour = _hour(DEDUP_DEPLOYMENT["cron"])
    daily = {name: cron for name, cron in SCHEDULES.items() if _is_daily(cron)}

    for name, cron in daily.items():
        assert _hour(cron) < dedup_hour, name


def test_api_sources_poll_more_often_than_once_a_day():
    """An API scan is cheap enough to run repeatedly; the cadence should reflect
    that rather than defaulting everything to daily."""
    assert not _is_daily(SCHEDULES["nawy"])
    assert not _is_daily(SCHEDULES["property_finder"])


def _hour(cron: str) -> int:
    return int(cron.split()[1])


def _is_daily(cron: str) -> bool:
    return "*/" not in cron.split()[1]
