"""Whether a run may be persisted, and why not when it may not.

A run that writes a truncated catalogue is worse than one that raises: the
partial data looks like a real result, and nothing downstream can tell the
difference. So a run is judged before anything is written, and the verdict is
recorded rather than inferred from what happens to be in the tables afterwards.
"""

from dataclasses import dataclass
from enum import Enum

from collect.base import CollectionResult


class StopReason(str, Enum):
    """Why a run ended. Recorded on every exit path.

    Distinguishing these matters at 3am: NO_RECORDS is usually an outage,
    BELOW_FLOOR usually a markup change, FETCH_ERROR usually transport.
    """

    COMPLETE = "complete"
    NO_RECORDS = "no_records"
    BELOW_FLOOR = "below_floor"
    FETCH_ERROR = "fetch_error"


@dataclass
class RunReport:
    """The verdict plus the numbers behind it, so a caller need not re-derive
    them from logs."""

    source: str
    stop_reason: StopReason
    counts: dict[str, int]
    coverage: dict[str, float]
    message: str

    @property
    def ok(self) -> bool:
        return self.stop_reason is StopReason.COMPLETE


def evaluate(
    result: CollectionResult,
    min_projects: int,
    coverage_floors: dict[str, float],
) -> RunReport:
    """Judge a collected result against the source's floors.

    `coverage_floors` guards the failure a count cannot see: a parser returning
    the expected number of rows with every field empty.
    """
    counts = result.counts()
    coverage = result.field_coverage("projects")

    def report(stop_reason: StopReason, message: str) -> RunReport:
        return RunReport(result.source, stop_reason, counts, coverage, message)

    if counts["projects"] == 0:
        return report(StopReason.NO_RECORDS, "no projects returned")

    if counts["projects"] < min_projects:
        return report(
            StopReason.BELOW_FLOOR,
            f"{counts['projects']} projects is below the floor of {min_projects}",
        )

    short = [
        f"{field} {coverage.get(field, 0.0):.0%} < {floor:.0%}"
        for field, floor in coverage_floors.items()
        if coverage.get(field, 0.0) < floor
    ]
    if short:
        return report(
            StopReason.BELOW_FLOOR, "field coverage collapsed: " + ", ".join(short)
        )

    return report(StopReason.COMPLETE, "ok")
