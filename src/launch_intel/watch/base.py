from abc import ABC, abstractmethod
from typing import ClassVar

from launch_intel.models import Candidate, RawPage, SourceConfig
from launch_intel.watch.fetcher import Fetcher


class BaseAdapter(ABC):
    """
    Interface every source implements. An adapter knows *how* to fetch a
    specific site's pages and *how* to carve raw content into per-launch
    candidates — it does not detect changes (change_detector.py) or run
    extraction (extract/extractor.py).
    """

    #: Must match `adapter_name` in config/sources.yaml and the key it's
    #: registered under in watch/adapters/__init__.py.
    adapter_name: ClassVar[str]

    def __init__(self, source: SourceConfig, fetcher: Fetcher | None = None):
        self.source = source
        self.fetcher = fetcher or Fetcher(rate_limit_seconds=source.rate_limit_seconds)

    @abstractmethod
    async def fetch_pages(self) -> list[RawPage]:
        """Fetch every configured URL for this source and return raw pages."""
        raise NotImplementedError

    @abstractmethod
    def parse_candidates(self, page: RawPage) -> list[Candidate]:
        """
        Split one fetched page into individual launch-sized candidates
        (e.g. one per listing card / news item). Return an empty list if the
        page contains nothing extraction-worthy right now.
        """
        raise NotImplementedError
