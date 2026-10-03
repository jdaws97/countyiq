# CountyIQ

CountyIQ is a York County real-estate intelligence platform for investors and
developers, built around three active surfaces:

- `frontend/`: React app for the feed, radar, map, municipality, search, property/entity/project case files, watch workspace, and operations views
- `api/`: FastAPI service serving `/api/*`
- `pipelines/`: manually invoked local Dagster jobs for source ingestion and intelligence passes

Start here:

- [Current State](./docs/current-state.md)
- [Architecture Overview](./docs/architecture-overview.md)
- [Open Items](./docs/open-items.md)
- [Infrastructure](./docs/infrastructure.md)
- [Local Pipeline Commands](./docs/operations/local-pipelines.md)
- [Local Dev Rules](./AGENTS.md)

Current product and architecture docs live directly under `docs/` and its
named topic folders. Time-stamped source investigations live under
`docs/research/`; they are evidence, not runtime configuration or product
direction.
