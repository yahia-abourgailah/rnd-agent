"""Candidate matching: cluster entity rows that refer to the same real-world
thing, using normalised-name equality plus RapidFuzz similarity.

Entities are dicts with at least {id, name}. Optional `block` narrows fuzzy
comparisons to rows sharing a key (e.g. the same developer for projects), which
both speeds things up and prevents cross-context false matches.
"""

import re
from collections import defaultdict

from rapidfuzz import fuzz

from launch_intel.dedup.normalize import normalize_name

DEFAULT_THRESHOLD = 90  # token_sort_ratio; strict enough to avoid false merges
_NUM_RE = re.compile(r"\d+")


def _numbers(name: str) -> list[str]:
    """Numeric tokens in a name. 'La Vista 6' -> ['6']. Numbers distinguish
    real projects (phase 1 ≠ phase 2), so a fuzzy match must agree on them."""
    return sorted(_NUM_RE.findall(name))


class _UnionFind:
    def __init__(self, ids):
        self.parent = {i: i for i in ids}

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def cluster_entities(
    items: list[dict],
    threshold: int = DEFAULT_THRESHOLD,
    block_key: str | None = None,
) -> list[list]:
    """Return clusters (each a list of ≥2 ids) of rows judged the same entity.

    Rows whose normalised names are identical always merge. Beyond that, rows
    are fuzzy-compared (within the same `block_key` bucket, if given).
    """
    norm = {it["id"]: normalize_name(it["name"]) for it in items}
    uf = _UnionFind([it["id"] for it in items])

    # 1) exact normalised-name matches (cheap, high precision)
    by_norm: dict[str, list] = defaultdict(list)
    for it in items:
        if norm[it["id"]]:
            by_norm[norm[it["id"]]].append(it["id"])
    for ids in by_norm.values():
        for other in ids[1:]:
            uf.union(ids[0], other)

    # 2) fuzzy matches within each block
    blocks: dict[object, list[dict]] = defaultdict(list)
    for it in items:
        blocks[it.get(block_key) if block_key else None].append(it)

    for bucket in blocks.values():
        for i in range(len(bucket)):
            id_a, name_a = bucket[i]["id"], norm[bucket[i]["id"]]
            if not name_a:
                continue
            nums_a = _numbers(name_a)
            for j in range(i + 1, len(bucket)):
                id_b, name_b = bucket[j]["id"], norm[bucket[j]["id"]]
                if not name_b or uf.find(id_a) == uf.find(id_b):
                    continue
                # Numbered names must agree on their numbers — "La Vista 1" and
                # "La Vista 2" are distinct projects, not a fuzzy duplicate.
                if _numbers(name_b) != nums_a:
                    continue
                if fuzz.token_sort_ratio(name_a, name_b) >= threshold:
                    uf.union(id_a, id_b)

    clusters: dict[object, list] = defaultdict(list)
    for it in items:
        clusters[uf.find(it["id"])].append(it["id"])
    return [members for members in clusters.values() if len(members) > 1]
