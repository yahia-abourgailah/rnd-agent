from datetime import datetime
from enum import Enum

from pydantic import BaseModel

from launch_intel.models.source import SourceType


class ContentType(str, Enum):
    HTML = "html"
    JSON = "json"


class RawPage(BaseModel):
    """
    Output of the watch stage's fetcher — one fetched URL's raw content.
    Consumed by change_detector (has this changed?) and, if changed, by
    extract (turn it into Launch objects).
    """

    url: str
    content: str
    content_type: ContentType
    fetched_at: datetime


class Candidate(BaseModel):
    """
    A single launch-sized snippet carved out of a RawPage by an adapter
    (e.g. one listing card), ready to be handed to the extractor. Keeping this
    separate from RawPage lets one page yield zero, one, or many candidates.
    """

    source_url: str
    source_name: str
    source_type: SourceType
    content_type: ContentType
    text: str
    raw_content_hash: str
