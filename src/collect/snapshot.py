"""One availability snapshot per project per run, for every source.

Sources without unit rows contribute price and delivery only; that is still
enough for price movement and new-entrant detection, and a project with no
snapshot has no history at all. History cannot be backfilled, so a run writes a
snapshot whether or not anything changed.
"""

from collect.base import CollectionResult
from collect.nawy import compute_availability
from models import Availability


def snapshots_for(result: CollectionResult) -> list[Availability]:
    """A snapshot for every project the run collected.

    Projects whose units were collected get the full rollup — unit counts,
    price range, price per sqm. The rest get what the project record itself
    knows.
    """
    rollups = {
        snapshot.project_source_id: snapshot
        for snapshot in compute_availability(result.units, result.fetched_at)
    }

    return [
        rollups.get(project.source_id)
        or Availability(
            source=result.source,
            project_source_id=project.source_id,
            snapshot_at=result.fetched_at,
            min_price=project.min_price,
            delivery_range=project.delivery_date,
        )
        for project in result.projects
    ]
