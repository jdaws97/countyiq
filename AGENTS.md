# CountyIQ - Codex Instructions

## Working Agreement

1. Use the `countyiq` skill when architecture context will materially improve
   the work: cross-cutting implementation or diagnosis, schema/migrations,
   deployment, county ingestion, entity resolution, or LLM pipeline changes.
   Skip it for meta-review, status checks, simple lookups, and trivial edits.
2. Keep the user's requested mode: read-only, diagnosis, implementation, or
   monitoring. Do not turn review or diagnosis into an implementation.
3. Preserve the dirty worktree. Existing changes are user-owned; never revert
   or overwrite unrelated work.
4. Inspect the relevant code and tests first. Load only the documentation needed
   to resolve architecture, intent, or uncertainty.
5. Treat project invariants as defaults, not a reason to avoid analysis. When
   the user explicitly reopens a decision, evaluate the alternatives on their
   merits and identify the migration cost.
6. Finish authorized work in the requested mode. Reuse prior authorization,
   make reasonable assumptions for routine choices, and ask only for missing
   information or permission that blocks progress.
7. User instructions override repository and skill defaults within higher-priority
   instructions and runtime permissions. If a rule requires a pause, cite its
   exact source and wording and explain why prior authorization is insufficient.

## Delegation

Prefer direct tools for searches, reads, commands, and tests. Delegate bounded,
independent work with an objective acceptance check when it saves time or effort
after handoff, review, and integration. Before delegating, read
`docs/operations/agent-orchestration.md`; default to at most two children and no
nested delegation. The primary agent retains architecture, security, schema,
identity, LLM-policy, integration, and final acceptance decisions, and reruns the
cheapest relevant check. Do not copy broad repository context into child briefs.

## Local Execution

- Write human-readable code with clear names and conventional multiline layout,
  including tests and scripts. Avoid compressed statements and dense one-liners.
  Follow `docs/operations/code-style.md` and run the relevant formatter before
  finishing code changes.
- Use `uv`, Python 3.11, and project virtual environments; never use bare
  `python`, `pip`, or create ad hoc virtual environments.
- Run the relevant required checks below and report actual results. Start narrow;
  broaden or repeat only for new changes, failures, or unresolved risks. Avoid
  tests that merely mirror the implementation.
- Pipelines: work from `pipelines/` with `.venv/bin/python`. For Dagster wiring
  changes, run the definitions import smoke test; for broad pipeline changes,
  run `-m pytest tests/ -q -m "not integration"`.
- API: use `api/.venv/bin/python`; database-dependent tests run against
  `postgres-test`.
- Frontend: for TypeScript application changes run `npx tsc -b` and
  `npm run lint`; add `npm run build` when bundling may be affected.
- Customer UI: read `docs/frontend/customer-experience.md` before changing
  navigation, page composition, investigation content, or evidence presentation.
  Preserve its customer journeys and shared components; document intentional
  changes to that direction and verify the affected journey in a real browser.
- Database: from `pipelines/`, use `docker compose up -d postgres-test`. A new
  volume runs ordered `init-db/*.sql` before `alembic upgrade head`. Use
  `docker compose down -v` only for an explicitly intended reset.
- Consult current primary documentation when an external library's version or
  behavior is uncertain. Use Playwright for browser-visible behavior, layout,
  interaction changes, and live scraper behavior - not every frontend edit.
