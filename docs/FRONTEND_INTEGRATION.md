# Frontend Integration Guide

How to wire the CRM dashboard to the Launch Intelligence API.

**Who owns what:** we own the data, the collectors and these endpoints. You own
the screens. Everything here is read-only JSON except `POST /chat`.

For the field-by-field reference of every endpoint, see
[`DASHBOARD_API.md`](DASHBOARD_API.md). This document covers the things you need
to decide *before* writing components: where the key lives, what the types are,
what the errors mean, and which numbers are safe to put in front of a client.

---

## 1. Environments

| | Base URL |
|---|---|
| Production | `https://<fill-in>` |
| Local (ours) | `http://127.0.0.1:8000` |

Interactive Swagger is at `<base>/docs` and the machine-readable spec at
`<base>/openapi.json`. **Generate your client from `openapi.json`** rather than
hand-writing request code — the types in section 4 are there to read, not to
retype.

Put the base URL in an environment variable. Do not hardcode it; the host will
change at least once.

---

## 2. Authentication — the key never reaches the browser

Every endpoint except `GET /health` requires a shared secret in the `X-API-Key`
header.

```http
GET /insights/market-share?limit=5
X-API-Key: <the key>
```

The key is a single shared secret with no per-user scoping and no expiry. Anything
shipped to the browser is readable by anyone who opens devtools, so **the key
must live on your server only**:

```
Browser (user session)  →  your Next.js/CRM backend (holds the key)  →  this API
```

In Next.js that is a route handler or server action — an environment variable
*without* the `NEXT_PUBLIC_` prefix, so the bundler cannot leak it:

```ts
// app/api/intel/[...path]/route.ts
export async function GET(req: Request, { params }: { params: { path: string[] } }) {
  const url = new URL(req.url)
  const target = `${process.env.INTEL_API_URL}/${params.path.join('/')}${url.search}`

  const upstream = await fetch(target, {
    headers: { 'X-API-Key': process.env.INTEL_API_KEY! },
    next: { revalidate: 300 },
  })

  return new Response(upstream.body, {
    status: upstream.status,
    headers: { 'content-type': 'application/json' },
  })
}
```

Your components then call `/api/intel/insights/zones` and never see the key.

> **CORS is currently open to all origins.** That is a development setting. It
> makes calling us straight from the browser *work*, which is exactly the trap —
> it works right up until the key is scraped from your bundle. Use the proxy.
> We will restrict `allow_origins` to your domain before the API is public.

Wrong or missing key → `401 {"detail":"Invalid or missing API key"}`.

---

## 3. Conventions that apply everywhere

**Money.** All amounts are **EGP**. `min_price` is a *starting* price — the
cheapest unit currently listed — not an average and not a fixed price. Label it
"from EGP X" in the UI. `currency` is returned per project; today it is always
`"EGP"`, but read it rather than assuming.

**Deduplication.** Nawy and Property Finder both list roughly 20% of the same
projects. Every endpoint takes `dedup` and defaults to `true`, which counts each
real project once. **Leave it alone** unless you are building a per-source
comparison — `dedup=false` double-counts and will not reconcile against any other
screen.

**Nulls mean unknown, not zero.** A project with `min_price: null` has no
published price; it is not free. Never coerce to `0` — it sorts to the top of a
cheapest-first list and reads as a real number. Render "—" or "Price on request".
Field coverage is in `/monitoring/quality`: today **59% of projects have a price**
and **66% have a delivery date**.

**Timestamps** are ISO 8601 in **UTC** (trailing `Z`). Convert for display; Egypt
is UTC+2/+3.

**Pagination.** `/launches` and `/projects` take `limit` (max 200, default 50)
and `offset`, and return `total`. Nothing else paginates — the insight endpoints
take `limit` only and are already aggregated to a chartable size.

**Ids are UUID strings.** Treat them as opaque.

---

## 4. Types

Copy these into your codebase, or generate the equivalent from `openapi.json`.

```ts
// ---- shared ----
export type Source = 'nawy' | 'property_finder'

// ---- GET /projects ----
export interface ProjectRow {
  project_id: string
  name: string
  developer: string | null
  zone: string | null
  source: Source
  min_price: number | null
  currency: string | null
  property_types: string[]
  is_launch: boolean
  delivery_date: string | null   // "2027" or "2027-Q3"
  first_seen_at: string          // ISO UTC
}

export interface ProjectsResponse {
  total: number
  limit: number
  offset: number
  results: ProjectRow[]
}

// ---- GET /projects/{id} ----
export interface UnitSummary {
  count: number
  min_price: number | null
  max_price: number | null
  price_per_sqm_min: number | null
  price_per_sqm_max: number | null
  bedrooms: Record<string, number>        // "0" is a studio, not missing
  property_types: Record<string, number>
  finishing: Record<string, number>
}

export interface PriceSnapshot {
  snapshot_at: string
  min_price: number | null
  max_price: number | null
  total_units: number | null
}

export interface ProjectDetail {
  project: ProjectRow
  requested_id: string | null      // set when you asked for a duplicate's id
  units_available_from: Source[]
  units: UnitSummary
  price_history: PriceSnapshot[]
  also_listed_on: Source[]
}

// ---- GET /launches ----
export interface LaunchEvent {
  kind: 'new' | 'price_change'
  project_id: string
  name: string
  developer: string | null
  zone: string | null
  source: Source
  occurred_at: string
  min_price: number | null   // 'new' only
  from_price: number | null  // 'price_change' only
  to_price: number | null    // 'price_change' only
  change_pct: number | null  // 'price_change' only
}

export interface LaunchesResponse {
  since: string
  min_change_pct: number
  snapshot_runs_in_window: number
  total: number
  results: LaunchEvent[]
}

// ---- GET /insights/* ----
export interface ZoneRow {
  zone: string
  city: string | null
  projects: number
  developers: number
  launches: number
  min_price: number | null
  median_price: number | null
  max_price: number | null
}

export interface MarketShareRow {
  developer_id: string
  developer: string
  projects: number
  market_share_pct: number
}

export interface WhitespaceRow {
  zone: string
  city: string | null
  projects: number
  developers: number
  median_price: number | null
  competition: 'low' | 'medium' | 'high'
  opportunity_score: number   // 0..1
}

export interface PaymentTermsRow {
  developer: string
  projects: number
  avg_down_payment_pct: number | null
  avg_installment_years: number | null
}

// ---- POST /chat ----
export interface ChatRequest {
  message: string               // 1..2000 chars
  conversation_id?: string
}

export interface ChatResponse {
  reply: string
  conversation_id: string
}
```

`LaunchEvent` is a discriminated union in practice — narrow on `kind` before
reading the price fields:

```ts
if (event.kind === 'price_change') {
  // from_price, to_price, change_pct are populated
}
```

---

## 5. Errors

Every failure returns `{"detail": "<message>"}`. The `detail` string is written
for a developer, not an end user — log it, don't render it.

| Status | Means | What the UI should do |
|---|---|---|
| `401` | Missing or wrong API key | Not a user error. Alert your team — the deployment is misconfigured. |
| `404` | No project with that id | "Project not found." |
| `422` | Invalid parameter — bad `since`, malformed id, `min_price` above `max_price` | Fix the request. Surface as a form validation message. |
| `500` | Our bug | Retry once, then show a generic failure. Tell us. |
| `502` / `504` | `/chat` only — the assistant failed or gave up | See section 8. |
| `503` | `/chat` only — the assistant is not loaded | Hide or disable the chat entry point. |

A `503` on `/chat` does **not** mean the API is down. The chat agent is
deliberately isolated: if it fails to start, every other endpoint keeps serving.
Degrade the chat panel independently rather than blocking the dashboard.

---

## 6. Screen recipes

### Overview dashboard

Five parallel calls, all cacheable for ~5 minutes — the underlying data changes
only when a collection run finishes.

| Widget | Call | Shape |
|---|---|---|
| Top developers | `/insights/market-share?limit=10` | Horizontal bar |
| Zone activity | `/insights/zones?limit=15` | Table or map |
| Price spread | `/insights/price-distribution` | Histogram (5 fixed brackets, always in order) |
| Supply pipeline | `/insights/delivery-pipeline` | Column chart by year |
| Opportunity | `/insights/whitespace?min_projects=5&limit=10` | Ranked table |

Each response's `results` array maps straight onto a chart series.

Two of these need a caveat in the UI, not just in this document:

- **`whitespace.opportunity_score`** is a heuristic — 60% low-competition, 40%
  price level. It has no demand signal in it, because absorption velocity needs
  snapshot history we are still accumulating. Ship it as "zones worth a look",
  never as a ranking of where to invest. The response carries a `note` field
  saying so; show it.
- **`payment-terms`** is derived from whatever each source publishes. Only Nawy
  exposes installment years, so `avg_installment_years` is `null` for a
  Property-Finder-only developer. That is missing data, not a zero-year plan.

### Change feed

```
GET /launches?since=7d&min_change_pct=5&limit=50
```

**Read `snapshot_runs_in_window` before rendering an empty state.** Price
movement is only detectable across two or more collection runs. If that number is
`0` or `1`, an empty feed means *not enough history yet* — say that, not "no
activity", which is a different and much more alarming claim to put in front of a
client.

Current honest state of this feed: the catalogue was rebuilt on **6 Aug 2026**, so
every project shares that `first_seen_at`. **Any window reaching back to 6 August
reports all ~2,666 projects as `new`.** Only a handful are genuinely newer.
Default your UI to `since=7d` and it behaves sensibly from mid-August onward.
Price movement is likewise thin today — a few projects have moved at all — and
thickens as snapshot history accumulates.

Group the feed by `kind`: "New this week" and "Price changes" read far better as
two lists than one interleaved stream.

### Search and detail

`/projects` for the list, `/projects/{id}` for the drill-down. Debounce `q` by
~300ms; it is a substring match on the name.

Three details that will otherwise bite:

- **`requested_id`** is non-null when the id you requested was a duplicate that
  resolved to a canonical project. A link built from any source's id lands
  somewhere useful instead of 404ing. If it is set, consider a quiet
  "showing the merged record" note.
- **`units_available_from: []`** means *no source publishes unit-level data for
  this project* — not that it has no units. Only Nawy contributes units today.
  Hide the unit panel; don't render "0 units".
- **`bedrooms` counts from zero.** The key `"0"` is a studio. A truthiness check
  will silently drop every studio from the mix chart.

`price_history` is ordered oldest-first and is ready to plot as a line. It will
often have one point — one point is not a trend line; render a value, not a
chart.

---

## 7. Filters

`source` (`nawy` | `property_finder`) and `zone` are accepted by most endpoints.

Zone names come from `/insights/zones` — use that to populate a dropdown rather
than typing names, because sources spell them differently. The filter accepts
either the canonical name or a source's variant, so `New Cairo` and
`New Cairo City` both return the same rows.

> **Zone figures changed on 2026-08-09.** Each source's spelling of a zone was
> previously reported as its own row, splitting every per-zone number. New Cairo
> went 383 → **523**, El Sheikh Zayed 156 → **266**. The response shape did not
> change; the old numbers were undercounting. A chart keyed on zone name now has
> fewer, larger bars.

---

## 8. Chat

```http
POST /chat
X-API-Key: <key>

{"message": "which developers launched in New Cairo this month?"}
```

Response: `{"reply": "...", "conversation_id": "..."}`.

Omit `conversation_id` on the first message; **echo the returned value back on
every follow-up** or each turn starts a fresh conversation with no memory. Store
it per chat session on your side.

The reply is plain prose. There is no streaming — a request takes **several
seconds** because the assistant writes SQL, runs it, and reads the result before
answering. Show a typing indicator and set a client timeout of at least 60s.

Failure modes are distinct and worth handling separately:

- **`504`** — the assistant looped without converging. Suggest a narrower
  question; the same question retried verbatim will usually fail again.
- **`502`** — it crashed. Retrying is reasonable.
- **`503`** — the agent did not load at all. Disable the chat UI.

The assistant queries a **read-only** database role, so no message can modify
data. It can still be wrong — treat replies as a research aid, not as a
figure to forward to a client unchecked.

---

## 9. Known limits — read before demoing

- **Two sources live:** Nawy and Property Finder. Bayut and Aqarmap are not
  connected. Anything labelled "the market" means those two.
- **Primary and off-plan only.** Resale is deliberately excluded, so unit counts
  are lower than a public portal's and are not comparable to one.
- **Collection is not yet scheduled.** Runs are triggered manually today, so
  `first_seen_at` and price history advance in steps, not continuously. The
  change feed is only as fresh as the last run.
- **Duplicate rate is ~16% for projects and ~26% for developers** — that is what
  dedup is removing. `/monitoring/quality` reports it live; it is a useful
  internal health panel and a bad thing to show a client.
- **No per-user auth, no rate limiting.** One shared key, unthrottled. Cache on
  your side and don't fan out a request per table row.

## 10. Questions

`<base>/docs` answers most shape questions faster than we can. For anything
about *what a number means* — dedup, price semantics, coverage — ask us; those
are judgement calls baked into the queries, not documented in the schema.
