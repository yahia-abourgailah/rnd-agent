# Competitive Launch Intelligence — Project Status & Handoff

**Repo:** https://github.com/yahia-abourgailah/rnd-agent (branch `main`)
**Purpose:** Automated pipeline for The Address Investments that (a) monitors
competitor real-estate launches across Egyptian sources and (b) maintains a
**connected catalogue** of the whole market — developers, projects, units,
areas, availability — for the R&D team's CRM. Later: dedup across sources,
alerts, and a chatbot over the data.

> This file is the single source of truth for "where are we." Read it top to
> bottom to continue the project in a fresh session.

---

## 1. The pipeline (mental model)

```
Watch → Extract → Dedup → Store → Notify
  ✅       ✅        ✅       ✅       🚧
```

> **Dedup is now built for the relational catalogue** (cross-source, see §5a).
> The flat-`launches` launch-detection path still has no dedup (teammate's).
> An **insights API** (§6) and **API-key auth** now sit on top of the catalogue.

Each stage is a self-contained module under `src/`. Stages
communicate only through the shared Pydantic models in `models/`. Two design
rules hold throughout:

- **Detection before extraction:** fetch cheaply, hash the content, and only
  pay for the LLM on pages that actually changed.
- **Thin flows, fat stages:** `pipeline/flows.py` only wires stages in order;
  all real logic lives in the stage modules, so everything is testable without
  Prefect running.

**Two data models now coexist:**
1. The original flat `launches` table — produced by the Watch→Extract pipeline
   above (new-launch detection).
2. A **relational model** — `sources`, `developers`, `areas`, `projects`,
   `units`, `availability` — populated by a **backfill** from Nawy's structured
   API. This is the mentor's "past + connected" ask (§5), now **BUILT and
   loaded**. The flat `launches` table links into it via a nullable `project_id`.

---

## 2. What is DONE and verified working

| Area | Status | Notes |
|---|---|---|
| Shared contract (`models/`) | ✅ | `Launch`, `SourceConfig`, `SourceEvidence`, `RawPage`, `Candidate` |
| **Watch** — fetcher | ✅ | Playwright (JS) + httpx (JSON), retries w/ exponential backoff, per-source rate limits, neutral User-Agent |
| **Watch** — change detector | ✅ | sha256 hash; still uses a local JSON file (see Known Issue #4) |
| **Watch** — Nawy adapter | ✅ | reads Nawy's embedded `__NEXT_DATA__` JSON + enriches via its listing API |
| **Extract** | ✅ | ScrapeGraphAI + company `gemma-4`; Arabic/English; many launches per page |
| **Store** | ✅ | Postgres: `launches`, `raw_content`, `fetch_log` (Alembic-managed) |
| **Relational model** | ✅ | `sources`, `developers`, `areas`, `projects`, `units`, `availability` — connected by FKs (Alembic-managed). See §5. |
| **Backfill (Nawy)** | ✅ | `scripts/collect.py --source nawy` — full catalogue into the relational tables. |
| **Backfill (Property Finder)** | ✅ | `scripts/collect.py --source property_finder` — 2nd live source (1,341 projects). See §5a. |
| **Cross-source dedup** | ✅ | `scripts/dedup.py` — matches the same developer/project across sources, links via `canonical_id`. See §5b. |
| **Insights API** | ✅ | 8 read endpoints (FastAPI) over the catalogue + CORS + API-key auth. See §6. |
| Infra | ✅ | Docker (Postgres+pgvector, Redis), 3 environments (dev/staging/prod), GitHub |
| Tests | ✅ | 53 passing, fully offline (saved fixtures + mocked LLM) |

**End-to-end proof (launch detection):** `python scripts/run_source.py --source
nawy` fetches Nawy's new-launches page, extracts ~24 launches with `gemma-4`, and
writes them to the flat `launches` table — queryable by price/zone/developer.

**End-to-end proof (relational backfill, 2 sources):** the backfill loaded Nawy
(1,830 projects) + Property Finder (1,341 projects) = **3,171 project rows, 874
developers, 100 areas, 299 units**. All linked (0 orphaned FKs).

**End-to-end proof (dedup):** `python scripts/dedup.py` linked cross-source
duplicates → **642 unique developers (was 874)** and **2,520 unique projects
(was 3,171)**. Property Finder adds **708 projects Nawy doesn't have**; the rest
overlap. Verified: `SODIC`(Nawy) is canonical, `Sodic`(PF) → canonical; numbered
phases ("La Vista 1..7") stay distinct.

### Identity design (settled with mentor)
- Every relational row's **primary key `id` is a UUID we generate** — our own,
  independent of any source. Foreign keys reference these UUIDs.
- The origin's own id is kept only as **`external_ref`** (`"nawy:1198"`), the key
  a re-sync matches on to UPDATE-not-duplicate. Uniqueness is on `external_ref`.
- **Provenance is normalised** into the `sources` registry (`nawy`=1,
  `property_finder`=2, `sodic`=3, `palm_hills`=4); every entity carries a
  `source_id` FK. `is_active` marks which sources are live — **Nawy and Property
  Finder are both active**; SODIC/Palm Hills are registered but not built.

### The two live sources
Both are Next.js apps that server-render their data into a `__NEXT_DATA__`
`<script>` tag, so we read structured JSON directly (no LLM):
- **Nawy** — `listing-api.nawy.com` JSON API. Fixed zone-misattribution and gives
  unit-level facts.
- **Property Finder** — `propertyfinder.eg/en/new-projects`, paginated; each
  project carries its developer + location inline (no per-unit data on the
  listing, so PF contributes projects/developers/areas, not `units`).

**Both APIs are undocumented and could change** — the adapters fail safe (return
nothing) if the shape changes. Shapes are captured as offline fixtures in
`tests/fixtures/live/`.

---

## 3. What is NOT built yet

| Stage / piece | Owner | What it is |
|---|---|---|
| **Notify** | teammate | Slack alerts (Block Kit) to R&D. Router/digest logic buildable; *delivery* blocked until a `SLACK_BOT_TOKEN` exists. |
| **Feedback loop** | either | FastAPI Confirm/Reject endpoint + feedback handler (stubs). Coupled to the Slack alerts. |
| **Dashboard UI** | full-stack interns | Mentor's call: the **full-stack interns build the React/Next.js charts** against our insights API (§6). We provide endpoints, not screens. (Metabase is NOT being used.) |
| **Confidence scoring** | teammate | Define inputs/thresholds + score. Currently `confidence`=1.0 everywhere (Known Issue #2). |
| **More adapters** | you | Nawy + Property Finder are live. `sodic.py`/`palm_hills.py` are stubs — but they're single developers Nawy already covers, so **low value** (mostly duplicate data). |
| **Orchestration / monitoring / prod** | either | Move to Prefect flows, adapter-failure alerting, lead-time/ROI reporting, deploy + runbooks — all not started. |

---

## 4. Known issues (found by running against live data)

1. **Duplicates — solved for the relational catalogue, still open for flat
   `launches`.** Relational tables upsert on `UNIQUE(external_ref)` (no same-source
   dupes) and **cross-source dupes are now linked by `canonical_id`** via
   `scripts/dedup.py` (§5b). The flat `launches` table still re-inserts on every
   run — that's the teammate's launch-detection dedup, not built.
2. **`confidence` is 1.0 on almost everything.** The model doesn't discriminate,
   so it isn't yet a usable filter signal. Revisit with messier sources, or
   redefine it to measure completeness (contract change).
3. **Nawy's prices flicker.** A project's `minPrice` depends on live inventory,
   so it changes between crawls even when nothing meaningful launched. Effect:
   change detection fires every crawl → you'd pay for an LLM call hourly.
   Fix: hash only the stable fields, not the whole payload.
4. **Change detector still uses a local JSON file** (`.crawl_state.json`).
   `db/repository.latest_hash_for()` exists to replace it with a DB lookup, but
   isn't wired in yet. The file dies with the container and doesn't work across
   multiple workers.
5. **`PropertyType` enum vs reality.** Nawy uses 12 types; we now cover 11
   (added studio/loft/cabin). "Administrative"/"Medical" map to `commercial`.
   Any new source vocabulary needs an enum decision.

---

## 5. THE MENTOR'S ASK: all past data + "connected" — ✅ BUILT

Mentor's request: store **all** the developers' projects (not just new
launches), and make the records **connected** (relational). Done — the whole
Nawy catalogue is loaded into linked tables.

**Nawy endpoints used** (undocumented, public — shapes captured as offline
fixtures in `tests/fixtures/live/nawy_*.json`):

| Endpoint | Count | Loads into |
|---|---|---|
| `/v1/developers` | 394 | `developers` (no `total` field — paginate to empty) |
| `/v1/areas` | 47 | `areas` |
| `/v1/search/compounds` | 1,830 | `projects` (carries `developerId`, `areaId`) |
| `/v1/search/properties` | per-compound | `units` |

### The relational model as built
```
sources ──┐  (every entity carries source_id → sources)
          ├──< developers ──┐
          ├──< areas ───────┤
          └──< projects ────┴──(FKs)   projects is the hub
                  │
                  ├──< units          (price, beds, area, delivery, per unit)
                  ├──< availability   (computed rollup per project, time-stamped)
                  └──  is_launch flag + flat launches.project_id → projects.id
```
- **Identity:** `id` is a UUID we generate; the origin id lives only in
  `external_ref` ("nawy:1198"); provenance is the `source_id` FK. (See §2.)
- **Launches:** a project is flagged `is_launch=true` by cross-referencing
  Nawy's new-launches feed (the proven `NawyAdapter` parser). 24 current.
- **Availability is computed, not fetched:** Nawy has no availability endpoint,
  so each snapshot is rolled up from a project's `units` (totals, price range,
  price/m², delivery range) and stamped with `snapshot_at`.

### Load order (so FKs resolve)
`developers → areas → projects → units → availability`. A **gap-fill** step
creates minimal `developers`/`areas` rows for any id a compound references but
the entity endpoints miss (e.g. leaf areas) — which is why all 1,830 projects
linked cleanly.

### Decisions (settled)
- **Scope of "past":** load **everything** — all 1,830 compounds (the whole
  market). ✅
- **Enrich units:** **launches deep, market wide** — per-unit rows for the 24
  live launches; headline facts (developer, area, price, types) for all 1,830.
  Run `scripts/collect.py --source nawy` to load every project and its units (~1,800 API
  calls, slow) when needed.
- **Shared-contract change:** the flat `launches` model was kept intact
  (additive `project_id` link), so the teammate's dedup work isn't broken — all
  53 tests still pass.

### Run it
```bash
python scripts/collect.py --source nawy --dry-run   # fetch, map, report; write nothing
python scripts/collect.py --source nawy         # full catalogue incl. per-unit rows
python scripts/collect.py --source property_finder   # Property Finder (2nd source)
python scripts/dedup.py                         # link cross-source duplicates (run AFTER backfills)
```

---

## 5a. Second source: Property Finder — ✅ BUILT

`src/collect/property_finder.py`. Same pattern as Nawy:
reads `__NEXT_DATA__` from `propertyfinder.eg/en/new-projects` (paginated, ~56
pages, 1,341 projects), maps to our models, no LLM. Developers and areas are
**derived from the projects** (PF has no standalone feeds); areas are grouped at
district level. **No per-unit data** on the listing, so PF fills
projects/developers/areas only. Rows land in the same tables with `source_id=2`.

## 5b. Cross-source dedup — ✅ BUILT

`src/dedup/` (`normalize.py`, `matcher.py`, `resolver.py`) +
`scripts/dedup.py`. Links the same real entity seen by both sources:
- **Normalize** names to a match key (strip case, punctuation, noise words like
  "Developments"/"Group") — `"SODIC Developments"` and `"Sodic"` → `"sodic"`.
- **Match** with exact key + **RapidFuzz** fuzzy similarity (≥90), clustered by
  union-find. Projects are **blocked by developer** (only compare same-company
  projects) and matching is **number-aware** (`"La Vista 1"` ≠ `"La Vista 2"`).
- **Resolve**: pick the canonical row (lowest `source_id` → Nawy wins); duplicates
  get `canonical_id` → canonical. Projects are repointed to the canonical developer.
- Result: 874→642 developers, 3,171→2,520 projects. Re-runnable (resets each run).
- **Not semantic embeddings** — RapidFuzz is the right offline tool for short
  names. `dedup/embeddings.py` stays a stub (would need an embedding model).

---

## 6. Displaying on the CRM — insights API ✅ BUILT

**We own the data + API; the full-stack interns build the React/Next.js charts.**
Full reference for them: `docs/DASHBOARD_API.md`.

Run the API: `python -m uvicorn api.main:app --port 8000`
(Swagger at `/docs`, spec at `/openapi.json`.)

**8 live insight endpoints** (`src/api/routes/insights.py` &
`monitoring.py`), all over the deduped catalogue:

| Endpoint | Answers |
|---|---|
| `/insights/market-share` | developer share by project count |
| `/insights/zones` | per-zone activity, competition, price range |
| `/insights/price-distribution` | projects by price bracket |
| `/insights/property-mix` | projects by property type |
| `/insights/delivery-pipeline` | projects by delivery year (supply) |
| `/insights/whitespace` | zones ranked by opportunity (low competition + value) |
| `/insights/payment-terms` | financing benchmark per developer |
| `/monitoring/quality` | duplicate rate, source coverage, completeness |

- **Common params:** `source` (nawy/property_finder), `dedup` (default true =
  count unique deduped projects), `limit`, some take `zone`.
- **CORS** enabled (browser apps can call it).
- **Auth:** every data endpoint requires an `X-API-Key` header
  (`src/api/security.py`); key set via `API_KEY` env
  (`config/settings.py`). `/health` is open. Empty `API_KEY` disables auth
  (local dev only). The key lives in the CRM **backend**, never in browser code.

---

## 7. How to run it (fresh machine / new session)

```bash
# 1. Start infra (Docker Desktop must be running first)
docker compose up -d

# 2. Python env
python -m venv .venv
.venv\Scripts\Activate.ps1              # Windows PowerShell
pip install -e ".[dev]"
playwright install chromium

# 3. Config — .env must exist (gitignored). Needs at least:
#    OPENAI_API_KEY=<company key>
#    EXTRACTION_MODEL=openai/gemma-4
#    LLM_BASE_URL=https://vllm.addressinv.com/v1   (company gemma-4 endpoint)
#    API_KEY=<strong random>   (auth for the insights API; empty = auth off, dev only)

# 4. Sanity check (offline, no API/network)
pytest -q                                # expect 53 passed

# 5a. Launch-detection pipeline → flat launches table
del .crawl_state.json                    # force re-run (change detection is per-URL)
python scripts\run_source.py --source nawy

# 5b. Relational backfill → developers/areas/projects/units/availability
python scripts\collect.py --source nawy           # Nawy; ~4 min; re-runnable
python scripts\collect.py --source property_finder   # Property Finder (2nd source)

# 5c. Cross-source dedup (run AFTER both backfills)
python scripts\dedup.py

# 5d. Serve the insights API (needs API_KEY in .env for auth)
python -m uvicorn api.main:app --port 8000   # docs at /docs

# 6. Inspect the data
docker compose exec postgres psql -U launch_intel -d launch_intel
#   \dt                     list tables
#   -- connected view through the relational model:
#   SELECT p.name, d.name AS developer, a.name AS area, p.min_price
#     FROM projects p
#     JOIN developers d ON d.id = p.developer_id
#     JOIN areas a      ON a.id = p.area_id
#     ORDER BY p.min_price DESC NULLS LAST LIMIT 10;
#   \q                      quit
```

### Gotchas
- **Docker Desktop stops on reboot** — restart it, then `docker compose up -d`.
- **Change detection** skips unchanged pages; delete `.crawl_state.json` to force.
- **`LLM_BASE_URL` must point at the company gemma-4 endpoint** and
  `EXTRACTION_MODEL` must keep the `openai/` prefix (it selects the API dialect,
  not the vendor). Without the base URL, requests go to OpenAI and fail.
- **Never put the real API key in `*.example` files** — those are committed.
  It goes only in `.env` (gitignored).

---

## 8. Repo map

```
src/                import root (on PYTHONPATH; packages below are top-level: `from watch.fetcher import Fetcher`)
  config/          settings.py (env-layered), sources.<env>.yaml (crawl registry — separate from the DB sources table)
  chatbot_agent/   LangGraph SQL chatbot over the warehouse (graph, nodes/, tools/)
  models/          shared contract: Launch, SourceConfig, RawPage, Candidate + relational: Developer, Area, Project, Unit, Availability
  watch/           fetcher, change_detector, base adapter, adapters/ (nawy real; others stubs)
  extract/         extractor (ScrapeGraphAI), prompts, normalize
  collect/         nawy.py, property_finder.py — fetch + map source endpoints → models (no LLM), behind one SourceCollector protocol
  dedup/           normalize.py, matcher.py (RapidFuzz), resolver.py — cross-source dedup (WORKS)
  db/              engine, tables (flat + relational), repository (upserts + dedup writes), migrations/ (Alembic)
  metrics/         quality.py — duplicate rate / coverage / completeness (lead_time.py still stub)
  api/             main.py, security.py (API key), dependencies.py, schemas.py, routes/ (insights, monitoring, health; launches/feedback stubs)
  pipeline/        flows.py (thin), tasks.py (the steps)
  notify/ feedback/   ← stubs, TODO markers
scripts/           run_source.py, collect.py (--source nawy|property_finder, --dry-run), dedup.py — all WORK; seed_sources.py stub
tests/             mirrors src/; 53 tests; fixtures/live/ has real saved HTML + nawy_*.json + property finder samples
docs/              this file + DASHBOARD_API.md (frontend handoff reference)
```

Migrations (Alembic, in order): `e2cf8c9`-era flat tables → `b7f1a2c3d4e5`
(relational tables) → `c9d2e3f4a5b6` (UUID identity + external_ref) →
`d0e1f2a3b4c5` (sources registry + source_id FKs) → `e1f2a3b4c5d6`
(dedup `canonical_id`). **Head: `e1f2a3b4c5d6`.**

---

## 9. Suggested next actions (pick by goal)

- **Trends over time (biggest unlock):** set up a **weekly re-sync** (Windows Task
  Scheduler or Prefect) so `availability` snapshots + `first_seen_at` accumulate
  history → price movement, absorption velocity, new-entrant detection. History
  only builds going forward, so start it early. (May want a project-price snapshot
  table so price-movement covers all projects, not just the 24 with units.)
- **Chatbot (`src/chatbot_agent/`):** text-to-SQL over the relational schema; the
  FKs make the joins possible. LangGraph loop (`chatbot` ↔ `tools`) against the
  self-hosted `gemma-4` endpoint (`LLM_BASE_URL`). Run it with
  `python -m chatbot_agent.app`. **Before any shared environment: set
  `DATABASE_READONLY_URL` to a `GRANT SELECT`-only role.** The SQL it runs is
  LLM-authored; `tools/postgres.py` refuses anything but a single SELECT/WITH
  and runs it in a READ ONLY transaction with a statement timeout, but the
  least-privilege role is the defence that shouldn't be skipped.
  Still open: no eval set for SQL accuracy, and no UI beyond the CLI.
- **Lead-time tracking (#21) + confidence scoring** — self-contained code tasks.
- **Notifications:** router/digest logic is buildable; Slack *delivery* needs a
  `SLACK_BOT_TOKEN`.
- **Handed off:** the React dashboard (full-stack interns, against §6 API).
- **Correctness:** price-flicker (Issue #3), change detection to DB (Issue #4).

### Blocked on external input (not code)
Eval-set labelling, the 3 Validation Gates (need R&D humans), Slack token,
production deploy, ROI baseline.

---

_Last updated: 2026-07-28. Done: relational catalogue (UUID identity, `sources`
registry), **2 live sources** (Nawy + Property Finder, 3,171 projects →
**2,520 deduped**), **cross-source dedup**, **8-endpoint insights API** with CORS
+ **API-key auth**, frontend handoff doc. 53 tests passing. Migration head:
`e1f2a3b4c5d6`. Uncommitted work from this session — commit before continuing._
