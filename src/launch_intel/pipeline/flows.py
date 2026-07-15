import asyncio
import json
import logging
import sys

from prefect import flow

from launch_intel.pipeline.tasks import (
    extract_candidates,
    fetch_source_pages,
    find_changed_candidates,
    load_source_config,
)
from launch_intel.watch import ChangeDetector

logger = logging.getLogger(__name__)


@flow(name="crawl-one-source")
async def crawl_one_source(source_name: str) -> list[dict]:
    """
    Phase 1 flow: crawl one source -> detect change -> extract -> log the
    resulting Launch objects as JSON.

    Deliberately thin — every decision (what changed, how to parse, how to
    extract) lives in watch/ and extract/ so those stages stay testable
    without Prefect running at all.

    TODO(phase2): dedup.resolver plugs in here, between extract and storing.
    TODO(phase3): db.repository.save(...) plugs in after dedup.
    TODO(phase3): notify.router plugs in after a launch is saved as new.
    """
    source = load_source_config(source_name)
    pages = await fetch_source_pages(source)

    detector = ChangeDetector()
    candidates = find_changed_candidates(source, pages, detector)

    if not candidates:
        logger.info("No new/changed content for source=%s", source_name)
        return []

    launches = extract_candidates(candidates)

    results = [json.loads(launch.model_dump_json()) for launch in launches]
    for result in results:
        print(json.dumps(result, indent=2, ensure_ascii=False))

    return results


if __name__ == "__main__":
    source_name = sys.argv[1] if len(sys.argv) > 1 else "generic_developer_demo"
    asyncio.run(crawl_one_source(source_name))
