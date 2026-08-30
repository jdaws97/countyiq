# CountyIQ — Codex Instructions

## Start Every Task

1. Invoke the `countyiq` skill before any repository action. Let the skill route
   you to the minimum necessary docs; do not preload broad context.
2. Classify the request as read-only, diagnosis, implementation, or monitoring.
   Do not turn review/diagnosis into an implementation without user authority.
3. Preserve the dirty worktree. Treat existing changes as user-owned and never
   revert or overwrite them.
4. For multi-step work, keep a short live plan. Before completion, run fresh,
   relevant verification and report the actual results.

## Token-Efficient Orchestration

The primary agent is the chief of staff: it owns scope, risk, architecture,
integration, and the final answer. Delegation is optional, not the default.

Delegate only when the task is independently useful, has a narrow boundary and
an objective acceptance oracle, and is likely to save more primary-agent tokens
than the handoff plus verification will consume. Use direct tools for simple
searches, file reads, commands, and test runs; do not spawn an agent merely to
operate a tool.

- **Luna (`gpt-5.6-luna`, low):** atomic, mechanically checkable work. Give it
  exact input files, at most one concern, a fixed output schema, and normally no
  more than three owned files. Good fits: bounded extraction from named files,
  a one-file change with existing tests, fixture normalization, or a precisely
  specified repetitive edit. Never use Luna for open-ended discovery, schema or
  migration design, security, architecture, ambiguous debugging, or final
  judgment.
- **Terra (`gpt-5.6-terra`, low by default; medium only for real synthesis):**
  repository discovery, dependency/data-flow mapping, failure triage, scoped
  implementation, and checklist-based review. Give it bounded questions and
  require file/line or command evidence. Prefer one well-scoped Terra discovery
  over several overlapping agents.
- **Primary/root (usually Sol):** ambiguous or cross-cutting work, task
  decomposition, database/schema migrations, identity/entity-resolution logic,
  security/privacy, destructive operations, LLM prompt/eval policy, integration,
  and acceptance decisions.

Use `fork_turns="none"` and pass a compact self-contained brief unless a small
number of recent turns is essential. Default to at most two children and no
nested delegation. Parallelize only genuinely independent workstreams.

When a delegation candidate exists, read `docs/operations/agent-orchestration.md`
before spawning. It defines the compact task packet, dirty-file ownership,
receipts, verification ladder, eval ledger, and trust gate. The primary agent
must rerun the cheapest oracle and verify scope; a child's confidence or another
agent's agreement is not verification. Keep judgment-only and high-risk work at
the primary, and record material delegated outcomes so trust remains empirical.

## Local Execution

The mandatory `countyiq` skill is the canonical source for architecture routing
and project invariants; do not duplicate its context in child prompts.

- Use `uv`, never `pip` or `venv`; use Python 3.11 and never bare `python`.
- Pipelines: `cd pipelines`; use `.venv/bin/python`. Run
  `-m pytest tests/ -q -k "not integration"` and the definitions import smoke test
  for wiring changes.
- API: `api/.venv/bin/python -m pytest api/tests -v` against `postgres-test`.
- Frontend: `npx tsc -b && npm run lint`; add `npm run build` when bundling may
  be affected.
- Database: from `pipelines`, start `docker compose up -d postgres-test`; a new
  volume runs the ordered `init-db/*.sql` scripts automatically before
  `alembic upgrade head`. Use `docker compose down -v` only for an intended
  reset.
- Consult current primary docs (Context7 when available) before coding against
  an external library. Inspect live scraper targets and meaningful frontend work
  with Playwright.
