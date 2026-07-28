"""Given matcher clusters, pick the canonical row per cluster and produce the
{duplicate_id -> canonical_id} mapping the repository writes to canonical_id.

Canonical choice: the row from the highest-priority source (lowest source_id —
Nawy=1 is primary), tie-broken by the longer name (usually the more complete)."""


def resolve(clusters: list[list], items: list[dict]) -> dict:
    """Map each non-canonical row id to its cluster's canonical id."""
    by_id = {it["id"]: it for it in items}
    mapping: dict = {}
    for cluster in clusters:
        canonical = min(
            cluster,
            key=lambda i: (by_id[i].get("source_id", 9999), -len(by_id[i].get("name") or "")),
        )
        for member in cluster:
            if member != canonical:
                mapping[member] = canonical
    return mapping
