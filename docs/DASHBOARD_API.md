# Dashboard API — reference for the frontend team

The R&D competitive-intelligence data, served as read-only JSON endpoints. The
full-stack team builds the CRM dashboard (React/Next.js) with charts against
these — **we own the data + API, you own the screens.**

## Running it

```bash
# from the repo root, with the venv active and Postgres up
python -m uvicorn api.main:app --port 8000
```

- **Base URL (local dev):** `http://127.0.0.1:8000`
- **Interactive docs (Swagger):** `http://127.0.0.1:8000/docs` — try every endpoint in the browser
- **OpenAPI spec:** `http://127.0.0.1:8000/openapi.json` — you can auto-generate a typed API client from this
- **CORS:** enabled for all origins (dev), so a browser app on any localhost port can call it.

## Changed 2026-08-09 — zones are now real zones

`/insights/zones` and `/insights/whitespace` previously reported **each source's
spelling of a zone as its own row**. Nawy's "New Cairo" and Property Finder's
"New Cairo City" are one place, and were counted as two.

They are now resolved to a single canonical zone. The figures grew:

| Zone | Was | Now |
|---|---|---|
| New Cairo | 383 | **523** |
| El Sheikh Zayed | 156 | **266** |
| New Capital City | 262 | **320** |
| Ras El Hekma | 147 | **180** |

Nothing about the response *shape* changed — only the numbers, which were
previously undercounting. Duplicate zone rows have disappeared, so a chart keyed
on zone name will have fewer, larger bars.

`?zone=` filters accept either spelling, so an existing call using an old zone
name still returns rows.

## Authentication

Every data endpoint requires an **API key**, sent as the `X-API-Key` header.
`/health` is the only open endpoint.

```
GET /insights/market-share?limit=5
X-API-Key: <the shared key>
```

- The key is configured on our side via the `API_KEY` env var. Ask us for the value.
- **Keep the key in your CRM backend, not in browser/React code** — anything in the
  browser is publicly readable. The secure flow is:
  `React (user session) → your CRM backend (holds the key) → this API`.
- No key / wrong key → `401 {"detail":"Invalid or missing API key"}`.

(Locally, if `API_KEY` is unset the check is skipped for convenience — but any
shared/deployed instance will have it set.)

## Common query parameters
- `source` — `nawy` or `property_finder`. Omit for the combined market.
- `dedup` — `true` (default) counts unique deduped projects; `false` gives raw per-source rows (with cross-source duplicates).
- `limit` — cap the number of rows returned.

## Endpoints

| Method | Path | Returns |
|---|---|---|
| GET | `/health` | `{"status":"ok"}` — liveness check |
| GET | `/launches` | **Change feed** — what appeared and what moved (`since`, `min_change_pct`, `source`, `zone`, `developer`, `limit`, `offset`) |
| GET | `/projects` | Search (`q`, `developer`, `zone`, `source`, `is_launch`, `min_price`, `max_price`, `delivery_year`, `sort`, `limit`, `offset`) |
| GET | `/projects/{id}` | One project in full: unit rollup, price history, other sources listing it |
| GET | `/insights/market-share` | Developer share by project count (`source`, `zone`, `dedup`, `limit`) |
| GET | `/insights/zones` | Per-zone activity, competition, launches, price range (`source`, `dedup`, `limit`) |
| GET | `/insights/price-distribution` | Project counts by price bracket (`source`, `dedup`) |
| GET | `/insights/property-mix` | Project counts by property type (`source`, `dedup`) |
| GET | `/insights/delivery-pipeline` | Projects by delivery year (`source`, `dedup`) |
| GET | `/insights/whitespace` | Zones ranked by opportunity score (`source`, `min_projects`, `dedup`, `limit`) |
| GET | `/insights/payment-terms` | Financing benchmark per developer (`source`, `min_projects`, `dedup`, `limit`) |
| GET | `/monitoring/quality` | Duplicate rate, source coverage + overlap, field completeness |
| POST | `/chat` | Ask a question in natural language (`message`, `conversation_id`) |

## Example

Request:
```
GET /insights/market-share?limit=3
```

Response:
```json
{
  "source": null,
  "zone": null,
  "total_projects": 2520,
  "developer_count": 623,
  "results": [
    { "developer_id": "612a5ed2-…", "developer": "Palm Hills Developments", "projects": 83, "market_share_pct": 3.29 },
    { "developer_id": "c61f03c1-…", "developer": "Mountain View", "projects": 65, "market_share_pct": 2.58 },
    { "developer_id": "4520fb8a-…", "developer": "SODIC", "projects": 63, "market_share_pct": 2.50 }
  ]
}
```

Suggested charts: market-share → bar/pie; zones → table or map; price-distribution
→ histogram; delivery-pipeline → column chart by year; whitespace → ranked table;
payment-terms → sorted bar. Each endpoint's `results` array maps directly to a chart series.

## Notes / limits
- **Prices are EGP; starting price** (`min_price`) unless stated.
- **Two sources live:** Nawy and Property Finder. `source_id` provenance is normalised.
- **Deduped by default** so combined numbers don't double-count the ~20% of projects both sources list.
- **Auth:** API-key required on all data endpoints (see Authentication above).

## `GET /launches` — what changed

The change feed: projects that appeared, and prices that moved enough to mean
something.

```
GET /launches?since=7d&min_change_pct=5&zone=New Cairo&limit=50
X-API-Key: <key>
```

| Parameter | Default | Notes |
|---|---|---|
| `since` | `7d` | `7d`, `30d`, or an ISO date. Anything else is a 422. |
| `min_change_pct` | `5` | A price move below this is treated as inventory noise. |
| `source`, `zone`, `developer` | — | Filters |
| `limit`, `offset` | 50 / 0 | `limit` caps at 200 |

Each result is an **event**, newest first. `kind` is `new` or `price_change`,
and decides which optional fields are set:

```json
{
  "since": "2026-08-02T09:00:00Z",
  "min_change_pct": 5.0,
  "snapshot_runs_in_window": 4,
  "total": 12,
  "results": [
    {"kind": "new", "project_id": "…", "name": "Southmed", "developer": "TMG",
     "zone": "Al Dabaa", "source": "nawy",
     "occurred_at": "2026-08-08T…", "min_price": 6000000.0},
    {"kind": "price_change", "project_id": "…", "name": "Perla",
     "occurred_at": "2026-08-09T…",
     "from_price": 6000000.0, "to_price": 7200000.0, "change_pct": 20.0}
  ]
}
```

**Read `snapshot_runs_in_window` before concluding nothing moved.** Price
movement needs at least two collection runs inside the window. If that number is
0 or 1, an empty feed means "not enough history yet", not "nothing happened".
The history only accumulates going forward.

Prices from these sources shift as inventory sells, so a raw delta would fire
constantly. A move is reported only when it clears `min_change_pct` **and** is
still heading the same way at the latest observation — a spike that already
reverted stays quiet.

A project that appeared inside the window reports only as `new`: its first
observed price is not a change from anything.

## `GET /projects` — search

```
GET /projects?q=palm&zone=New Cairo&is_launch=true&sort=newest&limit=50
```

Filters: `q` (name contains), `developer`, `zone`, `source`, `is_launch`,
`min_price`, `max_price`, `delivery_year` (`YYYY`).
`sort`: `newest` | `price` | `name`. `limit` caps at 200.
`min_price` above `max_price` is a 422.

Returns `{total, limit, offset, results: [...]}`. Deduplicated by default, so a
project reported by several sources appears once.

## `GET /projects/{id}` — detail

Everything known about one project: the project, a unit rollup, its price
history, and which other sources list it.

```json
{
  "project": {"project_id": "…", "name": "New Garden City", "developer": "City Edge Developments",
              "zone": "New Capital City", "source": "nawy", "min_price": 3633000.0, "…": "…"},
  "requested_id": null,
  "units_available_from": ["nawy"],
  "units": {"count": 94, "min_price": 3633000.0, "max_price": 43319000.0,
            "price_per_sqm_min": 41563.0, "price_per_sqm_max": 216595.0,
            "bedrooms": {"0": 15, "1": 9, "2": 24, "3": 45, "4": 1},
            "property_types": {"apartment": 80, "commercial": 14},
            "finishing": {"finished": 80, "not_finished": 14}},
  "price_history": [{"snapshot_at": "…", "min_price": 3633000.0, "max_price": 43319000.0, "total_units": 94}],
  "also_listed_on": ["property_finder"]
}
```

Three things worth knowing:

- **`units_available_from`** names the sources that actually contribute unit
  rows. Only Nawy does today — Property Finder's listing has no per-unit data.
  An empty `units` block with `units_available_from: []` means *no source
  publishes units for this project*, not that the project has none.
- **`bedrooms` counts from zero.** A studio is `"0"`, not a missing value.
- **`requested_id`** is set when you asked for a *duplicate's* id. The `project`
  returned is the canonical row it resolves to, so a link built from any
  source's id lands somewhere useful rather than 404ing.

Unknown id → 404. Malformed id → 422.
