# Competitive Launch Intelligence — Project Status & Handoff

**Repo:** https://github.com/yahia-abourgailah/rnd-agent (branch `main`)
**Purpose:** Automated pipeline for The Address Investments that monitors
competitor real-estate launches across Egyptian sources, extracts structured
data with an LLM, stores it, and (later) deduplicates and alerts the R&D team.

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
| Infra | ✅ | Docker (Postgres+pgvector, Redis), 3 environments (dev/staging/prod), GitHub |
| Tests | ✅ | 53 passing, fully offline (saved fixtures + mocked LLM) |

**End-to-end proof:** `python scripts/run_source.py --source nawy` fetches
Nawy's new-launches page, extracts ~24 launches with `gemma-4`, and writes them
to Postgres — queryable by price/zone/developer. Verified live.

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
| **Dedup** | teammate | Recognise the same launch reported by multiple sources as one event. Currently re-running inserts duplicate rows — expected. |
| **Notify** | teammate | Slack alerts (Block Kit) to the R&D team with source links. |
| **API** (`api/`) | either | FastAPI read endpoints. Stubbed, empty. Needed for the CRM (see §6). |
| **Dashboard** | either | Metabase — sketched (commented) in `docker-compose.yml`, not wired. |
| More adapters | you | Only Nawy is real. `sodic.py`, `palm_hills.py`, `property_finder.py` raise `NotImplementedError`. |
| Backfill / past data | you | The big new ask — see §5. |

---

## 4. Known issues (found by running against live data)

1. **Duplicates on every run.** No uniqueness constraint; each run inserts new
   rows. This is *expected* — dedup (teammate's stage) solves it.
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

## 5. THE NEW ASK: all past data + "connected to each other"

Mentor's request: store **all** the developers' projects (not just new
launches), and make the records **connected** (relational).

**The data exists** — Nawy exposes it, with the links already built in:

| Endpoint | Count | What |
|---|---|---|
| `listing-api.nawy.com/v1/search/compounds` | **1,828** | every project, past + present |
| `listing-api.nawy.com/v1/developers` | all | the companies |
| `listing-api.nawy.com/v1/areas` | 47 | the zones |

Every compound record carries `developerId` and `areaId` — those are foreign
keys waiting to be used.

### Proposed relational model
```
developers ──< compounds >── areas
                  │
                  └──< launches   (a launch = a compound newly on market, isLaunch=true)
                         └──< units   (sizes, delivery, per unit)
```
- A **launch is a compound that recently came to market** — so `launches`
  points at `compounds`, which points at `developers` and `areas`.
- This makes dedup *easier* (match on real `developerId`, not fuzzy "SODIC" text).

### Build order for this expansion
1. New tables `developers`, `areas`, `compounds`, `launches` (`db/tables.py` + migration).
2. Backfill adapters for the three endpoints above; reuse the existing `Fetcher`.
3. One-time `scripts/backfill.py`: load developers → areas → compounds (in that
   order, so foreign keys resolve), then flag launches.
4. Ongoing: existing hourly crawl adds new launches; a weekly job re-syncs the
   full compound list for price/status changes.

### Decisions to settle BEFORE building (with mentor + teammate)
- **Scope of "past":** all 1,828 compounds, or only The Address's named
  competitors? (Get the competitor list — crawling 1,828 when you track 30 is
  wasted load.)
- **Enrich everything?** Unit-level enrichment for 1,828 compounds is ~1,828 API
  calls. Maybe only new launches get deep enrichment; old projects store
  compound-level facts only.
- **This is a shared-contract change.** The model shifts from a flat `launches`
  table to linked entities. Teammate builds dedup against the current shape —
  align first.

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

# 5. Run the pipeline end-to-end (writes to Postgres)
del .crawl_state.json                    # force re-run (change detection is per-URL)
python scripts\run_source.py --source nawy

# 6. Inspect the data
docker compose exec postgres psql -U launch_intel -d launch_intel
#   \dt                     list tables
#   SELECT project_name, developer, zone, price_from
#     FROM launches ORDER BY price_from DESC NULLS LAST LIMIT 10;
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
config/            settings.py (env-layered), sources.<env>.yaml (source registry)
src/launch_intel/
  models/          the shared contract (Launch, SourceConfig, SourceEvidence, RawPage, Candidate)
  watch/           fetcher, change_detector, base adapter, adapters/ (nawy real; others stubs)
  extract/         extractor (ScrapeGraphAI), prompts, normalize
  db/              engine, tables, repository, migrations/ (Alembic)
  pipeline/        flows.py (thin), tasks.py (the steps)
  dedup/ notify/ feedback/ metrics/ api/   ← stubs, TODO markers
scripts/           run_source.py (works), backfill.py (stub), seed_sources.py (stub)
tests/             mirrors src/; 53 tests; fixtures/live/ has real saved HTML/JSON
docs/              this file
```

---

## 9. Suggested next actions (pick by goal)

- **Ship something visible to R&D:** wire Metabase onto the existing Postgres.
- **The mentor's ask (past + connected):** do §5 — but write/approve the schema
  with mentor + teammate first (it's a contract change).
- **CRM:** build the FastAPI read endpoints (§6), hand the CRM team the URLs.
- **Correctness:** fix the price-flicker (Known Issue #3) and wire change
  detection to the DB (Known Issue #4).
- **Coverage:** build the SODIC or Palm Hills adapter.

---

_Last updated: 2026-07-26. Latest commit: `e2cf8c9` (Persist launches and raw
payloads to Postgres). 53 tests passing._
