import asyncio
import logging
import sys

from prefect import flow

from collect.registry import get_collector_class
from collect.report import RunReport, StopReason, evaluate
from collect.snapshot import snapshots_for
from db import repository as repo
from dedup import matcher, resolver
from dedup.normalize import normalize_area_name
from pipeline.tasks import (
    extract_candidates,
    fetch_source_pages,
    find_changed_candidates,
    load_source_config,
    persist_launches,
)
from watch import ChangeDetector
from watch.fetcher import Fetcher

logger = logging.getLogger(__name__)

#: Per-source minimum share of projects carrying a field. Guards the failure a
#: record count cannot see: the expected number of rows, every field empty.
#: Values sit below what each source actually delivers, measured on a full run.
COVERAGE_FLOORS: dict[str, dict[str, float]] = {
    "nawy": {"name": 0.99},
    "property_finder": {"name": 0.99, "delivery_date": 0.8},
}


@flow(name="crawl-one-source")
async def crawl_one_source(source_name: str) -> int:
    """
    Crawl one source -> store the raw payload -> detect change -> extract ->
    persist. Returns the number of launches saved.

    Deliberately thin — every decision (what changed, how to parse, how to
    extract) lives in watch/, extract/ and db/ so those stages stay testable
    without Prefect running at all.

    TODO(phase2): dedup.resolver plugs in between extract and persist, so a
      launch seen on several sources merges instead of inserting duplicates.
    TODO(phase3): notify.router plugs in after a launch is persisted as new.
    """
    source = load_source_config(source_name)
    pages = await fetch_source_pages(source)

    detector = ChangeDetector()
    candidates = find_changed_candidates(source, pages, detector)

    if not candidates:
        logger.info("No new/changed content for source=%s", source_name)
        return 0

    launches = extract_candidates(candidates)
    saved = persist_launches(launches)

    logger.info("source=%s saved=%d", source_name, saved)
    return saved


if __name__ == "__main__":
    source_name = sys.argv[1] if len(sys.argv) > 1 else "generic_developer_demo"
    asyncio.run(crawl_one_source(source_name))


@flow(name="collect-one-source")
async def collect_source(
    source_name: str, dry_run: bool = False, limit: int | None = None
) -> RunReport:
    """Collect one source and persist it, unless the run fails its floors.

    Returns a report rather than raising: one source failing must leave the
    others untouched, and the reason belongs in the report rather than being
    inferred from whatever ends up in the tables.
    """
    collector_class = get_collector_class(source_name)
    collector = collector_class(
        fetcher=Fetcher(rate_limit_seconds=collector_class.rate_limit_seconds),
        limit=limit,
    )

    try:
        result = await collector.collect()
    except Exception as exc:
        logger.exception("collect source=%s stop_reason=fetch_error", source_name)
        return RunReport(
            source_name,
            StopReason.FETCH_ERROR,
            {},
            {},
            f"{type(exc).__name__}: {exc}",
        )

    report = evaluate(
        result, collector_class.min_projects, COVERAGE_FLOORS.get(source_name, {})
    )
    if not report.ok:
        logger.error(
            "collect source=%s stop_reason=%s %s",
            source_name,
            report.stop_reason.value,
            report.message,
        )
        return report

    if dry_run:
        logger.info("collect source=%s dry_run counts=%s", source_name, report.counts)
        return report

    developer_map = repo.upsert_developers(result.developers)
    area_map = repo.upsert_areas(result.areas)
    project_map = repo.upsert_projects(result.projects, developer_map, area_map)
    repo.upsert_units(result.units, project_map)
    repo.save_availability(snapshots_for(result), project_map)

    logger.info(
        "collect source=%s stop_reason=complete counts=%s", source_name, report.counts
    )
    return report


@flow(name="dedup-catalogue")
def dedup_catalogue(threshold: int = matcher.DEFAULT_THRESHOLD) -> dict[str, int]:
    """Link the same developer, project and area across sources.

    Runs after collection, never inside it: a source run rewrites
    projects.developer_id from that source's own developer, which undoes the
    remapping onto canonical developers. Collection that is not followed by
    dedup leaves the catalogue counting one company as several, and the API
    keeps answering — with wrong numbers.
    """
    developers = repo.all_developers()
    developer_map = resolver.resolve(
        matcher.cluster_entities(developers, threshold=threshold), developers
    )
    repo.set_developer_canonicals(developer_map)
    repointed = repo.remap_projects_to_canonical_developers()

    projects = repo.all_projects_for_dedup()
    project_map = resolver.resolve(
        matcher.cluster_entities(projects, threshold=threshold, block_key="developer_id"),
        projects,
    )
    repo.set_project_canonicals(project_map)

    areas = repo.all_areas_for_dedup()
    area_map = resolver.resolve(
        matcher.cluster_entities(areas, threshold=threshold, normalizer=normalize_area_name),
        areas,
    )
    repo.set_area_canonicals(area_map)

    merged = {
        "developers_merged": len(developer_map),
        "projects_merged": len(project_map),
        "areas_merged": len(area_map),
        "projects_repointed": repointed,
    }
    logger.info("dedup %s", merged)
    return merged
