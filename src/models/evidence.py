import uuid
from datetime import datetime

from pydantic import BaseModel


class SourceEvidence(BaseModel):
    """
    Links one source hit to a Launch, so Phase 2 (dedup) can group multiple
    evidence records that turn out to describe the same real-world launch.

    launch_id must be set to the Launch.id it corresponds to — whatever code
    constructs a Launch + SourceEvidence together is responsible for passing
    the same UUID to both (see extract/extractor.py).
    """

    launch_id: uuid.UUID
    source_url: str
    source_name: str  # matches SourceConfig.name
    observed_at: datetime
    raw_content_hash: str  # ties back to change_detector's content hash
