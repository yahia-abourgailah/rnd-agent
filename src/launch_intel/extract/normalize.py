"""
Light, deterministic cleanup applied to LLM output before it becomes a
Launch — whitespace/casing/known-alias fixes only. Fuzzy matching against a
canonical developer/zone list (RapidFuzz, cross-launch) is dedup's job, not
extraction's — see TODO(phase2) in dedup/matcher.py.
"""

# TODO(phase2): grow this alongside real source data, or replace with a
# lookup table seeded from db once dedup exists.
_DEVELOPER_ALIASES = {
    "sodic": "SODIC",
    "palm hills": "Palm Hills Developments",
    "emaar misr": "Emaar Misr",
}

_ZONE_ALIASES = {
    "new cairo": "New Cairo",
    "6th of october": "6th of October",
    "north coast": "North Coast",
    "sheikh zayed": "Sheikh Zayed",
}


def normalize_developer(raw: str | None) -> str | None:
    if raw is None:
        return None
    cleaned = raw.strip()
    return _DEVELOPER_ALIASES.get(cleaned.lower(), cleaned)


def normalize_zone(raw: str | None) -> str | None:
    if raw is None:
        return None
    cleaned = raw.strip()
    return _ZONE_ALIASES.get(cleaned.lower(), cleaned)
