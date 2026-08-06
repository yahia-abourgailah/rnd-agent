# Multi-Source Collection Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collect the same projects from Nawy, Property Finder and Aqarmap on independent schedules, through one shared code path, with price/availability history accumulating from day one.

**Architecture:** Every source implements a `SourceCollector` protocol returning a `CollectionResult` of already-cleaned contract models. A registry maps a source name to its collector, so one Prefect flow runs any source and adding a source is one module plus one registry line. Collectors never touch the database; persistence stays in `db/repository.py`.

**Tech Stack:** Python 3.11, Pydantic v2, SQLAlchemy 2.x, Alembic, Prefect 3, httpx, BeautifulSoup4, pytest.

## Global Constraints

- Import root is `src/` as a **path root, not a package**: `from collect.nawy import ...`, never `from src.collect...`. There is no `src/__init__.py`.
- No explanatory comments in code. Module/class/function docstrings stating contract are allowed; so are functional pragmas (`# noqa`).
- Type hints on every function. Pydantic models for data crossing a boundary, never raw dicts.
- Config comes from `config/settings.py` only. No `os.environ` reads in modules, no `load_dotenv()`.
- Tests must pass with no network and no database. Live payloads are saved to `tests/fixtures/live/`.
- Cleaning happens at the source boundary, inside the collector: `CleanStr` via the contract models, plus `delivery_year()`, `canonical_property_type()` / `normalize_property_types()` from `models`.
- A collector never writes to the database and never imports `db.repository`.
- `make lint` (ruff) must pass before every commit.
- Run tests with `ENV_FILE=/dev/null .venv/bin/python -m pytest`.

---

### Task 1: Collector protocol and result type

**Files:**
- Create: `src/collect/__init__.py`
- Create: `src/collect/base.py`
- Test: `tests/test_collect/test_base.py`

**Interfaces:**
- Consumes: `models.Developer`, `models.Area`, `models.Project`, `models.Unit`
- Produces: `CollectionResult` dataclass with fields `source: str`, `developers: list[Developer]`, `areas: list[Area]`, `projects: list[Project]`, `units: list[Unit]`, `fetched_at: datetime`, and methods `counts() -> dict[str, int]`, `field_coverage(entity: str) -> dict[str, float]`; `SourceCollector` Protocol with `name: str`, `min_projects: int`, `async def collect(self) -> CollectionResult`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_collect/test_base.py
from datetime import UTC, datetime

from collect.base import CollectionResult
from models import Area, Developer, Project


def _result(**overrides) -> CollectionResult:
    base = {
        "source": "nawy",
        "developers": [Developer(source="nawy", source_id="1", name="SODIC")],
        "areas": [Area(source="nawy", source_id="2", name="New Cairo")],
        "projects": [
            Project(source="nawy", source_id="3", name="Eastown", min_price=100.0),
            Project(source="nawy", source_id="4", name="Villette"),
        ],
        "units": [],
        "fetched_at": datetime.now(UTC),
    }
    return CollectionResult(**{**base, **overrides})


def test_counts_reports_every_entity():
    assert _result().counts() == {
        "developers": 1,
        "areas": 1,
        "projects": 2,
        "units": 0,
    }


def test_field_coverage_is_the_share_of_rows_with_a_value():
    """A collector can return the right number of records with every field
    empty; coverage is what catches that."""
    coverage = _result().field_coverage("projects")

    assert coverage["name"] == 1.0
    assert coverage["min_price"] == 0.5


def test_field_coverage_of_no_rows_is_empty_not_a_crash():
    assert _result(projects=[]).field_coverage("projects") == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `ENV_FILE=/dev/null .venv/bin/python -m pytest tests/test_collect/test_base.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'collect'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/collect/__init__.py
"""Source collectors. Each fetches one source and maps it onto the contract
models; none of them touch the database."""
```

```python
# src/collect/base.py
"""The contract between a source and the rest of the pipeline.

A collector fetches and maps. It returns cleaned contract models, so every
source lands in one vocabulary and downstream code never learns whether a JSON
API or an HTML parser produced a row.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from models import Area, Developer, Project, Unit

_ENTITIES = ("developers", "areas", "projects", "units")


@dataclass
class CollectionResult:
    """One source's output for one run."""

    source: str
    developers: list[Developer]
    areas: list[Area]
    projects: list[Project]
    units: list[Unit]
    fetched_at: datetime

    def counts(self) -> dict[str, int]:
        return {entity: len(getattr(self, entity)) for entity in _ENTITIES}

    def field_coverage(self, entity: str) -> dict[str, float]:
        """Share of rows with a non-empty value, per field."""
        rows = getattr(self, entity)
        if not rows:
            return {}
        fields = type(rows[0]).model_fields
        return {
            field: sum(1 for row in rows if getattr(row, field) not in (None, "", []))
            / len(rows)
            for field in fields
        }


class SourceCollector(Protocol):
    """What every source implements.

    `min_projects` is the sanity floor: a run returning fewer aborts without
    writing, because a truncated scrape that persists is worse than one that
    raises.
    """

    name: str
    min_projects: int

    async def collect(self) -> CollectionResult: ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `ENV_FILE=/dev/null .venv/bin/python -m pytest tests/test_collect/test_base.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/collect tests/test_collect
git commit -m "Add the collector protocol and result type"
```

---

### Task 2: Move Nawy onto the protocol

**Files:**
- Create: `src/collect/nawy.py` (moved from `src/backfill/nawy_client.py` via `git mv`)
- Delete: `src/backfill/nawy_client.py`
- Modify: `tests/test_backfill/test_nawy_mapping.py`, `tests/test_backfill/test_primary_only.py` (imports only)
- Test: `tests/test_collect/test_nawy_collector.py`

**Interfaces:**
- Consumes: `CollectionResult`, `SourceCollector` from Task 1; existing `fetch_developers`, `fetch_areas`, `fetch_compounds`, `fetch_launch_compound_ids`, `map_developer`, `map_area`, `map_compound`, `map_unit`, `developers_from_compounds`, `areas_from_compounds`, `compute_availability`; `watch.adapters.nawy.fetch_primary_units`.
- Produces: `NawyCollector` class with `name = "nawy"`, `min_projects = 1500`, `__init__(self, fetcher: Fetcher, units_scope: str = "all", limit: int | None = None)`, `async def collect(self) -> CollectionResult`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_collect/test_nawy_collector.py
"""The collector must produce exactly what scripts/backfill.py produced, so the
refactor is provably behaviour-preserving."""

import json
import pathlib

import pytest

from collect.nawy import NawyCollector

FIXTURES = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "live"


def _load(name: str) -> list[dict]:
    payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return payload.get("results", payload) if isinstance(payload, dict) else payload


class FakeFetcher:
    """Serves the saved payloads; asserts the collector never hits the network."""

    def __init__(self):
        self.calls = []

    async def fetch_json(self, url, **kwargs):
        raise AssertionError(f"unexpected network call to {url}")


@pytest.fixture
def collector(monkeypatch):
    monkeypatch.setattr(
        "collect.nawy.fetch_developers",
        lambda fetcher, limit=None: _async(_load("nawy_developers.json")),
    )
    monkeypatch.setattr(
        "collect.nawy.fetch_areas",
        lambda fetcher, limit=None: _async(_load("nawy_areas.json")),
    )
    monkeypatch.setattr(
        "collect.nawy.fetch_compounds",
        lambda fetcher, limit=None: _async(_load("nawy_compounds.json")),
    )
    monkeypatch.setattr(
        "collect.nawy.fetch_launch_compound_ids", lambda fetcher: _async({1198})
    )
    monkeypatch.setattr(
        "collect.nawy.fetch_primary_units",
        lambda fetcher, compound_id=None, limit=None: _async(
            _load("nawy_webapi_units.json")
        ),
    )
    return NawyCollector(FakeFetcher())


async def _async(value):
    return value


@pytest.mark.asyncio
async def test_collect_returns_every_entity(collector):
    result = await collector.collect()

    assert result.source == "nawy"
    assert result.counts()["projects"] == 3
    assert result.counts()["developers"] >= 5


@pytest.mark.asyncio
async def test_collected_projects_are_already_cleaned(collector):
    """Cleaning belongs at the source boundary, so nothing downstream repeats it."""
    result = await collector.collect()

    for project in result.projects:
        assert project.name == project.name.strip()
        if project.delivery_date is not None:
            assert len(project.delivery_date) == 4
        for property_type in project.property_types:
            assert property_type == property_type.lower()


@pytest.mark.asyncio
async def test_launch_flag_comes_from_the_launch_id_set(collector):
    result = await collector.collect()

    launches = [p for p in result.projects if p.is_launch]
    assert [p.source_id for p in launches] == ["1198"]


@pytest.mark.asyncio
async def test_collector_declares_a_sanity_floor():
    assert NawyCollector.min_projects >= 1500
```

- [ ] **Step 2: Run test to verify it fails**

Run: `ENV_FILE=/dev/null .venv/bin/python -m pytest tests/test_collect/test_nawy_collector.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'collect.nawy'`

- [ ] **Step 3: Move the module and add the collector class**

```bash
git mv src/backfill/nawy_client.py src/collect/nawy.py
```

Then update the two test files' imports:
`from backfill import nawy_client as nc` becomes `from collect import nawy as nc`.

Append to `src/collect/nawy.py`:

```python
class NawyCollector:
    """Nawy: developers, areas and compounds from the entity endpoints, plus
    primary units from the web API."""

    name = SOURCE
    min_projects = 1500

    def __init__(
        self, fetcher: Fetcher, units_scope: str = "all", limit: int | None = None
    ):
        self.fetcher = fetcher
        self.units_scope = units_scope
        self.limit = limit

    async def collect(self) -> CollectionResult:
        launch_ids = await fetch_launch_compound_ids(self.fetcher)

        developer_raw = await fetch_developers(self.fetcher)
        area_raw = await fetch_areas(self.fetcher)
        compound_raw = await fetch_compounds(self.fetcher, self.limit)

        projects = [p for p in (map_compound(c, launch_ids) for c in compound_raw) if p]
        developers = [d for d in (map_developer(d) for d in developer_raw) if d]
        developers += developers_from_compounds(compound_raw)
        areas = [a for a in (map_area(a) for a in area_raw) if a]
        areas += areas_from_compounds(compound_raw)

        loaded = {int(p.source_id) for p in projects}
        target_ids = (
            sorted(loaded)
            if self.units_scope == "all"
            else [cid for cid in launch_ids if cid in loaded]
        )
        unit_raw: list[dict] = []
        if self.units_scope == "all":
            unit_raw = await fetch_primary_units(self.fetcher)
            unit_raw = [
                u for u in unit_raw if (u.get("compound") or {}).get("id") in loaded
            ]
        else:
            for compound_id in target_ids:
                unit_raw.extend(
                    await fetch_primary_units(self.fetcher, compound_id=compound_id)
                )
        units = [u for u in (map_unit(u) for u in unit_raw) if u]

        return CollectionResult(
            source=self.name,
            developers=developers,
            areas=areas,
            projects=projects,
            units=units,
            fetched_at=datetime.now(UTC),
        )
```

Add to the imports at the top of `src/collect/nawy.py`:

```python
from datetime import UTC, datetime

from collect.base import CollectionResult
```

- [ ] **Step 4: Run the whole suite to verify nothing regressed**

Run: `ENV_FILE=/dev/null .venv/bin/python -m pytest -q`
Expected: all previously passing tests still pass, plus 4 new ones. The
`test_extract` scrapegraphai failure is pre-existing and stays.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "Move Nawy collection onto the collector protocol"
```

---

### Task 3: Move Property Finder onto the protocol

**Files:**
- Create: `src/collect/property_finder.py` (moved from `src/backfill/property_finder_client.py` via `git mv`)
- Delete: `src/backfill/property_finder_client.py`, `src/backfill/__init__.py`
- Modify: `tests/test_backfill/test_property_finder_mapping.py` (imports only)
- Test: `tests/test_collect/test_property_finder_collector.py`

**Interfaces:**
- Consumes: `CollectionResult` from Task 1; existing `fetch_projects`, `map_project`, `developers_from_projects`, `areas_from_projects`.
- Produces: `PropertyFinderCollector` with `name = "property_finder"`, `min_projects = 1000`, `__init__(self, fetcher: Fetcher, limit: int | None = None)`, `async def collect(self) -> CollectionResult`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_collect/test_property_finder_collector.py
import json
import pathlib

import pytest

from collect.property_finder import PropertyFinderCollector

FIXTURE = (
    pathlib.Path(__file__).resolve().parents[1]
    / "fixtures"
    / "live"
    / "property_finder_new_projects.json"
)


async def _async(value):
    return value


@pytest.fixture
def collector(monkeypatch):
    projects = json.loads(FIXTURE.read_text(encoding="utf-8"))["projects"]
    monkeypatch.setattr(
        "collect.property_finder.fetch_projects",
        lambda fetcher, limit=None: _async(projects),
    )
    return PropertyFinderCollector(fetcher=None)


@pytest.mark.asyncio
async def test_collect_derives_developers_and_areas_from_projects(collector):
    """Property Finder has no standalone developer or area feed."""
    result = await collector.collect()

    assert result.source == "property_finder"
    assert result.projects
    assert result.developers
    assert result.areas


@pytest.mark.asyncio
async def test_property_finder_contributes_no_units(collector):
    """Its listing carries no per-unit rows; units must be empty, not invented."""
    result = await collector.collect()

    assert result.units == []


@pytest.mark.asyncio
async def test_completed_developments_are_not_flagged_as_launches(collector):
    result = await collector.collect()

    flags = [p.is_launch for p in result.projects]
    assert any(flags) and not all(flags)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `ENV_FILE=/dev/null .venv/bin/python -m pytest tests/test_collect/test_property_finder_collector.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'collect.property_finder'`

- [ ] **Step 3: Move the module and add the collector class**

```bash
git mv src/backfill/property_finder_client.py src/collect/property_finder.py
git rm src/backfill/__init__.py
```

Update `tests/test_backfill/test_property_finder_mapping.py`:
`from backfill import property_finder_client as pf` becomes
`from collect import property_finder as pf`.

Append to `src/collect/property_finder.py`:

```python
class PropertyFinderCollector:
    """Property Finder: developers and areas are derived from the projects,
    which is all the new-projects listing exposes."""

    name = SOURCE
    min_projects = 1000

    def __init__(self, fetcher: Fetcher, limit: int | None = None):
        self.fetcher = fetcher
        self.limit = limit

    async def collect(self) -> CollectionResult:
        raws = await fetch_projects(self.fetcher, self.limit)
        projects = [p for p in (map_project(r) for r in raws) if p]

        return CollectionResult(
            source=self.name,
            developers=developers_from_projects(raws),
            areas=areas_from_projects(raws),
            projects=projects,
            units=[],
            fetched_at=datetime.now(UTC),
        )
```

Add to the imports at the top of `src/collect/property_finder.py`:

```python
from datetime import UTC, datetime

from collect.base import CollectionResult
```

- [ ] **Step 4: Run the whole suite**

Run: `ENV_FILE=/dev/null .venv/bin/python -m pytest -q`
Expected: all pass except the pre-existing `test_extract` failure.

- [ ] **Step 5: Move the mapping tests to mirror src, then commit**

```bash
git mv tests/test_backfill tests/test_collect_mapping
git add -A
git commit -m "Move Property Finder collection onto the collector protocol"
```

---

### Task 4: Registry

**Files:**
- Create: `src/collect/registry.py`
- Test: `tests/test_collect/test_registry.py`

**Interfaces:**
- Consumes: `NawyCollector` (Task 2), `PropertyFinderCollector` (Task 3).
- Produces: `COLLECTOR_REGISTRY: dict[str, type]`, `get_collector_class(name: str) -> type`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_collect/test_registry.py
import pytest

from collect.nawy import NawyCollector
from collect.registry import COLLECTOR_REGISTRY, get_collector_class


def test_known_sources_resolve():
    assert get_collector_class("nawy") is NawyCollector


def test_unknown_source_names_the_known_ones():
    """A typo in a schedule must not fail with a bare KeyError."""
    with pytest.raises(ValueError) as exc:
        get_collector_class("nawi")

    assert "nawy" in str(exc.value)


def test_every_registered_collector_declares_its_contract():
    for name, collector in COLLECTOR_REGISTRY.items():
        assert collector.name == name
        assert collector.min_projects > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `ENV_FILE=/dev/null .venv/bin/python -m pytest tests/test_collect/test_registry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'collect.registry'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/collect/registry.py
"""Source name -> collector class. Adding a source is one line here."""

from collect.nawy import NawyCollector
from collect.property_finder import PropertyFinderCollector

COLLECTOR_REGISTRY: dict[str, type] = {
    NawyCollector.name: NawyCollector,
    PropertyFinderCollector.name: PropertyFinderCollector,
}


def get_collector_class(name: str) -> type:
    try:
        return COLLECTOR_REGISTRY[name]
    except KeyError:
        raise ValueError(
            f"No collector registered for {name!r}. "
            f"Known sources: {sorted(COLLECTOR_REGISTRY)}"
        ) from None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `ENV_FILE=/dev/null .venv/bin/python -m pytest tests/test_collect/test_registry.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/collect/registry.py tests/test_collect/test_registry.py
git commit -m "Add the collector registry"
```

---

### Task 5: Run report — floors, coverage, stop reason

**Files:**
- Create: `src/collect/report.py`
- Test: `tests/test_collect/test_report.py`

**Interfaces:**
- Consumes: `CollectionResult` (Task 1).
- Produces: `StopReason` str-Enum with members `COMPLETE`, `NO_RECORDS`, `BELOW_FLOOR`, `FETCH_ERROR`; `RunReport` dataclass with `source: str`, `stop_reason: StopReason`, `counts: dict[str, int]`, `coverage: dict[str, float]`, `message: str`, and property `ok: bool`; `evaluate(result: CollectionResult, min_projects: int, coverage_floors: dict[str, float]) -> RunReport`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_collect/test_report.py
from datetime import UTC, datetime

import pytest

from collect.base import CollectionResult
from collect.report import StopReason, evaluate
from models import Project


def _result(projects):
    return CollectionResult(
        source="aqarmap",
        developers=[],
        areas=[],
        projects=projects,
        units=[],
        fetched_at=datetime.now(UTC),
    )


def _projects(count, with_price=True):
    return [
        Project(
            source="aqarmap",
            source_id=str(i),
            name=f"P{i}",
            min_price=100.0 if with_price else None,
        )
        for i in range(count)
    ]


def test_a_full_run_is_complete():
    report = evaluate(_result(_projects(10)), min_projects=5, coverage_floors={})

    assert report.stop_reason is StopReason.COMPLETE
    assert report.ok


def test_a_truncated_run_is_below_floor():
    """A scrape returning 12 of ~1988 means the markup changed. Writing that
    would silently gut the catalogue."""
    report = evaluate(_result(_projects(2)), min_projects=5, coverage_floors={})

    assert report.stop_reason is StopReason.BELOW_FLOOR
    assert not report.ok
    assert "2" in report.message and "5" in report.message


def test_an_empty_run_is_distinguishable_from_a_truncated_one():
    report = evaluate(_result([]), min_projects=5, coverage_floors={})

    assert report.stop_reason is StopReason.NO_RECORDS


def test_collapsed_field_coverage_fails_even_at_full_count():
    """An HTML parser fails by returning the right number of rows with every
    field empty."""
    report = evaluate(
        _result(_projects(10, with_price=False)),
        min_projects=5,
        coverage_floors={"min_price": 0.8},
    )

    assert report.stop_reason is StopReason.BELOW_FLOOR
    assert "min_price" in report.message


@pytest.mark.parametrize("share", [0.8, 1.0])
def test_coverage_at_or_above_the_floor_passes(share):
    count = 10
    projects = _projects(int(count * share)) + _projects(
        count - int(count * share), with_price=False
    )
    for index, project in enumerate(projects):
        project.source_id = str(index)

    report = evaluate(
        _result(projects), min_projects=5, coverage_floors={"min_price": 0.8}
    )

    assert report.stop_reason is StopReason.COMPLETE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `ENV_FILE=/dev/null .venv/bin/python -m pytest tests/test_collect/test_report.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'collect.report'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/collect/report.py
"""Whether a run may be persisted, and why not when it may not.

A run that writes a truncated catalogue is worse than one that raises: the
partial data looks like a real result and nothing downstream can tell.
"""

from dataclasses import dataclass
from enum import Enum

from collect.base import CollectionResult


class StopReason(str, Enum):
    COMPLETE = "complete"
    NO_RECORDS = "no_records"
    BELOW_FLOOR = "below_floor"
    FETCH_ERROR = "fetch_error"


@dataclass
class RunReport:
    source: str
    stop_reason: StopReason
    counts: dict[str, int]
    coverage: dict[str, float]
    message: str

    @property
    def ok(self) -> bool:
        return self.stop_reason is StopReason.COMPLETE


def evaluate(
    result: CollectionResult,
    min_projects: int,
    coverage_floors: dict[str, float],
) -> RunReport:
    counts = result.counts()
    coverage = result.field_coverage("projects")

    if counts["projects"] == 0:
        return RunReport(
            result.source,
            StopReason.NO_RECORDS,
            counts,
            coverage,
            "no projects returned",
        )

    if counts["projects"] < min_projects:
        return RunReport(
            result.source,
            StopReason.BELOW_FLOOR,
            counts,
            coverage,
            f"{counts['projects']} projects is below the floor of {min_projects}",
        )

    short = [
        f"{field} {coverage.get(field, 0.0):.0%} < {floor:.0%}"
        for field, floor in coverage_floors.items()
        if coverage.get(field, 0.0) < floor
    ]
    if short:
        return RunReport(
            result.source,
            StopReason.BELOW_FLOOR,
            counts,
            coverage,
            "field coverage collapsed: " + ", ".join(short),
        )

    return RunReport(result.source, StopReason.COMPLETE, counts, coverage, "ok")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `ENV_FILE=/dev/null .venv/bin/python -m pytest tests/test_collect/test_report.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add src/collect/report.py tests/test_collect/test_report.py
git commit -m "Add run evaluation: sanity floor, coverage floor, stop reason"
```

---

### Task 6: Snapshots for every source

**Files:**
- Create: `src/collect/snapshot.py`
- Modify: `src/db/repository.py` (add `ON CONFLICT DO NOTHING` to `save_availability`, around line 324)
- Test: `tests/test_collect/test_snapshot.py`

**Interfaces:**
- Consumes: `CollectionResult` (Task 1); `models.Availability`; existing `collect.nawy.compute_availability`.
- Produces: `snapshots_for(result: CollectionResult) -> list[Availability]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_collect/test_snapshot.py
"""History only accrues forward, so every source snapshots every run — filling
what it knows and leaving the rest NULL."""

from datetime import UTC, datetime

from collect.base import CollectionResult
from collect.snapshot import snapshots_for
from models import Project, Unit


def _result(projects, units, source="property_finder"):
    return CollectionResult(
        source=source,
        developers=[],
        areas=[],
        projects=projects,
        units=units,
        fetched_at=datetime(2026, 8, 6, 12, 0, tzinfo=UTC),
    )


def test_a_source_without_units_still_snapshots_price():
    projects = [
        Project(source="property_finder", source_id="7", name="X", min_price=5_000_000.0)
    ]

    snapshots = snapshots_for(_result(projects, []))

    assert len(snapshots) == 1
    assert snapshots[0].min_price == 5_000_000.0
    assert snapshots[0].total_units is None


def test_a_source_with_units_snapshots_the_unit_rollup():
    projects = [Project(source="nawy", source_id="1198", name="Southmed")]
    units = [
        Unit(source="nawy", source_id="a", project_source_id="1198", price=100.0,
             unit_area_sqm=10.0, property_type="villa"),
        Unit(source="nawy", source_id="b", project_source_id="1198", price=300.0,
             unit_area_sqm=10.0, property_type="chalet"),
    ]

    snapshots = snapshots_for(_result(projects, units, source="nawy"))

    rollup = next(s for s in snapshots if s.project_source_id == "1198")
    assert rollup.total_units == 2
    assert rollup.min_price == 100.0
    assert rollup.max_price == 300.0


def test_every_snapshot_in_a_run_shares_one_timestamp():
    """One timestamp per run is what makes a retry idempotent."""
    projects = [
        Project(source="property_finder", source_id=str(i), name=f"P{i}")
        for i in range(3)
    ]

    stamps = {s.snapshot_at for s in snapshots_for(_result(projects, []))}

    assert len(stamps) == 1


def test_projects_with_no_price_and_no_units_are_still_recorded():
    """Absence at a point in time is itself a data point for trends."""
    projects = [Project(source="property_finder", source_id="9", name="Y")]

    assert len(snapshots_for(_result(projects, []))) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `ENV_FILE=/dev/null .venv/bin/python -m pytest tests/test_collect/test_snapshot.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'collect.snapshot'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/collect/snapshot.py
"""One availability snapshot per project per run, for every source.

Sources without unit rows contribute price and delivery only; that is still
enough for price movement and new-entrant detection. History cannot be
backfilled, so a run writes a snapshot whether or not anything changed.
"""

from collect.base import CollectionResult
from collect.nawy import compute_availability
from models import Availability


def snapshots_for(result: CollectionResult) -> list[Availability]:
    from_units = {
        snapshot.project_source_id: snapshot
        for snapshot in compute_availability(result.units, result.fetched_at)
    }

    snapshots: list[Availability] = []
    for project in result.projects:
        rollup = from_units.get(project.source_id)
        if rollup is not None:
            snapshots.append(rollup)
            continue
        snapshots.append(
            Availability(
                source=result.source,
                project_source_id=project.source_id,
                snapshot_at=result.fetched_at,
                min_price=project.min_price,
                delivery_range=project.delivery_date,
            )
        )
    return snapshots
```

- [ ] **Step 4: Run test to verify it passes**

Run: `ENV_FILE=/dev/null .venv/bin/python -m pytest tests/test_collect/test_snapshot.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Make a retried run idempotent**

The unique constraint already exists — migration `d6e7f8a9b0c1` added
`uq_availability_source_project_run` on `(source_id, project_id, snapshot_at)`,
ordered so the same index also serves per-source history queries. Only the
insert needs changing.

In `src/db/repository.py`, replace the `session.add(AvailabilityRow(...))` call
in `save_availability` with a Postgres upsert that ignores repeats:

```python
            session.execute(
                insert(AvailabilityRow)
                .values(
                    project_id=project_id,
                    source_id=smap[snap.source],
                    snapshot_at=snap.snapshot_at,
                    total_units=snap.total_units,
                    available_units=snap.available_units,
                    min_price=snap.min_price,
                    max_price=snap.max_price,
                    price_per_sqm_min=snap.price_per_sqm_min,
                    price_per_sqm_max=snap.price_per_sqm_max,
                    unit_types=snap.unit_types,
                    delivery_range=snap.delivery_range,
                )
                .on_conflict_do_nothing(
                    constraint="uq_availability_source_project_run"
                )
            )
```

- [ ] **Step 6: Run the suite**

Run: `ENV_FILE=/dev/null .venv/bin/python -m pytest -q`
Expected: suite passes except the pre-existing `test_extract` failure.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "Snapshot every project on every run, for every source"
```

---

### Task 7: One flow for any source, and the CLI with --dry-run

**Files:**
- Modify: `src/pipeline/flows.py` (add `collect_source`; leave `crawl_one_source` alone)
- Create: `scripts/collect.py`
- Delete: `scripts/backfill.py`
- Test: `tests/test_pipeline/test_collect_flow.py`

**Interfaces:**
- Consumes: `get_collector_class` (Task 4), `evaluate` / `StopReason` / `RunReport` (Task 5), `snapshots_for` (Task 6), `db.repository.upsert_developers` / `upsert_areas` / `upsert_projects` / `upsert_units` / `save_availability`.
- Produces: `async def collect_source(source_name: str, dry_run: bool = False, limit: int | None = None) -> RunReport`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pipeline/test_collect_flow.py
"""The flow is the only place that writes, so this is where 'refuses to persist
a bad run' is proven."""

from datetime import UTC, datetime

import pytest

from collect.base import CollectionResult
from collect.report import StopReason
from models import Project
from pipeline.flows import collect_source


class StubCollector:
    name = "stub"
    min_projects = 5

    def __init__(self, project_count, **kwargs):
        self.project_count = project_count

    async def collect(self):
        return CollectionResult(
            source=self.name,
            developers=[],
            areas=[],
            projects=[
                Project(source="stub", source_id=str(i), name=f"P{i}", min_price=1.0)
                for i in range(self.project_count)
            ],
            units=[],
            fetched_at=datetime.now(UTC),
        )


@pytest.fixture
def writes(monkeypatch):
    recorded = []
    for name in (
        "upsert_developers",
        "upsert_areas",
        "upsert_projects",
        "upsert_units",
        "save_availability",
    ):
        monkeypatch.setattr(
            f"pipeline.flows.repo.{name}",
            lambda *a, _n=name, **k: recorded.append(_n) or {},
        )
    return recorded


@pytest.fixture
def register(monkeypatch):
    def _register(project_count):
        monkeypatch.setattr(
            "pipeline.flows.get_collector_class",
            lambda name: lambda **kwargs: StubCollector(project_count),
        )
    return _register


@pytest.mark.asyncio
async def test_a_healthy_run_persists(register, writes):
    register(10)

    report = await collect_source("stub")

    assert report.stop_reason is StopReason.COMPLETE
    assert "upsert_projects" in writes


@pytest.mark.asyncio
async def test_a_run_below_the_floor_writes_nothing(register, writes):
    register(2)

    report = await collect_source("stub")

    assert report.stop_reason is StopReason.BELOW_FLOOR
    assert writes == []


@pytest.mark.asyncio
async def test_dry_run_writes_nothing_even_when_healthy(register, writes):
    register(10)

    report = await collect_source("stub", dry_run=True)

    assert report.stop_reason is StopReason.COMPLETE
    assert writes == []


@pytest.mark.asyncio
async def test_a_fetch_error_is_reported_not_raised(monkeypatch, writes):
    class Broken(StubCollector):
        async def collect(self):
            raise TimeoutError("upstream gone")

    monkeypatch.setattr(
        "pipeline.flows.get_collector_class", lambda name: lambda **kwargs: Broken(0)
    )

    report = await collect_source("stub")

    assert report.stop_reason is StopReason.FETCH_ERROR
    assert writes == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `ENV_FILE=/dev/null .venv/bin/python -m pytest tests/test_pipeline/test_collect_flow.py -v`
Expected: FAIL with `ImportError: cannot import name 'collect_source'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/pipeline/flows.py`:

```python
@flow(name="collect-one-source")
async def collect_source(
    source_name: str, dry_run: bool = False, limit: int | None = None
) -> RunReport:
    """Collect one source and persist it, unless the run fails its floors.

    Returns a report rather than raising, so one source failing leaves the
    others untouched and the reason is recorded rather than inferred.
    """
    collector_class = get_collector_class(source_name)
    collector = collector_class(fetcher=Fetcher(), limit=limit)

    try:
        result = await collector.collect()
    except Exception as exc:
        logger.exception("collect source=%s stop_reason=fetch_error", source_name)
        return RunReport(
            source_name, StopReason.FETCH_ERROR, {}, {}, f"{type(exc).__name__}: {exc}"
        )

    report = evaluate(result, collector.min_projects, COVERAGE_FLOORS.get(source_name, {}))
    if not report.ok:
        logger.error(
            "collect source=%s stop_reason=%s %s",
            source_name, report.stop_reason.value, report.message,
        )
        return report
    if dry_run:
        logger.info("collect source=%s dry_run counts=%s", source_name, report.counts)
        return report

    developer_map = repo.upsert_developers(result.developers)
    area_map = repo.upsert_areas(result.areas)
    project_map = repo.upsert_projects(result.projects, developer_map, area_map)
    repo.upsert_units(result.units, project_map)
    repo.save_availability(snapshots_for(result), project_map)

    logger.info(
        "collect source=%s stop_reason=complete counts=%s", source_name, report.counts
    )
    return report
```

Add to the imports at the top of `src/pipeline/flows.py`:

```python
from collect.registry import get_collector_class
from collect.report import RunReport, StopReason, evaluate
from collect.snapshot import snapshots_for
from db import repository as repo
from watch.fetcher import Fetcher

COVERAGE_FLOORS: dict[str, dict[str, float]] = {
    "nawy": {"name": 0.99},
    "property_finder": {"name": 0.99, "delivery_date": 0.8},
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `ENV_FILE=/dev/null .venv/bin/python -m pytest tests/test_pipeline/test_collect_flow.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Write the CLI**

Create `scripts/collect.py`:

```python
"""Collect one source into the catalogue.

    python scripts/collect.py --source nawy
    python scripts/collect.py --source aqarmap --dry-run

--dry-run fetches and maps for real, prints what it would write, and exits
without touching the database.
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from collect.registry import COLLECTOR_REGISTRY  # noqa: E402
from pipeline.flows import collect_source  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=sorted(COLLECTOR_REGISTRY), required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    report = asyncio.run(
        collect_source(args.source, dry_run=args.dry_run, limit=args.limit)
    )

    print(f"\nsource       : {report.source}")
    print(f"stop_reason  : {report.stop_reason.value}")
    print(f"counts       : {report.counts}")
    print(f"message      : {report.message}")
    if report.coverage:
        print("coverage     :")
        for field, share in sorted(report.coverage.items(), key=lambda kv: kv[1]):
            print(f"  {field:24} {share:6.1%}")

    sys.exit(0 if report.ok else 1)


if __name__ == "__main__":
    main()
```

Then `git rm scripts/backfill.py`.

- [ ] **Step 6: Verify against the live sources**

Run: `ENV_FILE=.env.dev .venv/bin/python scripts/collect.py --source property_finder --dry-run --limit 100`
Expected: exits 0, prints counts and coverage, and `SELECT count(*) FROM projects` is unchanged.

Run: `ENV_FILE=.env.dev .venv/bin/python scripts/collect.py --source nawy`
Expected: exits 0, `stop_reason: complete`, project count matches the pre-refactor 1,835.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "Add one collection flow for any source, with a dry-run CLI"
```

---

### Task 8: Aqarmap collector

**Files:**
- Create: `src/collect/aqarmap.py`
- Create: `tests/fixtures/live/aqarmap_compounds.html`
- Modify: `src/collect/registry.py`
- Modify: `src/config/sources.yaml`
- Test: `tests/test_collect/test_aqarmap_collector.py`

**Interfaces:**
- Consumes: `CollectionResult` (Task 1); `models.Project`, `models.Developer`, `models.Area`; `models.delivery_year`, `models.normalize_property_types`.
- Produces: `AqarmapCollector` with `name = "aqarmap"`, `min_projects = 1500`; `parse_compounds(html: str) -> list[dict]`; `map_compound(raw: dict) -> Project | None`.

**Before writing code:** save a real payload.

```bash
.venv/bin/python - <<'PY'
import httpx, pathlib
r = httpx.get("https://aqarmap.com.eg/en/compounds/",
              headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) "
                                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                                      "Chrome/127.0.0.0 Safari/537.36"},
              timeout=45, follow_redirects=True)
pathlib.Path("tests/fixtures/live/aqarmap_compounds.html").write_text(r.text)
print(r.status_code, len(r.text))
PY
```

**Then, before writing the parser,** confirm the two open questions from the
spec against that file: whether the compound list is server-rendered or
lazy-loaded (the first probe found only 6 compound links of ~1,988), and
whether each compound exposes a developer name. If the list is lazy-loaded,
stop and report — the collector then needs `Fetcher.fetch_rendered_html`
instead of `fetch_json`, and the cadence drops. Do not guess selectors.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_collect/test_aqarmap_collector.py
"""Aqarmap is the first source with no structured payload, so these tests pin
the parser against a saved page."""

import pathlib

import pytest

from collect.aqarmap import AqarmapCollector, map_compound, parse_compounds

FIXTURE = (
    pathlib.Path(__file__).resolve().parents[1]
    / "fixtures"
    / "live"
    / "aqarmap_compounds.html"
)


@pytest.fixture
def html():
    return FIXTURE.read_text(encoding="utf-8")


def test_parser_finds_compounds(html):
    compounds = parse_compounds(html)

    assert len(compounds) >= 6
    assert all(c.get("name") for c in compounds)


def test_mapped_projects_are_cleaned(html):
    for raw in parse_compounds(html):
        project = map_compound(raw)
        if project is None:
            continue
        assert project.name == project.name.strip()
        if project.delivery_date is not None:
            assert len(project.delivery_date) == 4
        for property_type in project.property_types:
            assert property_type == property_type.lower()


def test_records_without_a_name_are_skipped():
    assert map_compound({"url": "/en/compound/1"}) is None


def test_collector_declares_a_provisional_floor():
    """Confirmed against a real full run before aqarmap is scheduled."""
    assert AqarmapCollector.min_projects >= 1500
```

- [ ] **Step 2: Run test to verify it fails**

Run: `ENV_FILE=/dev/null .venv/bin/python -m pytest tests/test_collect/test_aqarmap_collector.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'collect.aqarmap'`

- [ ] **Step 3: Write the parser and collector**

Write `src/collect/aqarmap.py` with `parse_compounds` using BeautifulSoup against
the selectors observed in the saved fixture, `map_compound` producing a
`Project` through `delivery_year()` and `normalize_property_types()`, and
`AqarmapCollector.collect()` paginating the compounds guide. Follow the shape of
`src/collect/property_finder.py`: fetch, map, derive developers and areas from
the projects, return `CollectionResult` with `units=[]`.

Selectors come from the fixture, not from memory. If a field is absent from the
page, leave it `None` rather than inventing a source for it.

- [ ] **Step 4: Run test to verify it passes**

Run: `ENV_FILE=/dev/null .venv/bin/python -m pytest tests/test_collect/test_aqarmap_collector.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Register the source**

In `src/collect/registry.py` add `AqarmapCollector.name: AqarmapCollector` to
`COLLECTOR_REGISTRY` and import it.

In `src/config/sources.yaml` add:

```yaml
  - name: aqarmap
    tier: 2
    source_type: aggregator
    urls:
      - "https://aqarmap.com.eg/en/compounds/"
    crawl_frequency: "24h"
    adapter_name: aqarmap
```

Add a `sources` row via a migration so `source_id_map()` resolves it:

```python
op.execute(
    "INSERT INTO sources (id, name, display_name, base_url, source_type, "
    "is_primary, created_at) VALUES "
    "(3, 'aqarmap', 'Aqarmap', 'https://aqarmap.com.eg', 'aggregator', false, now()) "
    "ON CONFLICT (id) DO NOTHING"
)
```

- [ ] **Step 6: Dry run against the live site**

Run: `ENV_FILE=.env.dev .venv/bin/python scripts/collect.py --source aqarmap --dry-run`
Expected: prints counts and per-field coverage and writes nothing. **Read the
output before proceeding.** Confirm an Aqarmap "compound" really is our
`Project`, and set `min_projects` to roughly 75% of the real count.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "Add the Aqarmap collector"
```

---

### Task 9: Per-source schedules

**Files:**
- Create: `src/pipeline/deployments.py`
- Modify: `Makefile`
- Test: `tests/test_pipeline/test_deployments.py`

**Interfaces:**
- Consumes: `collect_source` (Task 7), `COLLECTOR_REGISTRY` (Task 4).
- Produces: `SCHEDULES: dict[str, str]` mapping source name to cron; `def deployment_specs() -> list[dict]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pipeline/test_deployments.py
from collect.registry import COLLECTOR_REGISTRY
from pipeline.deployments import SCHEDULES, deployment_specs


def test_every_registered_source_has_a_schedule():
    """A source that collects but is never scheduled looks healthy and returns
    stale data forever."""
    assert set(SCHEDULES) == set(COLLECTOR_REGISTRY)


def test_each_source_gets_its_own_deployment():
    specs = deployment_specs()

    assert len(specs) == len(COLLECTOR_REGISTRY)
    assert len({spec["name"] for spec in specs}) == len(specs)


def test_scraped_sources_are_scheduled_less_often_than_api_sources():
    """Aqarmap needs a fetch per page; Nawy is one API scan."""
    assert SCHEDULES["aqarmap"].startswith("0 3")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `ENV_FILE=/dev/null .venv/bin/python -m pytest tests/test_pipeline/test_deployments.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.deployments'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/pipeline/deployments.py
"""One Prefect deployment per source, so a failing source cannot block another.

Cadence follows collection cost: an API scan can run often, a page-by-page
scrape cannot.
"""

from collect.registry import COLLECTOR_REGISTRY

SCHEDULES: dict[str, str] = {
    "nawy": "0 */6 * * *",
    "property_finder": "0 */12 * * *",
    "aqarmap": "0 3 * * *",
}


def deployment_specs() -> list[dict]:
    return [
        {
            "name": f"collect-{name}",
            "flow": "collect-one-source",
            "parameters": {"source_name": name},
            "cron": SCHEDULES[name],
        }
        for name in sorted(COLLECTOR_REGISTRY)
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `ENV_FILE=/dev/null .venv/bin/python -m pytest tests/test_pipeline/test_deployments.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Add Makefile targets**

```makefile
collect:
	python scripts/collect.py --source $(SOURCE)

collect-dry:
	python scripts/collect.py --source $(SOURCE) --dry-run
```

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "Add per-source collection schedules"
```

---

### Task 10: Cross-source coverage check

**Files:**
- Modify: `src/metrics/quality.py`
- Test: `tests/test_metrics/test_source_overlap.py`

**Interfaces:**
- Consumes: `db.tables.Project`, `db.tables.Source`.
- Produces: `source_overlap(session) -> list[dict]` with keys `source`, `projects`, `shared`, `unique`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_metrics/test_source_overlap.py
"""Coverage is the reason for adding sources, so it has to be measurable.

A source contributing 1,988 projects that share only 20 with Nawy means either
the dedup thresholds are wrong or the two are not describing the same things.
"""

from metrics.quality import source_overlap


class FakeSession:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, _stmt):
        return self

    def all(self):
        return self._rows


def test_overlap_splits_shared_from_unique():
    rows = [("nawy", 100, 30), ("aqarmap", 80, 30)]

    overlap = source_overlap(FakeSession(rows))

    by_source = {row["source"]: row for row in overlap}
    assert by_source["nawy"]["shared"] == 30
    assert by_source["nawy"]["unique"] == 70
    assert by_source["aqarmap"]["unique"] == 50
```

- [ ] **Step 2: Run test to verify it fails**

Run: `ENV_FILE=/dev/null .venv/bin/python -m pytest tests/test_metrics/test_source_overlap.py -v`
Expected: FAIL with `ImportError: cannot import name 'source_overlap'`

- [ ] **Step 3: Write minimal implementation**

Add to `src/metrics/quality.py`:

```python
def source_overlap(session) -> list[dict]:
    """Projects per source, and how many are also reported by another source."""
    rows = session.execute(_SOURCE_OVERLAP_STMT).all()
    return [
        {"source": source, "projects": projects, "shared": shared,
         "unique": projects - shared}
        for source, projects, shared in rows
    ]
```

with `_SOURCE_OVERLAP_STMT` selecting, per source: the project count, and the
count of those whose `canonical_id` is set or which are the canonical target of
a project from another source.

- [ ] **Step 4: Run test to verify it passes**

Run: `ENV_FILE=/dev/null .venv/bin/python -m pytest tests/test_metrics/test_source_overlap.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Check the real numbers**

Run: `ENV_FILE=.env.dev .venv/bin/python scripts/dedup.py`
Then query `source_overlap` against the live database and read the result. If
Aqarmap shares almost nothing with Nawy, stop and investigate before treating
its projects as added coverage.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "Report cross-source project overlap"
```

---

## Self-review notes

Checked against the spec:

- Collector protocol + registry → Tasks 1, 4
- Cleaning at the source boundary → asserted in Tasks 2, 3, 8
- Collectors never touch the database → enforced by Task 7 owning all writes
- Sanity floor and coverage floor → Task 5, wired in Task 7
- `stop_reason` on every exit path → Task 5, all four values reachable in Task 7
- Snapshots for every source, retry-safe → Task 6
- Per-source Prefect deployments → Task 9
- Dry-run mode → Task 7 (flow) and Task 7 step 5 (CLI)
- Fixture before collector → Task 8 pre-step
- Cross-source consistency → Task 10
- Repair rule (mapping fix ships a migration) → stated in Global Constraints;
  no mapping change in this plan requires one, since Tasks 2 and 3 are moves.
- Bayut → correctly absent; it is registered but disabled and has no collector.

Open questions from the spec are handled as an explicit stop-and-report gate in
Task 8 rather than being guessed at.
