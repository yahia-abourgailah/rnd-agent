"""Cross-source dedup: recognise the same real developer / project reported by
different sources and link duplicates to a canonical row (canonical_id).

Order matters: dedup developers first and repoint projects to the canonical
developer, so project matching can block by developer (only compares projects
of the same company) — faster and far fewer false matches.

Re-runnable: canonical_id is reset and recomputed each run.

Usage:
    python scripts/dedup.py                 # developers + projects
    python scripts/dedup.py --threshold 92  # stricter name matching
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import repository as repo  # noqa: E402
from dedup import matcher, resolver  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("dedup")


def run(threshold: int) -> None:
    # 1. Developers
    developers = repo.all_developers()
    dev_clusters = matcher.cluster_entities(developers, threshold=threshold)
    dev_map = resolver.resolve(dev_clusters, developers)
    repo.set_developer_canonicals(dev_map)
    remapped = repo.remap_projects_to_canonical_developers()
    logger.info(
        "developers: %d rows -> %d duplicate clusters, %d rows merged, %d projects repointed",
        len(developers), len(dev_clusters), len(dev_map), remapped,
    )

    # 2. Projects (block by the now-canonical developer)
    projects = repo.all_projects_for_dedup()
    proj_clusters = matcher.cluster_entities(projects, threshold=threshold, block_key="developer_id")
    proj_map = resolver.resolve(proj_clusters, projects)
    repo.set_project_canonicals(proj_map)
    logger.info(
        "projects: %d rows -> %d duplicate clusters, %d rows merged",
        len(projects), len(proj_clusters), len(proj_map),
    )

    unique_devs = len(developers) - len(dev_map)
    unique_projects = len(projects) - len(proj_map)
    logger.info(
        "DONE. unique developers=%d (was %d), unique projects=%d (was %d)",
        unique_devs, len(developers), unique_projects, len(projects),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threshold", type=int, default=matcher.DEFAULT_THRESHOLD)
    args = parser.parse_args()
    run(args.threshold)


if __name__ == "__main__":
    main()
