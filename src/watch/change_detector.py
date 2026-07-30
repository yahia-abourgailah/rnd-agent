import hashlib
import json
from pathlib import Path

_DEFAULT_STATE_PATH = Path(".crawl_state.json")


def hash_content(content: str) -> str:
    """Stable content hash used both for change detection and as
    Candidate/SourceEvidence.raw_content_hash."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class ChangeDetector:
    """
    Cheap "did this page change since last crawl?" check, kept deliberately
    separate from extraction so the expensive LLM call only runs on content
    that's actually new.

    TODO(phase-later): this stores last-seen hashes in a local JSON file as a
    placeholder. Once db/tables.py exists, swap _load_state/_save_state for a
    table keyed on source_url so state is shared across workers/deploys.
    """

    def __init__(self, state_path: Path | None = None):
        self.state_path = state_path or _DEFAULT_STATE_PATH
        self._state: dict[str, str] = self._load_state()

    def _load_state(self) -> dict[str, str]:
        if self.state_path.exists():
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        return {}

    def _save_state(self) -> None:
        self.state_path.write_text(json.dumps(self._state, indent=2), encoding="utf-8")

    def has_changed(self, url: str, content: str) -> bool:
        return self._state.get(url) != hash_content(content)

    def mark_seen(self, url: str, content: str) -> None:
        self._state[url] = hash_content(content)
        self._save_state()
