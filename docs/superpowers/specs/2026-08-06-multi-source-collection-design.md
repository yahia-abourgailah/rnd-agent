# Multi-source collection pipeline — design

**Date:** 2026-08-06
**Status:** approved, not yet implemented
**Scope:** Nawy, Property Finder, Aqarmap. Bayut deferred. Social media out of scope.

## Goal

Collect the same real-world projects from several sources on a schedule, so
dedup can confirm a launch across sites and fill each source's gaps, and so
price and availability history accumulates from the day this ships.

Success looks like: adding a source costs one module and one registry line;
one source failing does not stop the others; and a truncated or drifted scrape
refuses to write rather than corrupting the catalogue.

## What each source actually exposes

Established by probing them, not assumed. This is what drives the design.

| Source | Exposes | Collection |
|---|---|---|
| Nawy | JSON API, server-side filters, 500/page | plain Python (working) |
| Property Finder | `__NEXT_DATA__` JSON | plain Python (working) |
| Aqarmap | server-rendered HTML, ~1,988 compounds, no JSON state, no API | HTML parsing (to build) |
| Bayut Egypt | redirects automated requests to `/captchaChallenge` | deferred — see below |

### On LLM extraction vs plain Python

ScrapeGraphAI is not the right tool for Nawy or Property Finder: it would pay a
model to re-derive fields that arrive already labelled, and risk hallucinating
numbers that arrived exact. Those stay plain Python.

The LLM tier earns its place only where the input is genuinely unstructured —
developer press releases, news pages, and later social media. Aqarmap sits in
between: CSS selectors are cheaper and deterministic, so it starts there, and
the LLM path remains available if its markup proves unstable.

This is not "one or the other". It is: **structured source → plain Python;
unstructured source → LLM extraction**, with the collector protocol hiding the
difference from everything downstream.

### On Bayut

Bayut redirects automated requests to a captcha challenge — an explicit
access-control measure. It is registered as a source with no adapter and
`enabled: false`. Nothing in this design works around that control. Adding it
later, via an official API or data partnership, costs one collector module.

## Architecture

```
src/collect/
  base.py            SourceCollector protocol, CollectionResult
  registry.py        name -> collector class
  nawy.py            moved from backfill/nawy_client.py
  property_finder.py moved from backfill/property_finder_client.py
  aqarmap.py         new
src/pipeline/
  flows.py           collect_source(name) — one flow, any source
scripts/
  collect.py         thin CLI over the same flow, with --dry-run
```

The `backfill/` package is renamed to `collect/`: once this runs on a schedule
it is no longer a backfill.

```python
class SourceCollector(Protocol):
    name: str
    min_projects: int              # sanity floor, see Failure modes
    async def collect(self) -> CollectionResult: ...


@dataclass
class CollectionResult:
    source: str
    developers: list[Developer]
    areas: list[Area]
    projects: list[Project]
    units: list[Unit]              # empty where a source has no unit data
    fetched_at: datetime
```

Two rules make the boundary hold:

1. **A collector never touches the database.** It fetches and maps. That makes
   it testable against a saved payload with no infrastructure.
2. **A collector returns contract models, not raw dicts.** Cleaning (`CleanStr`,
   `delivery_year`, `canonical_property_type`, resale exclusion) happens at the
   source boundary, so every source lands in one vocabulary. Cleaning that lives
   in each mapper is how `"Modon "` and `"Modon"` became two developers, and how
   one column came to hold both `"2029"` and `"2029-12-30"`.

The persist path does not change: `repository.upsert_*`, with the field-wise
duplicate merge and COALESCE semantics. Sources change; the write path does not.

## Data flow

Per source, per run:

```
fetch  →  map to contract models  →  CollectionResult
  →  upsert developers → areas → projects → units    (FK order)
  →  one availability snapshot per project
  →  [dedup runs separately, after all sources]
```

Dedup is deliberately **not** part of a source run: it compares rows across
sources, so running it inside a per-source job would make its output depend on
which source finished last.

### Orchestration

One Prefect deployment per source, each on its own cadence (Nawy 6h, Property
Finder 12h, Aqarmap daily), all writing through the same code path. A failing
source cannot block another. `scripts/collect.py` runs the identical flow by
hand, so manual and scheduled runs cannot drift apart.

### History

Reuses the existing `availability` table, which is already a per-project,
time-stamped rollup with price, price-per-sqm and unit counts. Today only Nawy
writes to it, and only when units are collected.

The change: **every source writes a snapshot for every project on every run**,
filling what it knows and leaving the rest NULL. Property Finder and Aqarmap
have no unit rows, so they contribute `min_price` and `delivery_range` with
`total_units` NULL — enough for price movement and new-entrant detection. Nawy
keeps contributing the full unit rollup, which absorption velocity needs.

- **Volume:** ~2,135 projects × 4 runs/day ≈ 8.5k rows/day, ~3M/year. Comfortable
  for Postgres. If it becomes noise, throttle snapshots to daily while still
  collecting every 6h.
- **Retry safety:** one timestamp per run for all its snapshots, inserted with
  `ON CONFLICT DO NOTHING` on `(project_id, source_id, snapshot_at)`, so a retry
  after a partial crash repairs itself instead of double-counting.

History is not backfillable. The series starts the day this ships.

## Failure modes

**Per-source isolation.** Each run records a `stop_reason`
(`complete | no_records | below_floor | fetch_error`), so a silent no-op is
distinguishable from a genuine empty result.

**Sanity floor.** Each source declares a minimum expected record count. A run
landing below it **aborts without writing**:

| Source | Floor | Observed |
|---|---|---|
| nawy | 1,500 | 1,835 |
| property_finder | 1,000 | 1,348 |
| aqarmap | 1,500 | ~1,988 advertised |

This is the `fetch_launch_compound_ids` lesson generalised: an empty fetch that
writes is worse than a fetch that raises. There, an empty launch set would have
silently cleared `is_launch` on every project.

**Field-coverage baseline.** A collector can return the right number of records
with every field NULL — HTML parsers fail exactly that way. Each run asserts
coverage per column against the source's baseline (e.g. ≥80% of Aqarmap projects
carry a price) and drops to `below_floor` if it collapses. This is what would
have caught `delivery_date` being 100% NULL for Nawy.

**The repair rule.** Fixing a mapper does not fix stored rows: the upsert
COALESCEs and never blanks an existing value. Every mapping correction therefore
ships with a data migration that recomputes affected rows from the stored `raw`
payload. Observed the hard way — 101 projects kept a resale price after the
mapper stopped producing one.

**Politeness** is unchanged: per-host rate limiting and an identifying
User-Agent. Aqarmap needs one fetch per listing page, so it gets the slowest
cadence.

## Testing

**No collector ships without a saved payload fixture.** Property Finder had
none, which is why its feed of completed developments was flagged 100% as
launches. Each collector gets a trimmed real payload in `tests/fixtures/live/`
and tests that need no network and no database.

**Dry-run mode** — the live checkpoint before anything is trusted:

```
python scripts/collect.py --source aqarmap --dry-run
```

Fetches and maps for real, then prints what it *would* write and exits: record
counts against the floor, field coverage per column, and a sample of mapped
records beside their raw payload. This is where to confirm that an Aqarmap
"compound" really is our `Project` before 1,988 rows land. It works for existing
sources too, so a mapping change can be inspected before it is trusted.

**Cross-source consistency check** after dedup, since coverage is the goal:
projects contributed per source, shared, and unique to one. If Aqarmap adds
1,988 projects and shares only 20 with Nawy, either the dedup thresholds are
wrong or the two are not describing the same things. `metrics/quality.py`
already computes source coverage; this extends it.

**Existing regression tests** for resale exclusion, primary-only pricing,
canonical vocabularies and area dedup keep running against every source, so a
new collector cannot quietly reintroduce a fixed bug.

## Out of scope

- Bayut collection (registered, disabled, no adapter).
- Social media trend collection. It shares the scheduling and storage ideas but
  needs its own contract models — it is not projects and units — and belongs in
  its own spec.
- Replacing ScrapeGraphAI for the launch-extraction path. That path is blocked
  on a separate Python 3.12 dependency issue, tracked in the handoff.

## Open questions

- Aqarmap's compounds guide lazy-loads: the first page exposed only 6 compound
  links of ~1,988. Pagination has to be confirmed during implementation; if it
  requires JS, Aqarmap moves to the Playwright fetch path and its cadence drops.
- Whether Aqarmap exposes developer identity per compound. If not, its projects
  cannot resolve a `developer_id`, and dedup blocks by developer — which would
  reduce its usefulness for cross-source confirmation.
