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

# Phase numbering arrives in both notations across sources; folding Roman to
# Arabic makes "Phase II" and "Phase 2" one key, while keeping "Phase I" and
# "Phase II" distinct — phases are what this product exists to spot.
_ROMAN_TOKENS = {
    "i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5",
    "vi": "6", "vii": "7", "viii": "8", "ix": "9", "x": "10",
}


def normalize_name(name: str | None) -> str:
    """Reduce a name to a comparable match key (lowercase, no noise words).

    Names made entirely of noise words ("Egypt Real Estate Group") keep their
    tokens instead of normalising to "", which the matcher skips outright — an
    empty key silently excluded those rows from dedup altogether.
    """
    if not name:
        return ""
    text = _PAREN.sub(" ", name.lower())
    text = _NON_ALNUM.sub(" ", text)
    all_tokens = [
        _ROMAN_TOKENS.get(t, t) for t in _SPACES.sub(" ", text).strip().split(" ") if t
    ]
    tokens = [t for t in all_tokens if t not in _NOISE]
    return " ".join(tokens or all_tokens)
