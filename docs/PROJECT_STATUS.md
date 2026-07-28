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
  ✅       ✅        🚧       ✅       🚧
```

Each stage is a self-contained module under `src/launch_intel/`. Stages
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
| **Backfill** | ✅ | `scripts/backfill.py` loads Nawy's full catalogue into the relational tables. `src/launch_intel/backfill/` |
| Infra | ✅ | Docker (Postgres+pgvector, Redis), 3 environments (dev/staging/prod), GitHub |
| Tests | ✅ | 53 passing, fully offline (saved fixtures + mocked LLM) |

**End-to-end proof (launch detection):** `python scripts/run_source.py --source
nawy` fetches Nawy's new-launches page, extracts ~24 launches with `gemma-4`, and
writes them to the flat `launches` table — queryable by price/zone/developer.

**End-to-end proof (relational backfill):** `python scripts/backfill.py` loaded
**394 developers, 47 areas, 1,830 projects, 299 launch units** and their
availability snapshots into the connected tables. Verified live: **1,830/1,830
projects link to a developer AND an area**, zero orphaned FKs, re-running syncs
in place (no duplicates).

### Identity design (settled with mentor)
- Every relational row's **primary key `id` is a UUID we generate** — our own,
  independent of any source. Foreign keys reference these UUIDs.
- The origin's own id is kept only as **`external_ref`** (`"nawy:1198"`), the key
  a re-sync matches on to UPDATE-not-duplicate. Uniqueness is on `external_ref`.
- **Provenance is normalised** into the `sources` registry (`nawy`=1,
  `property_finder`=2, `sodic`=3, `palm_hills`=4); every entity carries a
  `source_id` FK. `is_active` marks which sources are live (only Nawy today).

### The one real source: Nawy
Nawy is a Next.js app. Its data lives in a `__NEXT_DATA__` `<script>` tag and a
public JSON API (`listing-api.nawy.com`). The adapter reads those directly
instead of scraping rendered text — that fixed zone-misattribution (1/4 → 6/6
correct) and let us pull unit sizes, property types and delivery dates that the
listing page doesn't show. **This API is undocumented and could change without
notice** — the adapter fails safe (returns nothing) if the shape changes.

---

## 3. What is NOT built yet

| Stage / piece | Owner | What it is |
|---|---|---|
| **Dedup** | teammate | Recognise the same project reported by *multiple sources* as one entity. Not needed yet (only Nawy is live); the relational tables already prevent same-source duplicates via upsert on `external_ref`. Cross-source dedup will match on `developer_id`/`external_ref`, not fuzzy text. |
| **Notify** | teammate | Slack alerts (Block Kit) to the R&D team with source links. |
| **API** (`api/`) | either | FastAPI read endpoints. Stubbed, empty. Needed for the CRM (see §6). Next up (Phase 3). |
| **Dashboard** | either | Metabase — sketched (commented) in `docker-compose.yml`, not wired. |
| More adapters | you | Only Nawy is real & active. `property_finder.py`, `sodic.py`, `palm_hills.py` raise `NotImplementedError` (but are registered in the `sources` table, ready to activate). |

---

## 4. Known issues (found by running against live data)

1. **Duplicates on every run — only in the flat `launches` table.** That table
   has no uniqueness constraint, so the launch-detection pipeline re-inserts
   rows; dedup (teammate's stage) solves it. The **relational tables do NOT have
   this problem** — they upsert on `UNIQUE(external_ref)`, so re-running the
   backfill syncs in place (verified: projects stayed 1,830, not doubled).
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
  Run `scripts/backfill.py --units all` to deep-enrich every project (~1,800 API
  calls, slow) when needed.
- **Shared-contract change:** the flat `launches` model was kept intact
  (additive `project_id` link), so the teammate's dedup work isn't broken — all
  53 tests still pass.

### Run it
```bash
python scripts/backfill.py                 # all developers/areas/projects, units for launches
python scripts/backfill.py --units all     # + per-unit rows for every project (slow)
python scripts/backfill.py --limit 50      # smoke test (first 50 compounds)
```

---

## 6. Displaying on the CRM (custom / in-house)

The company CRM is custom-built. Recommended pattern: **the CRM calls our
FastAPI** (`api/`, already stubbed in the stack).

```
Nawy → pipeline → Postgres → our FastAPI → CRM backend → CRM screen
                              (we build)    (their team)  (their UI)
```

- We build read endpoints; the CRM's developers call them and render the data
  in their own UI. **We own the data source, not the screens.**
- Endpoints to build:
  - `GET /developers`, `GET /developers/{id}/compounds`
  - `GET /compounds/{id}` (fully linked)
  - `GET /launches?zone=&developer=&since=` (filtered)
- Alternative (quicker, more fragile): give the CRM read-only Postgres access +
  a joined SQL `VIEW`. Couples them to our schema — prefer the API.

The "connected" model is what makes a CRM project-card rich: click a developer →
all their projects; click an area → everything there.

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

# 4. Sanity check (offline, no API/network)
pytest -q                                # expect 53 passed

# 5a. Launch-detection pipeline → flat launches table
del .crawl_state.json                    # force re-run (change detection is per-URL)
python scripts\run_source.py --source nawy

# 5b. Relational backfill → developers/areas/projects/units/availability
python scripts\backfill.py               # ~2 min; re-runnable (upserts, no dupes)

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
config/            settings.py (env-layered), sources.<env>.yaml (crawl registry — separate from the DB sources table)
src/launch_intel/
  models/          shared contract: Launch, SourceConfig, RawPage, Candidate + relational: Developer, Area, Project, Unit, Availability
  watch/           fetcher, change_detector, base adapter, adapters/ (nawy real; others stubs)
  extract/         extractor (ScrapeGraphAI), prompts, normalize
  backfill/        nawy_client.py — fetch + map Nawy's entity endpoints → relational models (no LLM)
  db/              engine, tables (flat + relational), repository (upserts), migrations/ (Alembic)
  pipeline/        flows.py (thin), tasks.py (the steps)
  dedup/ notify/ feedback/ metrics/ api/   ← stubs, TODO markers
scripts/           run_source.py (works), backfill.py (WORKS), seed_sources.py (stub)
tests/             mirrors src/; 53 tests; fixtures/live/ has real saved HTML + nawy_*.json entity samples
docs/              this file
```

Migrations (Alembic, in order): `e2cf8c9`-era flat tables → `b7f1a2c3d4e5`
(relational tables) → `c9d2e3f4a5b6` (UUID identity + external_ref) →
`d0e1f2a3b4c5` (sources registry + source_id FKs).

---

## 9. Suggested next actions (pick by goal)

- **Phase 3 — CRM API (recommended next):** build the FastAPI read endpoints
  (§6) over the relational tables, hand the CRM/full-stack team the URLs.
- **Ship something visible to R&D now:** wire Metabase onto Postgres — the
  relational tables give instant rich dashboards (projects per developer/area,
  price distributions) with no frontend work.
- **Chatbot (new idea):** point a text-to-SQL bot at the relational schema so
  R&D can ask free-form questions; the FKs make the joins possible.
- **Coverage — a real 2nd source:** build the `property_finder` adapter
  (`source_id=2` is already registered); its rows land in the same tables. This
  is when cross-source **dedup** becomes needed.
- **Correctness:** fix the price-flicker (Known Issue #3) and wire change
  detection to the DB (Known Issue #4).

---

_Last updated: 2026-07-27. Phases 1–2 complete: relational model (UUID identity,
`sources` registry) + full Nawy backfill (394 developers, 47 areas, 1,830
projects). 53 tests passing. Migration head: `d0e1f2a3b4c5`._
