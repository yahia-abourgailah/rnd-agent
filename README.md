# Competitive Launch Intelligence System

Automated pipeline for The Address Investments that monitors competitor
real-estate project launches across Egyptian sources, extracts structured
data, deduplicates the same launch reported by multiple sources, stores it,
and notifies the R&D team with source links.

## Pipeline stages

```
Watch → Extract → Dedup → Store → Notify
```

Each stage is a self-contained module under `src/launch_intel/`. Stages
communicate **only** through the shared Pydantic models in
`src/launch_intel/models/`. Detection and extraction are deliberately
separate: `watch/change_detector.py` cheaply detects whether a page changed;
`extract/extractor.py` (an expensive LLM call) only runs on content that did.

## Phase status

This repo currently implements **Phase 1**: shared contracts + one working
end-to-end extraction path (crawl → detect change → extract → log JSON).
No dedup, no DB persistence, no Slack notifications yet — those stages exist
as stubs with `TODO(phase-later)` markers so the second developer has a
structure to build against without breaking imports.

| Stage    | Status                                             |
|----------|-----------------------------------------------------|
| models   | ✅ implemented — the shared contract                 |
| watch    | ✅ fetcher, change_detector, base adapter + 1 adapter |
| extract  | ✅ Instructor-based extractor + prompts               |
| pipeline | ✅ thin Prefect flow wiring watch → extract           |
| dedup    | 🚧 stubbed only                                       |
| db       | 🚧 stubbed only                                       |
| notify   | 🚧 stubbed only                                       |
| feedback | 🚧 stubbed only                                       |
| metrics  | 🚧 stubbed only                                       |
| api      | 🚧 stubbed only (health check works)                  |

## Getting started

```bash
cp .env.example .env        # fill in OPENAI_API_KEY at minimum
make dev                    # installs deps + playwright browser
make up                     # starts postgres+pgvector, redis (not required for Phase 1 flow)
make test
make crawl SOURCE=generic_developer_demo
```

## Adding a source

1. Write an adapter in `src/launch_intel/watch/adapters/your_source.py`
   implementing `BaseAdapter` (see `watch/base.py`).
2. Register it in `watch/adapters/__init__.py`.
3. Add one entry to `config/sources.yaml` pointing `adapter_name` at it.

## Shared contract

See `src/launch_intel/models/launch.py` for the canonical `Launch` schema.
**Do not change these models without syncing with the other developer** —
the dedup/notify side is built directly against this contract.
