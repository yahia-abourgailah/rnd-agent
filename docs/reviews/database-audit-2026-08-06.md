# Database audit — 2026-08-06

**Scope:** schema, relations, constraints, indexes, growth, migration hygiene.
**Data audited:** live dev database — 2,135 projects, 8,496 units, 505
developers, 67 areas, 878 availability snapshots, across 2 active sources.
**Verdict:** the relational model is sound and referentially clean. The risks are
not in the shape of the data but in what nothing prevents: one migration hazard
that could destroy data, and a complete absence of database-level invariants.

Findings are ordered by what they cost if ignored.

---

## CRITICAL — `alembic revision --autogenerate` emits `drop_table` for the chatbot's memory

**Fixed in this pass.**

LangGraph's `PostgresSaver.setup()` creates `checkpoints`, `checkpoint_writes`,
`checkpoint_blobs` and `checkpoint_migrations` in the same database. They are not
in `Base.metadata`, so autogenerate classified them as removed tables.

This was not theoretical. Running autogenerate produced:

```python
op.drop_table('checkpoints')
op.drop_table('checkpoint_writes')
op.drop_table('checkpoint_blobs')
op.drop_table('checkpoint_migrations')
```

Anyone adding a column and running the documented autogenerate workflow would
have committed that, and every stored conversation would be gone on the next
`alembic upgrade head`. The handoff document tells an intern to use exactly this
command.

**Fix applied:** `include_name` in `src/db/migrations/env.py` excludes tables
that another system owns, in both online and offline mode. Anything not
described by our models is not ours to drop. `alembic check` now reports no
drift at all.

**Residual risk:** the rule is prefix-based (`checkpoint*`). A future foreign
table with a different name reintroduces the hazard. Anything else sharing this
database needs adding to `_FOREIGN_TABLE_PREFIXES`.

---

## HIGH — no CHECK constraints anywhere; every invariant lives only in Python

`SELECT * FROM pg_constraint WHERE contype='c'` returns **zero rows**.

Every rule this codebase enforces is enforced only on the write path in Python:

| Invariant | Enforced by | What the database allows |
|---|---|---|
| `delivery_date` is a 4-digit year | `delivery_year()` | `'Q4 2027'`, `'next year'`, `''` |
| `sale_type` ∈ (primary, resale) | `SaleType` enum | `'PRIMARY'`, `'resell'`, anything ≤16 chars |
| price and area are non-negative | mapper `or None` | `-1`, `0` |
| `canonical_id` never self-references | union-find structure | `canonical_id = id` |
| `property_types` are canonical | `normalize_property_types()` | `'Twinhouse'` |

The data is currently clean — I checked all five and found zero violations. The
exposure is that nothing keeps it that way. A manual `UPDATE`, a psql session, a
future script that bypasses the mapper, or a restored backup can all violate
these silently, and the first symptom is a wrong number in a report.

This matters more than usual here because the chatbot writes its own SQL against
these tables and the insight endpoints aggregate them directly. `insights.py`
already carries a `delivery_date ~ '^[0-9]{4}'` regex guard — a workaround for an
invariant the schema should hold.

**Recommended:** add CHECK constraints for the five rules above. They are cheap,
they are documentation the database enforces, and they convert a silent wrong
answer into a loud write failure. Not applied in this pass because it is a
schema change that deserves its own migration and review.

---

## HIGH — `availability` grows to millions of rows with no partitioning and no source index

Once the multi-source design ships, this table takes 2,135 projects × 4 runs/day
≈ 8.5k rows/day, ~3M/year, and it is the table every trend query will read.

Two gaps:

1. **No index on `source_id`.** The only index is `(project_id, snapshot_at)`.
   "Latest snapshot per source for this project" and "how did Nawy's prices move"
   both scan. Add `(source_id, snapshot_at)`.
2. **No partitioning strategy.** Fine to 10M rows; beyond that, monthly range
   partitioning on `snapshot_at` keeps queries and vacuum bounded. The decision
   is cheap now and expensive after the table is large.

The planned unique constraint `(project_id, source_id, snapshot_at)` (Task 6 of
the implementation plan) doubles as the missing index if declared in that column
order — worth ordering it `(source_id, project_id, snapshot_at)` instead, so it
serves both purposes.

---

## MEDIUM — the same relationship has three different delete behaviours

`canonical_id` means one thing but behaves three ways:

| Table | On delete of the canonical row |
|---|---|
| `areas.canonical_id` | `SET NULL` |
| `developers.canonical_id` | `NO ACTION` |
| `projects.canonical_id` | `NO ACTION` |

Deleting a canonical area silently un-deduplicates its duplicates; deleting a
canonical developer raises a foreign key error instead. Same concept, opposite
outcomes, and neither is documented as intentional — the `SET NULL` came from the
areas migration written yesterday, the others from an earlier one.

`SET NULL` is the right semantic for all three: a duplicate whose canonical row
disappears should become canonical again, not block the delete.

Also worth noting: **nothing prevents a canonical chain.** `A → B → C` currently
does not occur (union-find always points at a root, verified: zero multi-hop
chains), but if a future dedup change produced one, every `WHERE canonical_id IS
NULL` count — which is now baked into the chatbot's system prompt and the
insight endpoints — would silently undercount. A CHECK cannot express this;
a trigger or a post-dedup assertion can.

---

## MEDIUM — `units.raw` is 75% of the units table

| Table | Rows | Total | Of which raw JSONB |
|---|---|---|---|
| units | 8,496 | 16 MB | 12 MB |
| projects | 2,135 | 6.8 MB | 2.3 MB |

Keeping `raw` has already paid for itself: yesterday's resale-price correction
recomputed 101 rows from `projects.raw`, which would have been impossible
otherwise. The point is not to remove it but to be deliberate:

- At this size it is free. At 10 sources and full unit coverage it dominates
  storage and every `SELECT *` drags it along.
- Consider `TOAST`-friendly access patterns: never `SELECT *` from `units` in
  application code, and if raw is only needed for repair, a separate
  `unit_payloads` table keyed by unit id keeps the hot table narrow.

No action needed now. Revisit when units pass ~100k rows.

---

## LOW — three tables have never held a row

`launches`, `raw_content` and `fetch_log` are all empty. They belong to the LLM
extraction path, which is blocked on the scrapegraphai / Python 3.11 dependency
conflict. That is a known, tracked issue, not schema rot — but it means that
part of the schema has never been exercised against real data, and its
constraints and indexes are unvalidated. Treat the first real extraction run as
a schema test, not just a feature test.

`sources` also carries `sodic` and `palm_hills` rows with no collector and no
data. Harmless, but a reader cannot distinguish "registered, not built" from
"built, currently empty". The `is_active` column already exists — set it false
for sources with no collector.

---

## What is sound, and should not be re-litigated

Checked and found correct, so the next reviewer need not repeat it:

- **Referential integrity is clean.** Zero orphaned projects, units, or
  availability rows; zero projects with a missing developer or area; zero
  self-referencing canonical rows; zero multi-hop canonical chains.
- **Identity model is right.** A generated UUID primary key with a separate
  `external_ref` unique key per source is the correct way to hold the same
  real-world entity from several origins. It is what makes re-syncs idempotent
  and cross-source dedup expressible.
- **Not-null discipline on the columns that matter.** `name`, `source_id`,
  `external_ref` and `is_launch` are all NOT NULL; the genuinely optional fields
  (`min_price`, `sale_type`) are nullable, which is honest.
- **Index coverage matches the actual query patterns** for projects and units —
  every foreign key used in a join is indexed, plus `is_launch` and the
  `canonical_id` columns that dedup-aware queries filter on.
- **The upsert semantics are deliberate and documented** — field-wise merge for
  duplicate refs, COALESCE so a partial re-sync enriches rather than blanks. The
  known cost (a mapping fix does not repair stored rows) is written down and has
  a worked precedent in the resale-price migration.
- **Migration chain is linear and each step is reversible** except two data
  corrections where reversal would reintroduce the defect, and both say so.

---

## Recommended order of work

1. **Add the CHECK constraints** (HIGH). One migration, five constraints, and the
   invariants stop depending on every future writer remembering them.
2. **Make `canonical_id` uniformly `SET NULL`** (MEDIUM). Same migration.
3. **Order the planned availability unique constraint `(source_id, project_id,
   snapshot_at)`** so it also serves as the missing source index (MEDIUM). This
   is a one-line change to Task 6 of the implementation plan, free if done now.
4. **Set `is_active = false` for sources with no collector** (LOW).
5. **Revisit `units.raw` placement** when units pass ~100k rows.

Items 1–3 are worth doing before the multi-source pipeline lands, because each
becomes more expensive once three sources are writing and the snapshot table is
large.
