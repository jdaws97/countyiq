# CountyIQ

CountyIQ is a York County civic intelligence platform built around three active surfaces:

- `frontend/`: React app for search, map, radar, owners, parcels, and operations views
- `api/`: FastAPI service serving `/api/*`
- `pipelines/`: Dagster pipelines for source ingestion plus the LLM-backed intelligence passes

Start here:

- [Current State](./docs/current-state.md)
- [Architecture Overview](./docs/architecture-overview.md)
- [Open Items](./docs/open-items.md)
- [Infrastructure](./docs/infrastructure.md)
- [Local Dev Rules](./AGENTS.md)

Historical plans, drafts, and older monolith docs live under `archives/` and are no longer the source of truth for day-to-day work.
