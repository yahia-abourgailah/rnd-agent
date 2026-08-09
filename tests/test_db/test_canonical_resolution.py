"""Collection must not undo dedup.

upsert_projects writes developer_id from the source's own developer. Dedup then
repointed duplicates onto the canonical developer as a separate pass, so the
next collection reversed it — and with Nawy collecting every 6 hours against a
daily dedup, the catalogue spent almost all its time counting one company as
several while the API answered confidently.
"""

import uuid

from db.repository import through_canonical


def test_a_duplicate_resolves_to_its_canonical():
    duplicate, canonical = uuid.uuid4(), uuid.uuid4()

    assert through_canonical(duplicate, {duplicate: canonical}) == canonical


def test_a_canonical_row_resolves_to_itself():
    canonical = uuid.uuid4()

    assert through_canonical(canonical, {}) == canonical


def test_absent_stays_absent():
    assert through_canonical(None, {uuid.uuid4(): uuid.uuid4()}) is None


def test_resolution_does_not_chain_endlessly():
    """Union-find always points at a root, but a single hop is all that is
    applied — a chain would otherwise loop here rather than fail loudly."""
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    assert through_canonical(a, {a: b, b: c}) == b
