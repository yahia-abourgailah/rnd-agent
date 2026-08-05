"""Versioned prompt text, kept out of orchestration code so diffs stay readable
and an eval run can pin the exact version it scored."""

from pathlib import Path

SYSTEM_PROMPT_VERSION = "system_v1"


def load_system_prompt(version: str = SYSTEM_PROMPT_VERSION) -> str:
    return (Path(__file__).parent / f"{version}.md").read_text(encoding="utf-8").strip()
