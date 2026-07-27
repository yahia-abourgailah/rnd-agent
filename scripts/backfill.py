"""One-time (re-runnable) backfill of Nawy's full catalogue into the relational
tables: developers, areas, projects, units, availability.

Load order matters — developers and areas first, so projects' foreign keys
resolve; projects before units, so units' project_id resolves.

Usage:
    python scripts/backfill.py                     # units for launches only (fast)
    python scripts/backfill.py --units all         # units for ALL projects (slow)
    python scripts/backfill.py --limit 50          # only first 50 compounds (smoke test)

Re-running is safe: every entity upserts on (source, source_id).
"""

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from launch_intel.backfill import nawy_client as nc  # noqa: E402
from launch_intel.db import repository as repo  # noqa: E402
from launch_intel.watch.fetcher import Fetcher  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("backfill")


async def run(units_scope: str, limit: int | None) -> None:
    fetcher = Fetcher(rate_limit_seconds=3)

    # 0. Which compounds are currently "launches" — so projects get is_launch
    #    set in a single pass (no second UPDATE stage).
    launch_ids = await nc.fetch_launch_compound_ids(fetcher)
    logger.info("new-launches feed: %d launch compounds", len(launch_ids))

    # 1. Developers
    dev_raw = await nc.fetch_developers(fetcher)
    developers = [d for d in (nc.map_developer(r) for r in dev_raw) if d]
    logger.info("fetched %d developers", len(developers))

    # 2. Areas
    area_raw = await nc.fetch_areas(fetcher)
    areas = [a for a in (nc.map_area(r) for r in area_raw) if a]
    logger.info("fetched %d areas", len(areas))

    # 3. Compounds -> projects
    comp_raw = await nc.fetch_compounds(fetcher, limit=limit)
    projects = [p for p in (nc.map_compound(r, launch_ids) for r in comp_raw) if p]
    logger.info("fetched %d compounds (projects)", len(projects))

    # 3a. Gap-fill: some developer/area ids referenced by compounds are not
    #     returned by the entity endpoints (leaf areas, etc.). Create minimal
    #     rows for them so every project FK resolves.
    developers += nc.developers_from_compounds(comp_raw)
    areas += nc.areas_from_compounds(comp_raw)

    # 4. Persist entities in FK order, collecting source_id -> db id maps.
    dev_map = repo.upsert_developers(developers)
    area_map = repo.upsert_areas(areas)
    project_map = repo.upsert_projects(projects, dev_map, area_map)
    logger.info(
        "upserted developers=%d areas=%d projects=%d",
        len(dev_map), len(area_map), len(project_map),
    )

    # 5. Units — launches only (default) or every project.
    if units_scope == "all":
        target_ids = [int(p.source_id) for p in projects]
    else:
        target_ids = [cid for cid in launch_ids]
        if limit is not None:
            loaded = {int(p.source_id) for p in projects}
            target_ids = [cid for cid in target_ids if cid in loaded]
    logger.info("fetching units for %d compounds (scope=%s)", len(target_ids), units_scope)

    unit_raw = await nc.fetch_units_for_compounds(fetcher, target_ids)
    units = [u for u in (nc.map_unit(r) for r in unit_raw) if u]
    n_units = repo.upsert_units(units, project_map)
    logger.info("upserted %d units", n_units)

    # 6. Availability snapshot, computed from the units just loaded.
    snapshots = nc.compute_availability(units, datetime.now(timezone.utc))
    n_avail = repo.save_availability(snapshots, project_map)
    logger.info("wrote %d availability snapshots", n_avail)

    # 7. Summary
    counts = repo.entity_counts()
    logger.info("DONE. table row counts: %s", counts)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--units",
        choices=["launches", "all"],
        default="launches",
        help="Fetch per-unit rows for launches only (default) or every project.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap the number of compounds loaded (smoke test).",
    )
    args = parser.parse_args()
    asyncio.run(run(args.units, args.limit))


if __name__ == "__main__":
    main()
