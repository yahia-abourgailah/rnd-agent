"""Candidate matching: cluster entity rows that refer to the same real-world
thing, using normalised-name equality plus RapidFuzz similarity.

Entities are dicts with at least {id, name}. Optional `block` narrows fuzzy
comparisons to rows sharing a key (e.g. the same developer for projects), which
both speeds things up and prevents cross-context false matches.
"""

import re
from collections import defaultdict
from collections.abc import Callable

from rapidfuzz import fuzz

from dedup.normalize import normalize_name

DEFAULT_THRESHOLD = 90  # token_sort_ratio; strict enough to avoid false merges
# Two names of equal length differing in one word score high overall, because
# most of the name matches. "Elan Villas Cairo Gate" and "Eden Villas Cairo
# Gate" are different Emaar projects but score 91. The word that actually
# differs is the whole signal, so it is scored on its own: elan/eden is 50,
# while genuine variants — tower/towers 91, masqad/maqsad 83 — sit well above.
_MIN_DIFFERING_TOKEN_RATIO = 80
# On a short name a single-character edit is a small distance but usually a
# different place: "Maadi" (a Cairo district) and "Makadi" (a Red Sea resort)
# score 91. Below this length only the exact-match pass may merge, which costs
# nothing — every real short-name duplicate seen so far matches exactly.
_MIN_FUZZY_NAME_CHARS = 9
_NUM_RE = re.compile(r"\d+")


def _differing_tokens_agree(name_a: str, name_b: str) -> bool:
    """Whether names of equal word count differ only in near-identical words."""
    tokens_a, tokens_b = name_a.split(), name_b.split()
    if len(tokens_a) != len(tokens_b):
        return True
    return all(
        fuzz.ratio(a, b) >= _MIN_DIFFERING_TOKEN_RATIO
        for a, b in zip(tokens_a, tokens_b, strict=True)
        if a != b
    )


def _numbers(name: str) -> list[str]:
    """Numeric tokens in an already-normalised name. 'La Vista 6' -> ['6'].

    Numbers distinguish real projects (phase 1 is not phase 2), so a fuzzy match
    must agree on them. Roman numerals are already folded to digits by
    normalize_name, so they are covered here too.
    """
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
    normalizer: Callable[[str | None], str] = normalize_name,
) -> list[list]:
    """Return clusters (each a list of ≥2 ids) of rows judged the same entity.

    Rows whose normalised names are identical always merge. Beyond that, rows
    are fuzzy-compared (within the same `block_key` bucket, if given).
    """
    norm = {it["id"]: normalizer(it["name"]) for it in items}
    uf = _UnionFind([it["id"] for it in items])

    blocks: dict[object, list[dict]] = defaultdict(list)
    for it in items:
        blocks[it.get(block_key) if block_key else None].append(it)

    # 1) exact normalised-name matches (cheap, high precision), within a block.
    # Blocking applies here too: two developers each having a project called
    # "The Address" is common, and merging them across developers was exactly
    # what block_key was meant to prevent.
    for bucket in blocks.values():
        by_norm: dict[str, list] = defaultdict(list)
        for it in bucket:
            if norm[it["id"]]:
                by_norm[norm[it["id"]]].append(it["id"])
        for ids in by_norm.values():
            for other in ids[1:]:
                uf.union(ids[0], other)

    # 2) fuzzy matches within each block

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
                if not _differing_tokens_agree(name_a, name_b):
                    continue
                if max(len(name_a), len(name_b)) < _MIN_FUZZY_NAME_CHARS:
                    continue
                if fuzz.token_sort_ratio(name_a, name_b) >= threshold:
                    uf.union(id_a, id_b)

    clusters: dict[object, list] = defaultdict(list)
    for it in items:
        clusters[uf.find(it["id"])].append(it["id"])
    return [members for members in clusters.values() if len(members) > 1]
