# CountyIQ Implementation Guide

> **Purpose:** Step-by-step playbook for building CountyIQ from scratch. Hand this document + the architecture docs in `docs/` + the Data Source Feasibility Report to Claude Code and execute in order.
> **Author:** Jarod Daws
> **Created:** March 20, 2026
> **Companion docs:**
> - `docs/` (full architecture reference; see `docs/infrastructure.md`, `docs/schema/`, `docs/pipelines/`, etc. for all design decisions and code samples)
> - `docs/data-source-feasibility.md` — Data source inventory (URLs, access methods, legal analysis, field inventories)

---

## How to Use This Document

**Build and verify locally first, deploy to production second.** The entire application stack — Dagster pipelines, FastAPI API, React frontend — runs on your local machine against Docker Postgres before deploying to the VPS. The phase order reflects this:

| Phase | Environment | What's verified |
|---|---|---|
| 0 | Local | Tools installed, repo scaffolded |
| 1 | Local + Hetzner VPS | VPS provisioned, Docker Compose ready, Cloudflare configured |
| 2 | Local Docker Postgres | Schema migrations work, upgrade/downgrade cycle passes |
| 3 | Local Docker Postgres + live APIs | Pipelines fetch real data, SCD2 upserts work, tests pass |
| 4 | Local Docker Postgres + localhost servers | API serves data, frontend renders map, Playwright screenshots confirm UI |
| 5 | **Production VPS** | Docker Compose deploy, GHCR + Watchtower, Cloudflare Pages, go-live |

**Verify locally before deploying to the VPS.** Everything runs against Docker Postgres on `localhost:5433`, FastAPI on `localhost:8000`, and Vite dev server on `localhost:5173`.

**The Expansion Roadmap is modular.** After Phase 5, you have a working MVP. Expansion items can be tackled in any order, whenever you're ready.

**Every step has a verification checkpoint.** Don't move to the next step until the checkpoint passes. This prevents cascading failures.

---

## Tooling Available During Implementation

The following MCP tools are available to Claude Code during implementation. Reference the right tool for each task type.

| Tool | When to use | Phase |
|---|---|---|
| **Context7** (`context7`) | Before writing code that uses Dagster, FastAPI, Alembic, MapLibre, Deck.gl, or any external library. Pulls current API docs to avoid deprecated patterns (e.g., Dagster API changes between versions). | All phases |
| **Playwright MCP** (`playwright`) | Before writing any Playwright scraper: navigate the live site, inspect DOM, test selectors, take screenshots. During frontend development: visually verify components render correctly on localhost and after Cloudflare Pages deploy. | Phase 3 (scrapers), Phase 4 (frontend) |
| **Frontend Design** (`frontend-design`) | When building React components, pages, or UI layouts. Produces distinctive, production-grade interfaces. Use for each major frontend view (Map, Search, Property Detail, Ops Health). | Phase 4 (frontend) |
| **Superpowers: Planning** | Before starting any phase or major step. Write an implementation plan, identify risks, and get alignment. | All phases |
| **Superpowers: Code Review** | After completing a major step (e.g., a full source asset with tests). Review against the plan and coding standards. | All phases |
| **Superpowers: Dispatching Parallel Agents** | When building independent source assets (e.g., FEMA + PA Open Data can be built in parallel). | Phase 3 |

---

## Table of Contents

### MVP Build
- [Phase 0: Local Environment Setup](#phase-0-local-environment-setup)
- [Phase 1: Hetzner VPS & Cloudflare Setup](#phase-1-hetzner-vps--cloudflare-setup)
- [Phase 2: Database Schema & Migrations](#phase-2-database-schema--migrations)
- [Phase 3: Dagster Pipelines & MVP Data Sources](#phase-3-dagster-pipelines--mvp-data-sources)
- [Phase 4: API, Frontend & Operations Stack](#phase-4-api-frontend--operations-stack)
- [Phase 5: GHCR, Watchtower, Cloudflare Pages & Go-Live](#phase-5-ghcr-watchtower-cloudflare-pages--go-live)

### Expansion Roadmap
- [Expansion A: Phase 2 Data Sources](#expansion-a-phase-2-data-sources)
- [Expansion B: Phase 3 Data Sources](#expansion-b-phase-3-data-sources)
- [Expansion C: Platform Upgrades](#expansion-c-platform-upgrades)

---
