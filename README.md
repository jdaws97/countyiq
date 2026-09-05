# CountyIQ

CountyIQ is a York County real-estate intelligence platform for investors and
developers, built around three active surfaces:

- `frontend/`: React app for the feed, radar, map, municipality, search, property/entity/project case files, watch workspace, and operations views
- `api/`: FastAPI service serving `/api/*`
- `pipelines/`: Dagster pipelines for source ingestion plus the LLM-backed intelligence passes

Start here:

- [Current State](./docs/current-state.md)
- [Architecture Overview](./docs/architecture-overview.md)
- [Open Items](./docs/open-items.md)
- [Infrastructure](./docs/infrastructure.md)
- [Local Dev Rules](./AGENTS.md)

Current product and architecture docs live directly under `docs/` and its
named topic folders. Time-stamped source investigations live under
`docs/research/`; they are evidence, not runtime configuration or product
direction.
