"""Aggressive name normalisation for MATCHING (distinct from extract/normalize.py,
which does light display cleanup). Here we strip everything that varies between
sources — legal suffixes, parentheticals, punctuation, case — so "SODIC",
"Sodic" and "SODIC Developments" all collapse to the same match key."""

import re

# Corporate/real-estate noise words dropped before comparing names.
_NOISE = {
    "developments", "development", "developer", "developers",
    "properties", "property", "real", "estate", "for", "investment",
    "investments", "group", "holding", "holdings", "company", "co",
    "egypt", "misr", "sae", "the", "and",
}
_PAREN = re.compile(r"\([^)]*\)")
_NON_ALNUM = re.compile(r"[^a-z0-9\s]")
_SPACES = re.compile(r"\s+")


def normalize_name(name: str | None) -> str:
    """Reduce a name to a comparable match key (lowercase, no noise words)."""
    if not name:
        return ""
    text = _PAREN.sub(" ", name.lower())
    text = _NON_ALNUM.sub(" ", text)
    tokens = [t for t in _SPACES.sub(" ", text).strip().split(" ") if t and t not in _NOISE]
    return " ".join(tokens)
