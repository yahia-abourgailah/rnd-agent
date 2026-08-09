"""Monitoring endpoints — data-quality health of the catalogue."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.dependencies import get_session
from api.schemas import QualityResponse
from metrics import quality

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


@router.get("/quality", response_model=QualityResponse)
def data_quality(session: Session = Depends(get_session)) -> QualityResponse:
    """Cross-source duplicate rate, per-source coverage, and field completeness.

    Precision/recall need a labelled eval set (not built yet), so they're absent."""
    dups = quality.duplicate_rates(session)
    return QualityResponse(
        developers=dups["developers"],
        projects=dups["projects"],
        source_coverage=quality.source_coverage(session),
        source_overlap=quality.source_overlap(session),
        completeness=quality.completeness(session),
        note="Precision/recall require a labelled eval set (task not yet done).",
    )
