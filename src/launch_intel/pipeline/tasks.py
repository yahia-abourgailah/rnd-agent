import logging

import yaml
from prefect import task

from config.settings import settings
from launch_intel.db.repository import save_launches, store_fetch
from launch_intel.extract import extract_launches
from launch_intel.models import Candidate, Launch, RawPage, SourceConfig
from launch_intel.watch import BaseAdapter, ChangeDetector, hash_content
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
        changed = detector.has_changed(page.url, page.content)
        # Persist BEFORE deciding what to do with it. Competitor sites
        # overwrite their pages, so a payload we fetched but didn't store is
        # unrecoverable — and every stored page is a test case for future
        # prompt changes. Unchanged pages cost only a fetch_log row.
        store_fetch(page, source.name, hash_content(page.content), changed)
        if not changed:
            logger.info("No change detected for %s, skipping", page.url)
            continue
        candidates.extend(adapter.parse_candidates(page))
        detector.mark_seen(page.url, page.content)
    return candidates


@task
def extract_candidates(candidates: list[Candidate]) -> list[Launch]:
    """One candidate can yield several launches (a page often lists multiple
    projects), so results are flattened into a single list."""
    launches: list[Launch] = []
    for candidate in candidates:
        launches.extend(extract_launches(candidate))
    return launches


@task
def persist_launches(launches: list[Launch]) -> int:
    """TODO(phase2): dedup runs before this, so repeat sightings of the same
    launch merge into one row instead of inserting a duplicate."""
    saved = save_launches(launches)
    logger.info("Saved %d launches", saved)
    return saved
