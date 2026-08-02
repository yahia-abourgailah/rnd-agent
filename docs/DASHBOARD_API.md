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
| GET | `/insights/market-share` | Developer share by project count (`source`, `zone`, `dedup`, `limit`) |
| GET | `/insights/zones` | Per-zone activity, competition, launches, price range (`source`, `dedup`, `limit`) |
| GET | `/insights/price-distribution` | Project counts by price bracket (`source`, `dedup`) |
| GET | `/insights/property-mix` | Project counts by property type (`source`, `dedup`) |
| GET | `/insights/delivery-pipeline` | Projects by delivery year (`source`, `dedup`) |
| GET | `/insights/whitespace` | Zones ranked by opportunity score (`source`, `min_projects`, `dedup`, `limit`) |
| GET | `/insights/payment-terms` | Financing benchmark per developer (`source`, `min_projects`, `dedup`, `limit`) |
| GET | `/monitoring/quality` | Duplicate rate, source coverage, field completeness |

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
