import asyncio
import logging
import sys

from prefect import flow

from launch_intel.pipeline.tasks import (
    extract_candidates,
    fetch_source_pages,
    find_changed_candidates,
    load_source_config,
    persist_launches,
)
from launch_intel.watch import ChangeDetector

logger = logging.getLogger(__name__)


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
