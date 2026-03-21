# CountyIQ Implementation Guide

> **Purpose:** Step-by-step playbook for building CountyIQ from scratch. Hand this document + the architecture docs in `docs/` + the Data Source Feasibility Report to Claude Code and execute in order.
> **Author:** Jarod Daws
> **Created:** March 20, 2026
> **Companion docs:**
> - `docs/` (full architecture reference; see `docs/infrastructure/`, `docs/schema/`, `docs/pipelines/`, etc. for all design decisions, code samples, and Terraform modules)
> - `docs/data-source-feasibility.md` — Data source inventory (URLs, access methods, legal analysis, field inventories)

---

## How to Use This Document

**Phases 0–5 are sequential.** Each phase has prerequisites that must be true before starting. Do not skip ahead — dependencies will break.

**The Expansion Roadmap is modular.** After Phase 5, you have a working MVP. Expansion items can be tackled in any order, whenever you're ready.

**Every step has a verification checkpoint.** Don't move to the next step until the checkpoint passes. This prevents cascading failures.

---

## Table of Contents

### MVP Build
- [Phase 0: Local Environment Setup](#phase-0-local-environment-setup)
- [Phase 1: AWS Account Bootstrap & Terraform Infrastructure](#phase-1-aws-account-bootstrap--terraform-infrastructure)
- [Phase 2: Database Schema & Migrations](#phase-2-database-schema--migrations)
- [Phase 3: Dagster Pipelines & MVP Data Sources](#phase-3-dagster-pipelines--mvp-data-sources)
- [Phase 4: API, Frontend & Operations Stack](#phase-4-api-frontend--operations-stack)
- [Phase 5: CI/CD, Validation & Go-Live](#phase-5-cicd-validation--go-live)

### Expansion Roadmap
- [Expansion A: Phase 2 Data Sources](#expansion-a-phase-2-data-sources)
- [Expansion B: Phase 3 Data Sources](#expansion-b-phase-3-data-sources)
- [Expansion C: Platform Upgrades](#expansion-c-platform-upgrades)

---
