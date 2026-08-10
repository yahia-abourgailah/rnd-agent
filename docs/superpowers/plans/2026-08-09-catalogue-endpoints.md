# Launches and Projects Endpoints Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A change feed answering "did a competitor just move?", the project drill-down it points at, and search.

**Architecture:** Materiality logic is a pure function over snapshot rows, testable with no database. Scoping shared by every catalogue endpoint moves into one module, which also fixes zone filtering to resolve through `areas.canonical_id`.

**Tech Stack:** FastAPI, SQLAlchemy 2.x, Pydantic v2, pytest.

## Global Constraints

- Import root is `src/` as a **path root, not a package**: `from api.queries import scoped`, never `from src.api...`.
- No explanatory comments in code. Docstrings stating contract are allowed; so are functional pragmas.
- Type hints on every function. Pydantic models for responses, never raw dicts.
- Tests pass with no network and no database.
- Every data route sits behind the existing `require_api_key` dependency.
- Every query is dedup-scoped by default (`canonical_id IS NULL`).
- `make lint` must pass before every commit.
- Tests run with `ENV_FILE=/dev/null .venv/bin/python -m pytest`.

---

### Task 1: Pure change detection

**Files:**
- Create: `src/api/changes.py`
- Test: `tests/test_api/test_changes.py`

**Interfaces:**
- Produces: `PriceChange` dataclass (`from_price: float`, `to_price: float`, `change_pct: float`, `observed_at: datetime`); `detect_price_change(snapshots: list[tuple[datetime, float]], min_change_pct: float) -> PriceChange | None` where snapshots are `(snapshot_at, min_price)` oldest first.

- [ ] **Step 1: Write the failing test** — see `tests/test_api/test_changes.py` below.
- [ ] **Step 2:** Run `ENV_FILE=/dev/null .venv/bin/python -m pytest tests/test_api/test_changes.py -v`. Expected: FAIL, no module named `api.changes`.
- [ ] **Step 3:** Implement `src/api/changes.py`.
- [ ] **Step 4:** Run the same command. Expected: PASS.
- [ ] **Step 5:** Commit `git commit -m "Add pure price-change detection"`.

---

### Task 2: Shared scoping, with canonical zones

**Files:**
- Create: `src/api/queries.py`
- Modify: `src/api/routes/insights.py` (replace `_scoped` with an import)
- Test: `tests/test_api/test_queries.py`

**Interfaces:**
- Produces: `scoped(stmt, source, zone, dedup=True)`; `canonical_area_name()` returning a SQLAlchemy expression resolving an area to its canonical name; `CANONICAL_AREA` (aliased `Area` for the canonical side).

- [ ] **Step 1:** Write the failing test asserting the compiled SQL joins `areas` to itself and filters on the canonical name.
- [ ] **Step 2:** Run it. Expected: FAIL, no module named `api.queries`.
- [ ] **Step 3:** Implement, then point `insights.py` at it.
- [ ] **Step 4:** Run the full suite. Expected: existing insight tests still pass.
- [ ] **Step 5:** Commit.

---

### Task 3: GET /launches

**Files:**
- Modify: `src/api/routes/launches.py`, `src/api/schemas.py`, `src/api/main.py`
- Test: `tests/test_api/test_launches_route.py`

**Interfaces:**
- Consumes: `detect_price_change` (Task 1), `scoped` (Task 2).
- Produces: `LaunchEvent`, `LaunchesResponse` schemas; `GET /launches`.

- [ ] **Step 1:** Write route tests with a stubbed session.
- [ ] **Step 2:** Run. Expected: FAIL, 404.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit.

---

### Task 4: GET /projects and GET /projects/{id}

**Files:**
- Create: `src/api/routes/projects.py`
- Modify: `src/api/schemas.py`, `src/api/main.py`
- Test: `tests/test_api/test_projects_route.py`

**Interfaces:**
- Consumes: `scoped` (Task 2).
- Produces: `ProjectRow`, `ProjectsResponse`, `ProjectDetail` schemas; both routes.

- [ ] **Step 1:** Write route tests.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit.

---

### Task 5: Live verification and the documented zone correction

**Files:**
- Modify: `docs/DASHBOARD_API.md`

- [ ] **Step 1:** Bring the stack up, hit each new endpoint, record real output.
- [ ] **Step 2:** Confirm `/insights/zones` now reports the canonical figure.
- [ ] **Step 3:** Document the new endpoints and the zone correction.
- [ ] **Step 4:** Commit.

---

## Self-review notes

Spec coverage: change feed → Task 3; detail → Task 4; search → Task 4;
materiality rule → Task 1; canonical zone fix → Task 2; documented correction →
Task 5; error handling → Tasks 3 and 4; testing → every task.

Task 1 carries the correctness risk and has the most tests, because it is the
part that decides whether the feed is trustworthy.
