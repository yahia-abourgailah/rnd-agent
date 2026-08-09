"""One Prefect deployment per source, plus the dedup pass that must follow them.

Cadence follows collection cost: an API scan can run often, a page-by-page
scrape cannot.

Dedup is scheduled rather than chained because the sources run on different
cadences and must not block one another. It sits after the last daily source of
the day, and is safe to run at any time — it recomputes canonical links from
scratch, so an extra run is a no-op rather than a corruption.
"""

from collect.registry import COLLECTOR_REGISTRY

#: cron, in the scheduler's timezone. Hour matters: dedup must come after the
#: daily sources, because a source run undoes its remapping.
SCHEDULES: dict[str, str] = {
    "nawy": "0 */6 * * *",
    "property_finder": "0 */12 * * *",
}

DEDUP_DEPLOYMENT: dict = {
    "name": "dedup-catalogue",
    "flow": "dedup-catalogue",
    "parameters": {},
    "cron": "0 5 * * *",
}


def deployment_specs() -> list[dict]:
    """Every deployment this project expects to exist.

    Returned as data rather than registered here so it can be asserted in tests
    and applied by whatever runs Prefect, without importing a server.
    """
    specs = [
        {
            "name": f"collect-{name}",
            "flow": "collect-one-source",
            "parameters": {"source_name": name},
            "cron": SCHEDULES[name],
        }
        for name in sorted(COLLECTOR_REGISTRY)
    ]
    specs.append(DEDUP_DEPLOYMENT)
    return specs
