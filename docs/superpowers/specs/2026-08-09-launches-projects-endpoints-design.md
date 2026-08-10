# Launches and projects endpoints — design

**Date:** 2026-08-09
**Status:** approved, not yet implemented
**Scope:** a change feed, project search, and project detail, plus the shared
scoping they need.

## Goal

Answer the question the R&D team actually opens the dashboard to ask: **did a
competitor just move?** Then let them click through to the thing that moved.

Today there are eight aggregate endpoints and no way to see an individual
project. `src/api/routes/launches.py` has zero routes in a product whose
purpose is launch intelligence.

## What each endpoint is for

| Endpoint | Question it answers |
|---|---|
| `GET /launches` | What changed since I last looked? |
| `GET /projects/{id}` | Tell me everything about that one |
| `GET /projects` | Find the ones matching these criteria |

## Architecture

```
src/api/queries.py            scoping shared by every catalogue endpoint
src/api/changes.py            pure change detection over snapshot rows
src/api/routes/launches.py    GET /launches
src/api/routes/projects.py    GET /projects, GET /projects/{id}
```

Two modules because a change feed and a searchable catalogue are different
concerns, following the existing one-module-per-concern pattern. Adding them to
`insights.py` would make a 360-line file with eight endpoints into the file
everything lives in.

### queries.py, and a bug it fixes

`_scoped` is currently private to `insights.py`. Three modules now need it, and
a duplicated scoping rule is how two endpoints drift into disagreeing about what
a zone is.

It also carries a real defect. Zone filtering and grouping match `Area.name`
directly, with no canonical resolution — so "New Cairo" (Nawy) and "New Cairo
City" (Property Finder) are treated as two separate zones. `/insights/zones`
reports New Cairo at 383 projects; resolved through `areas.canonical_id` the
figure is 521. The area dedup we built is simply never used at read time.

Moving the helper fixes it once, for every caller including `/insights/zones`.

**This changes numbers on a shipped endpoint.** `/insights/zones` will report
larger, fewer zones. It is a correction, not a regression, and it goes in
`docs/DASHBOARD_API.md` so the dashboard team reads it as one.

### changes.py, and why it is separate

Materiality logic lives in a pure function over snapshot rows:

```python
detect_price_changes(snapshots, min_change_pct) -> list[PriceChange]
```

No database, no session — so the rule that decides whether the feed is
trustworthy can be tested directly, with hand-built inputs covering the cases
that matter.

## The noise problem, and the rule

Known Issue #3: Nawy's `minPrice` depends on live inventory, so it moves between
crawls when nothing has launched. A feed built on raw price deltas would fire
constantly and be ignored within a week.

A price change is reported when **all three** hold:

1. There are at least 2 snapshots in the window.
2. The move from the first to the last snapshot is at least `min_change_pct`
   (default 5, tunable per request).
3. The most recent step runs in the same direction as the overall move — so a
   spike that has already reverted stays quiet.

With exactly two snapshots, condition 3 is trivially satisfied by the only step
present. That degrades gracefully rather than erroring.

New entrants need no threshold: `first_seen_at` is exact. It is set on insert
and is **not** in the upsert's update columns, so a re-sync never overwrites it.

### What the feed will actually show today

Three runs of snapshots exist. The price half will be nearly empty until the
schedule has been running for a while; the new-entrant half works immediately.

This is worth stating in the response rather than letting an empty list read as
"nothing moved". `/launches` returns `snapshot_runs_in_window` alongside its
results, so a caller can tell "no movement" from "not enough history yet".

## Endpoints

### GET /launches

```
?since=7d  &min_change_pct=5  &zone=  &developer=  &source=  &limit=  &offset=
```

One row per **event**, newest first:

| Field | Notes |
|---|---|
| `kind` | `new` or `price_change` |
| `project_id`, `name`, `developer`, `zone`, `source` | zone is the canonical zone |
| `first_seen_at`, `min_price` | on `new` rows |
| `from_price`, `to_price`, `change_pct`, `observed_at` | on `price_change` rows |

`since` accepts `7d`/`30d` or an ISO date. Default 7d.

### GET /projects/{id}

The project, its developer, and its canonical zone; plus:

- **unit summary** — count, price range, price-per-sqm range, bedroom mix,
  property types, finishing mix
- **price history** — its snapshots, oldest first
- **also listed on** — the other sources reporting this project, from the
  canonical cluster

Requesting a *duplicate's* id returns the canonical project with the requested
id echoed back, so a link built from any source lands somewhere sensible instead
of 404ing.

The unit summary is **Nawy-only** — Property Finder's listing carries no unit
rows. The response says so explicitly (`units_available_from: ["nawy"]`) rather
than letting an empty summary read as "this project has no units".

### GET /projects

```
?q=  &developer=  &zone=  &source=  &is_launch=  &min_price=  &max_price=
&delivery_year=  &sort=newest|price|name  &limit=50  &offset=0
```

`q` matches the project name, case-insensitively, as a substring. Returns the
rows a table needs plus a `total` for pagination. `limit` is capped at 200 so a
caller cannot ask for the whole catalogue in one response.

Every endpoint is dedup-scoped by default, consistent with the existing eight.

## Error handling

- Unknown project id → **404** with the id in the message.
- Bad query parameter (a `since` that will not parse, `limit` over the cap,
  `min_price` above `max_price`) → **422** naming the parameter. FastAPI gives
  most of this; the cross-field ones are explicit validators.
- Every route sits behind the existing API key dependency, like all data routes.

## Testing

- **`detect_price_changes`** — unit tested with hand-built snapshot lists: a
  move above and below the threshold; a spike that reverted; a single snapshot;
  an empty list; a change that is material but in the opposite direction to the
  latest step.
- **Routes** — `TestClient` with a stubbed session, following
  `tests/test_api/test_chat_route.py`. No database, no network.
- **Zone resolution** — a test proving a zone filter returns projects from both
  sources' spellings, which is the bug this fixes.
- **Live check** — after implementation, `/launches?since=30d` against the real
  catalogue, confirming new entrants appear and the count of snapshot runs is
  reported honestly.

## Out of scope

- `/feedback`, still blocked on a Slack app that does not exist.
- Unit-level insight endpoints (price-per-sqm by zone, unit mix, finishing).
  Genuinely valuable and entirely unexposed, but a separate spec.
- Trend endpoints beyond the feed — absorption velocity, new-entrant rate over
  time. They need months of snapshots.
- Any change to how prices are collected. The flicker is handled by the
  materiality rule here, not fixed at the source.
