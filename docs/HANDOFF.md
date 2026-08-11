# Intern handoff — rnd-agent

**Branch:** `dev` · **Written:** 2026-07-30

Read this end to end before writing code. Sections 1–3 get you running; section 4
is the work, in priority order. Section 5 is the stuff that will bite you.

Ask questions early. If a task's acceptance criteria are unclear, ask rather than
guess — a wrong assumption here costs more than a message.

---

## 1. What this project is

A competitive launch-intelligence pipeline for Egyptian real estate. It watches
competitor websites, extracts new project launches with an LLM, deduplicates them
across sources, and serves the result to a CRM dashboard over a read-only API.

The flow, and where each stage lives:

```
watch/     fetch pages, detect what changed   (only changed pages go further)
extract/   LLM turns page text -> Launch objects
dedup/     match the same launch across sources
db/        persist; relational catalogue (developers/areas/projects/units)
api/       read-only FastAPI for the dashboard
chatbot_agent/  LangGraph agent answering questions in SQL over that data
pipeline/  Prefect flow that chains watch -> extract -> persist
```

Read `docs/PROJECT_STATUS.md` next — it is the detailed status of every component.
`docs/DASHBOARD_API.md` is the API contract already handed to the frontend team;
**treat its endpoint paths and response shapes as a contract you may not silently
break.**

---

## 2. Getting it running

### Layout rule (read this first)

`src/` is a **path root, not a package**. Its subfolders are top-level packages:

```python
from watch.fetcher import Fetcher      # correct
from config.settings import settings   # correct

from src.watch.fetcher import Fetcher  # WRONG — will not import
import launch_intel                    # WRONG — this package no longer exists
```

There is deliberately **no `src/__init__.py`**. Do not add one; it breaks the
packaging config in `pyproject.toml`.

If you see `launch_intel` anywhere outside a database username, it is a leftover
from an old layout and should be fixed. See section 5.1 for the history.

### Setup

```bash
git checkout dev && git pull

python3.12 -m venv .venv && source .venv/bin/activate   # see task 4.1 re: 3.12
pip install -e ".[dev]"
playwright install chromium

cp .env.example .env                # then fill in the values below
docker compose up -d                # postgres (pgvector) + redis
alembic upgrade head                # migrations; head is e1f2a3b4c5d6
```

Values you must set in `.env`:

| Variable | What it is |
|---|---|
| `DATABASE_URL` | main read/write Postgres URL |
| `DATABASE_READONLY_URL` | SELECT-only role for the chatbot — see task 4.2 |
| `LLM_BASE_URL` | our self-hosted OpenAI-compatible endpoint |
| `OPENAI_API_KEY` | key for that endpoint (may be a placeholder) |
| `API_KEY` | shared secret the dashboard sends as `X-API-Key` |

`ENV_FILE` selects which file host-side runs load; it and Docker Compose both
default to `.env`. Never commit a real `.env` — only `*.example` templates are
tracked, so a new host needs its own copy before anything will start.

### Check it works

```bash
make test                                   # expect 74 passed (see task 4.1)
make lint

PYTHONPATH=src uvicorn api.main:app --reload --port 8000   # http://localhost:8000/docs
python -m chatbot_agent.app                                # CLI chatbot
python scripts/run_source.py --source nawy                 # one crawl end to end
```

---

## 3. Current state — be precise about this

**Working:** the Nawy adapter and backfill, the fetcher (retry + per-host rate
limiting), change detection, the relational catalogue and its migrations, cross-source
dedup, 7 insight endpoints + `/monitoring/quality`, and the chatbot's SQL tooling.

**Not working / not built:**

| Thing | State |
|---|---|
| LLM extraction | **Blocked** — dependency conflict, task 4.1 |
| Chat over HTTP | Does not exist — CLI only, task 4.4 |
| `/launches`, `/feedback` routes | Empty stub routers, zero endpoints |
| `notify/` (Slack) | Stubs; also needs a `SLACK_BOT_TOKEN` |
| `metrics/lead_time.py` | Stub |
| Palm Hills / SODIC / Property Finder adapters | Stubs — only Nawy is real |
| API in Docker | No `app` service runs uvicorn; compose only has postgres + redis |
| Precision/recall metrics | Need a labelled eval set that doesn't exist yet |

Tests: **74 passing, 1 failing.** The failure is `test_extract/test_extractor.py`
and it is task 4.1 — it is *not* something you broke.

---

## 4. Your tasks, in order

Do them in this order; 4.1 and 4.2 block real work and are also the smallest.

Work on a branch off `dev`, one branch per task, and open a PR each time. Every
task below lists **acceptance criteria** — a PR is not done until they all hold
and `make test` and `make lint` pass.

---

### 4.1 Unblock LLM extraction (do this first)

**Problem.** `scrapegraphai` is broken on Python 3.11. The lock resolves
`scrapegraphai==1.76.0` (the last 3.11-compatible release), which imports
`ChatOllama` from `langchain-community`; version `0.4.2` removed it. Pinning
`langchain-community<0.4` just trades this for a `langchain-core` break. This is
why `test_extract` fails and why no extraction can run at all.

**Fix.** `scrapegraphai>=2.x` requires Python ≥3.12, and 2.1.6 resolves cleanly.
Bump the floor:
- `pyproject.toml`: `requires-python = ">=3.12"`, `[tool.ruff] target-version = "py312"`
- `Dockerfile`: `FROM python:3.12-slim`
- regenerate `uv.lock`

Then check the ScrapeGraphAI 2.x API still matches `extract/extractor.py` — the
`SmartScraperGraph(prompt=, source=, config=, schema=)` call and the shape of what
`.run()` returns. If 2.x changed either, adapt `extractor.py`, not the tests.

**Acceptance:** `test_extract/test_extractor.py` passes; `python scripts/run_source.py
--source nawy` produces real `Launch` objects against the live site; Docker image builds.

**If the 2.x API turns out to be a big rewrite, stop and flag it** — pinning the
whole langchain stack to older versions on 3.11 is the fallback, but it is worse
and I'd want to discuss before you spend days on it.

---

### 4.2 Create the read-only database role

**Why.** `chatbot_agent` runs SQL written by an LLM. Three defences exist in code
(see `src/chatbot_agent/tools/postgres.py`), but the one that actually matters is
that the credentials it uses **cannot write**. Right now `DATABASE_READONLY_URL` is
blank, which falls back to the read/write URL.

```sql
CREATE ROLE launch_intel_ro LOGIN PASSWORD '<strong-password>';
GRANT CONNECT ON DATABASE launch_intel TO launch_intel_ro;
GRANT USAGE ON SCHEMA public TO launch_intel_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO launch_intel_ro;
-- so tables added by future migrations are covered automatically:
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO launch_intel_ro;
```

Add it to `docker/postgres-init/` as a second init script so a fresh dev stack gets
it automatically, and set `DATABASE_READONLY_URL` in every environment.

**Acceptance:** connected as `launch_intel_ro`, `SELECT` works and
`DELETE FROM launches` is refused with a *permission* error (not just the read-only
transaction error). Add a test that skips cleanly when no database is available.

---

### 4.3 Verify chatbot answer quality

The chatbot's plumbing is tested, but **nothing tests whether its answers are
right.** That is the actual product risk: a confident wrong number is worse than
an error.

Build a small eval set — 15–20 questions you know the true answer to (`How many
launches in New Cairo?`, `Which developer has the most projects?`, `What's the
average price per sqm in Sheikh Zayed?`) as a YAML or JSON fixture, plus a script
that runs each through the graph and reports pass/fail.

Expect problems and write down what you find: `gemma-4` is a small model, and
small models are unreliable at tool-calling and at joining across the FK graph.
Things to check specifically:
- Does it call `describe_schema` before guessing column names?
- Does it use `canonical_id IS NULL` when counting projects, or does it
  double-count cross-source duplicates? (See `_scoped()` in `api/routes/insights.py`
  for how the insight endpoints handle this — the chatbot currently has no such
  guidance, and probably needs it in the system prompt.)
- Does it loop forever on failed queries? If so, add a recursion limit.

**Acceptance:** an eval script in `scripts/`, a fixture of questions with expected
answers, and a short written summary of the pass rate and the failure patterns.

---

### 4.4 Expose the chatbot over HTTP

**Decide the versioning first, and ask before you start.** Our standard is a
`/v1/` prefix, but the existing API is unversioned and `docs/DASHBOARD_API.md` is
already in the frontend team's hands. Either match the existing convention or move
every route to `/v1/` in one change — do not ship a single versioned route next to
eight unversioned ones.

Then add a chat route (`src/api/routes/chat.py`):

- `POST` taking `{message, conversation_id?}`, returning `{reply, conversation_id}`.
- Pydantic request/response models in `api/schemas.py`, consistent with what's
  already there.
- Register it in `api/main.py` **behind `_auth`** like every other data router.
- `main.py` currently sets `allow_methods=["GET"]` — CORS must allow POST.
- The graph is synchronous and the LLM call is slow. Run it in a threadpool
  (a plain `def` endpoint, not `async def`, gets you this for free) so one chat
  request doesn't block the whole event loop.
- Multi-turn conversations need LangGraph checkpointing
  (`MemorySaver` to start, Postgres later) keyed by `conversation_id`. If you skip
  that for v1, say so explicitly and make the endpoint single-turn — do not fake it.

**Acceptance:** you can chat from `/docs` after entering the API key; a test using
FastAPI's `TestClient` with a stubbed model (see `tests/test_chatbot_agent/test_graph.py`
for the pattern) covers both a plain answer and a tool-calling answer;
`docs/DASHBOARD_API.md` documents the new endpoint.

---

### 4.5 Run the API in Docker

`docker-compose.prod.yml` builds an `app` service, but the `Dockerfile` CMD runs
the Prefect flow — nothing serves the API. Add a service that runs
`uvicorn api.main:app --host 0.0.0.0 --port 8000`, with a healthcheck hitting
`/health`, exposed on localhost in `docker-compose.override.yml` only.

**Acceptance:** `docker compose up -d` gives a reachable `/docs`; `make api` (add
the target) runs it locally without Docker.

---

### 4.6 Fill in the stub routers

`api/routes/launches.py` and `api/routes/feedback.py` register routers with zero
endpoints, so they appear in `main.py` but contribute nothing — misleading to
anyone reading the code.

`launches.py` should expose paginated, filterable reads over the `launches` table
via `db/repository.py` (filters: source, zone, developer, date range; always
paginate — never return an unbounded list). `feedback.py` is a Slack webhook and is
blocked on the Slack app existing, so **leave it stubbed and note that in the PR**
rather than half-building it.

**Acceptance:** `/launches` returns paginated results with a documented response
model, tests cover filters and pagination bounds, `docs/DASHBOARD_API.md` updated.

---

### 4.7 Lint and dead-code cleanup (small, do it when blocked)

`ruff check src tests` reports ~75 findings, ~64 auto-fixable — mostly
`UP017` (`timezone.utc` → `datetime.UTC`), `UP007` unions, `I001` import order.

- The 8 `B008` hits are FastAPI's `Depends()` idiom and are **false positives** —
  add `lint.ignore = ["B008"]` under `[tool.ruff]` rather than rewriting them.
- `[tool.ruff]` currently selects no rule set explicitly; pin one so the findings
  don't shift under a ruff upgrade.
- `REPO_ROOT` in `config/settings.py` is dead and, since the layout change, points
  at `src/` rather than the repo root. Delete it before someone uses it.
- Do this as **one commit that changes only formatting** — never mixed with a
  behaviour change, or the diff becomes unreviewable.

---

### 4.8 Then: the real product work

Once the above is done, the highest-value work is in
`docs/PROJECT_STATUS.md` §9. The biggest one:

**Start collecting history.** Schedule a weekly re-sync so `availability` snapshots
and `first_seen_at` accumulate. Price movement, absorption velocity and new-entrant
detection are all impossible until there's a time series, and history only builds
going forward — every week not running is a week of data that can't be recovered.

After that: the Palm Hills / SODIC / Property Finder adapters (copy the Nawy
pattern in `watch/adapters/nawy.py`), and `metrics/lead_time.py`.

---

## 5. Things that will bite you

### 5.1 Never move a package without updating its imports

On 2026-07-30 a commit moved `src/launch_intel/*` to `src/*` — 80 files renamed,
zero imports updated. Every module in the project failed to import, and the repo
sat in that state until it was found. Docs, `Dockerfile` and `alembic.ini` all
still pointed at the old package too.

If you restructure anything: `grep -rn "old_name" .` across **all** file types —
not just `.py`. Config files, Dockerfiles and docs hold import paths too. Then run
this before you commit:

```bash
python -c "
import importlib, pathlib, sys
sys.path.insert(0, 'src')
for p in pathlib.Path('src').rglob('*.py'):
    if 'migrations' in p.parts: continue
    m = '.'.join(p.relative_to('src').with_suffix('').parts).removesuffix('.__init__')
    try: importlib.import_module(m)
    except Exception as e: print('FAIL', m, type(e).__name__, e)
"
```

It must print nothing. `make test` alone does **not** catch this — plenty of
modules have no test that imports them.

### 5.2 Nothing may open a connection at import time

A module that connects to Postgres (or an LLM endpoint) when imported makes the
whole package unimportable without live infrastructure, and untestable in CI. Build
engines and clients lazily — `get_engine()` in `chatbot_agent/tools/postgres.py`
is the pattern to copy. The check in 5.1 catches violations.

### 5.3 The LLM is not trusted input

Anything the model produces — SQL, extracted fields, tool arguments — is untrusted.
It goes through validation before it touches the database or the API response.
Don't add a code path that runs model output directly. If you need a new tool for
the agent, it gets the same allow-list treatment as `query_database`.

### 5.4 Don't let extraction re-fetch

`extract/extractor.py` hands ScrapeGraphAI **already-fetched text**, never a URL.
This is deliberate: `watch/` fetches cheaply and `change_detector` filters out
unchanged pages so the expensive LLM pass only runs on new content. Passing a URL
would silently re-fetch and defeat the whole cost control. There's a test guarding
this (`test_extract_launch_is_fed_local_content_not_a_url`) — if you find yourself
changing it, you're going the wrong way.

### 5.5 Fetch politely

`watch/fetcher.py` rate-limits per host and sends an identifying User-Agent with a
contact address. Don't raise the rate or strip the UA to make a crawl faster. We
are scraping competitors' public sites; getting IP-banned costs us the data source
permanently.

### 5.6 Store the payload before deciding what to do with it

`pipeline/tasks.py` persists every fetched page *before* change detection runs.
Competitor sites overwrite their pages, so a payload we fetched but didn't store
is gone forever — and every stored page is a test case for future prompt changes.
Keep that ordering.

### 5.7 Migrations

Schema changes go through Alembic (`alembic revision --autogenerate -m "..."`),
never a hand-edited table. **Read the generated migration before committing** —
autogenerate gets column drops and type changes wrong often enough to matter.
Current head: `e1f2a3b4c5d6`.

### 5.8 Conventions

- Type hints everywhere; Pydantic models for data crossing a boundary, not raw dicts.
- Config from `config/settings.py` only — no `os.environ` reads scattered in modules,
  no `load_dotenv()`, no hardcoded URLs or secrets.
- Comments explain **why**, not what. The existing codebase does this well; match it.
- Tests mirror `src/` structure. Tests must not need network or a database — stub
  the model (`tests/test_chatbot_agent/test_graph.py`) and use the saved fixtures
  in `tests/fixtures/live/` for adapters.
- Don't change behaviour and reformat in the same commit.

---

## 6. First week

1. Get set up (section 2) and confirm 74 tests pass and `/docs` loads.
2. Read `docs/PROJECT_STATUS.md`, then `watch/fetcher.py` → `pipeline/tasks.py` →
   `extract/extractor.py` in that order. That's the spine of the system.
3. Do task 4.2 (read-only role) — small, self-contained, teaches you the schema.
4. Then task 4.1 (unblock extraction) — the one that matters most.

If you're stuck for more than half a day, ask. Post what you tried and the exact
error, not just "it doesn't work".
