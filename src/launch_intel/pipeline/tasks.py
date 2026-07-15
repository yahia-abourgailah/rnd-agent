import logging

import yaml
from prefect import task

from config.settings import settings
from launch_intel.extract import extract_launch
from launch_intel.models import Candidate, Launch, RawPage, SourceConfig
from launch_intel.watch import BaseAdapter, ChangeDetector
from launch_intel.watch.adapters import get_adapter_class

logger = logging.getLogger(__name__)


def _build_adapter(source: SourceConfig) -> BaseAdapter:
    return get_adapter_class(source.adapter_name)(source)


@task
def load_source_config(source_name: str, registry_path=None) -> SourceConfig:
    registry_path = registry_path or settings.sources_registry_path
    data = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    for entry in data["sources"]:
        if entry["name"] == source_name:
            return SourceConfig(**entry)
    raise ValueError(f"No source named {source_name!r} in {registry_path}")


@task
async def fetch_source_pages(source: SourceConfig) -> list[RawPage]:
    return await _build_adapter(source).fetch_pages()


@task
def find_changed_candidates(
    source: SourceConfig, pages: list[RawPage], detector: ChangeDetector
) -> list[Candidate]:
    """Cheap change check per page — only carves out candidates (and only
    marks a page seen) for pages whose content actually changed, so
    extract_candidates never runs the expensive LLM call on stale content."""
    adapter = _build_adapter(source)
    candidates: list[Candidate] = []
    for page in pages:
        if not detector.has_changed(page.url, page.content):
            logger.info("No change detected for %s, skipping", page.url)
            continue
        candidates.extend(adapter.parse_candidates(page))
        detector.mark_seen(page.url, page.content)
    return candidates


@task
def extract_candidates(candidates: list[Candidate]) -> list[Launch]:
    return [extract_launch(candidate) for candidate in candidates]
