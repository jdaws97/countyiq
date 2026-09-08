# Agent Orchestration

This document expands the compact policy in `AGENTS.md`. It is intentionally
not required reading for ordinary tasks. Read it when delegating, changing the
policy, or interpreting the agent metrics.

## Objective

Apply the delegation rules in `AGENTS.md`. Judge a handoff by completion time,
total effort across agents, and verification quality. Parallel work may be
worthwhile even when it consumes more tokens; token savings alone do not decide
whether to delegate.

## Routing

| Route | Default effort | Use it for | Do not use it for |
|---|---:|---|---|
| Direct tools | n/a | Search, inventory generation, reading, commands, tests | Semantic synthesis |
| Luna | low | One concern, named inputs, fixed output, deterministic oracle | Broad discovery, ambiguity, high-risk decisions |
| Terra | low | Discovery from a precomputed inventory, data-flow maps, failure triage, scoped implementation | Final architecture or acceptance authority |
| Terra | medium | Multi-file synthesis that low effort has failed or evals show benefits from | Routine extraction |
| Primary/root | task-dependent | Scope, architecture, migrations, security, integration, final judgment | Mechanical bulk work with a strong oracle |

### Hard routing boundaries

Keep these with the primary agent unless the child is only collecting bounded
evidence:

- Alembic and destructive/data-loss-sensitive changes
- PIDN, owner identity, entity resolution, and cross-schema semantics
- authentication, secrets, permissions, privacy, and external side effects
- CountyIQ LLM prompt policy, eval thresholds, and model selection
- changes spanning pipeline, API, and frontend contracts
- acceptance of work that has no independent oracle

## Delegation Packet

Every child gets these fields, stated once:

1. **Goal:** one observable outcome.
2. **Owned scope:** exact files or exact read-only boundary.
3. **Inputs:** relevant paths, symbols, commands, or a precomputed inventory.
4. **Constraints:** CountyIQ invariants and prohibited actions relevant to this task.
5. **Deliverable:** compact schema and output limit. Never request pasted files.
6. **Oracle:** exact command or evidence rule that decides pass/fail.
7. **Stop condition:** when to return `blocked` instead of expanding scope.

Use `fork_turns="none"` for model-overridden agents and send this packet directly.
Avoid repeating repo history. Ask for at most 1,200 output tokens from Luna and
2,000 from Terra unless the artifact itself requires more.

For edits, snapshot the worktree first. Assign non-overlapping files to children.
An already-dirty file remains primary-owned unless its starting hash/diff is
recorded and one child receives exclusive ownership.

## Verification Ladder

Classify the oracle before spawning the child.

### A — Deterministic

Examples: focused tests, compiler/typechecker, schema validation, exact query
result, parser fixture assertion, or a strict structural checker.

The primary reruns the cheapest oracle and verifies changed-path scope. For a
low-risk change, those passes replace line-by-line review. Historical trust is
useful for routing but is not required for acceptance.

### B — Sampled

Examples: discovery completeness, refactor behavior with partial tests, or docs
whose facts span several sources.

Verify a machine-generated inventory or sample the most consequential claims,
then inspect only risk-relevant hunks. Skip broader review only when the
model/task-class metrics are `trusted`.

### C — Judgment-only

Examples: architecture quality, migration safety, identity semantics, security,
and UX/product tradeoffs.

Keep the decision with the primary agent. A child may gather evidence or offer a
bounded critique, but its agreement is not verification.

## Metrics and Trust Gate

`.agents/orchestration/runs.jsonl` stores one JSON object per material delegated
run. Record code-writing delegations, explicit calibration runs, and new failure
modes; do not log trivial read-only help unless it is part of an eval.

Every record includes `work_kind`, `changed_files`, and `pre_run_verdict`.
Code-writing runs must name their changed files and pass a regression check.
Sampled work performed while its model/task class is on `probation` or
`suspended` requires full primary review; only a pre-run `trusted` verdict permits
targeted review. Timestamps must be timezone-aware RFC 3339 values and ledger
order must be chronological.

Run:

```bash
pipelines/.venv/bin/python .agents/orchestration/agent_metrics.py validate
pipelines/.venv/bin/python .agents/orchestration/agent_metrics.py report
pipelines/.venv/bin/python .agents/orchestration/agent_metrics.py gate --model luna --task-class atomic_change
```

The report groups by model and task class and measures:

- verified pass rate and 95% Wilson lower bound
- false-claim, scope-failure, rework, and escaped-defect rates
- acceptance without full review
- median output size
- median estimated token savings when token fields are available

Trust thresholds and the rolling window are defined in
`.agents/orchestration/policy.json`; use the `gate` command for the verdict.
Change thresholds only after an eval demonstrates a better quality/cost tradeoff.

Trust is scoped to a **model plus task class**. Luna succeeding at exact-file
extraction does not qualify it for repository discovery. Any escaped defect or
repeated false success claim suspends expansion until new calibration passes.

Token fields are optional because the desktop runtime may not expose per-child
usage. When available, estimate savings as:

```text
root_solo_estimate - agent_prompt - agent_output - root_verification
```

Never substitute output brevity for correctness. Missing token data affects the
efficiency column, not the quality gate.

## Calibration Set

`eval_cases.json` is a compact set of CountyIQ-shaped routing cases. Re-run
representative cases after model, prompt, tool, or policy changes. Compare the
same case and oracle across configurations. The initial live calibration is in
`runs.jsonl`: Terra passed bounded repository discovery; Luna met its formatting
contract but missed workflow evidence, demonstrating that syntactic compliance
alone is not a completeness oracle.
