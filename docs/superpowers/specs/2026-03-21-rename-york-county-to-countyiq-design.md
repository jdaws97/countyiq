# Rename countyiq to countyiq — Design Spec

**Goal:** Standardize all naming from York-County-specific to the generic `countyiq` convention across the entire repo, so future multi-county expansion doesn't carry confusing legacy names.

**Motivation:** The Python package, S3 buckets, DB name, SSM paths, EC2 paths, Terraform tags, AWS resource names, and 200+ doc references all say "countyiq" or "countyiq". This is misleading as the platform scales to additional counties. Fixing it now with ~60 files is manageable; fixing it later with 200+ files is painful.

**Principle:** If a name refers to the *platform* (infrastructure, code, resources), it should say `countyiq`. If a name refers to *York County data specifically* (config entries, fixture data, data source URLs), it stays as-is.

---

## Scope

### In scope — rename these

**Pipeline Python package:**
- Directory: `pipelines/countyiq/` → `pipelines/countyiq/`
- All `from countyiq.*` imports → `from countyiq.*` (every `.py` file that imports from the package, including tests)
- `pyproject.toml`: name `countyiq-pipelines` → `countyiq`, include `countyiq*` → `countyiq*`
- `uv.lock`: auto-regenerated when `pyproject.toml` changes — do NOT manually edit

**Infrastructure defaults in pipeline code:**
- S3 bucket defaults: `countyiq-raw` → `countyiq-raw`
- Database name default: `countyiq` → `countyiq`
- Slack SSM paths: `/countyiq/slack-webhook-*` → `/countyiq/slack-webhook-*`
- `docker-compose.yml`: `POSTGRES_DB: countyiq` → `POSTGRES_DB: countyiq`
- `alembic.ini`: connection string `countyiq` → `countyiq`

**Test files (imports and connection defaults only):**
- `test_plcb_integration.py`, `test_parcels_integration.py`: `from countyiq.*` → `from countyiq.*`, `dbname="countyiq"` → `dbname="countyiq"`
- `test_county_config.py`, `test_parcels_parser.py`, `test_plcb_parser.py`: `from countyiq.*` → `from countyiq.*`

**CLAUDE.md:** Apply all substitution rules. Update every path, connection string, bucket name, SSM path, env var, and Dagster entry point (`-m countyiq.definitions` → `-m countyiq.definitions`).

**SKILL.md** (both `.claude/skills/countyiq/SKILL.md` and `.agents/skills/countyiq/SKILL.md`): Apply all substitution rules — same treatment as CLAUDE.md.

**Terraform (13+ files in `infra/`):**
- Project tags: `countyiq` → `countyiq` (everywhere)
- Terraform variable default: `countyiq` → `countyiq`
- S3 bucket names: `countyiq-frontend` → `countyiq-frontend`, `countyiq-tiles` → `countyiq-tiles`, `countyiq-raw` → `countyiq-raw`
- State backend: `countyiq-terraform-state` → `countyiq-terraform-state`, `countyiq-terraform-locks` → `countyiq-terraform-locks`
- Lambda function/resources: `countyiq-api` → `countyiq-api`, `countyiq-api-lambda` → `countyiq-api-lambda`, `countyiq-api-keepalive` → `countyiq-api-keepalive`
- EC2/Dagster resources: `countyiq-dagster` → `countyiq-dagster`
- IAM resources: `countyiq-github-actions` → `countyiq-github-actions`, `countyiq-deploy-policy` → `countyiq-deploy-policy`
- Monitoring resources: `countyiq-alerts` → `countyiq-alerts`, `countyiq-monthly` → `countyiq-monthly`, `countyiq-high-cpu` → `countyiq-high-cpu`, `countyiq-high-memory` → `countyiq-high-memory`, `countyiq-high-disk` → `countyiq-high-disk`, `countyiq-instance-status` → `countyiq-instance-status`, `countyiq-dagster-health` → `countyiq-dagster-health`
- CloudWatch namespace: `CountyIQ/EC2` → `CountyIQ/EC2`
- EC2 paths: `/opt/countyiq` → `/opt/countyiq`
- SSM parameters: `/countyiq/rds-*` → `/countyiq/rds-*`
- CloudWatch log groups: `/countyiq/dagster` → `/countyiq/dagster`, `/countyiq/system` → `/countyiq/system`
- No `terraform apply` — code changes only.

**Docs (30+ markdown files, ~200 references):** Apply all substitution rules across `docs/**/*.md`.

### Out of scope — do NOT change

- `county_config.py` York data entries — the `"york"` key, `name="York County"`, `plcb_filter="York County"`, `assessment_url="https://assessmentpublic.yorkcountypa.gov/"`, `s3_prefix="york"` are county-specific data, not platform naming
- Test fixture content — real York County CSV rows (`.csv`), JSON data (`.json`), PA addresses (e.g. "YORK PA 17401")
- Test function names that describe behavior — `test_parse_filters_to_countyiq`, `test_york_config_exists`, etc.
- Test assertions that validate York config — `assert config.name == "York County"`
- The `COUNTY` env var default value `"york"` in `county_config.py` — this is the config key, not a naming convention
- `docs/superpowers/plans/` files — historical records of past work
- `old_docs/` directory — legacy files, left as-is
- Alembic migration file comments (e.g. `# Source 1: York County GIS Portal`) — migration files are immutable historical records

---

## Substitution Rules

Ordered by specificity (most specific first to avoid partial matches). Apply all rules to all in-scope files.

| # | Pattern | Replacement | Notes |
|---|---------|-------------|-------|
| 1 | `countyiq-terraform-state` | `countyiq-terraform-state` | S3 state bucket |
| 2 | `countyiq-terraform-locks` | `countyiq-terraform-locks` | DynamoDB lock table |
| 3 | `countyiq-frontend` | `countyiq-frontend` | S3 + CloudFront |
| 4 | `countyiq-tiles` | `countyiq-tiles` | S3 tiles bucket |
| 5 | `countyiq-raw` | `countyiq-raw` | S3 raw archive bucket |
| 6 | `countyiq` | `countyiq` | Terraform Project tag, variable default |
| 7 | `countyiq` | `countyiq` | DB name (underscore variant) |
| 8 | `countyiq-api-keepalive` | `countyiq-api-keepalive` | CloudWatch rule |
| 9 | `countyiq-api-lambda` | `countyiq-api-lambda` | Lambda layer |
| 10 | `countyiq-api` | `countyiq-api` | Lambda function, IAM, API Gateway |
| 11 | `countyiq-dagster-health` | `countyiq-dagster-health` | CloudWatch alarm |
| 12 | `countyiq-dagster` | `countyiq-dagster` | EC2 instance name |
| 13 | `countyiq-github-actions` | `countyiq-github-actions` | IAM role |
| 14 | `countyiq-deploy-policy` | `countyiq-deploy-policy` | IAM policy |
| 15 | `countyiq-instance-status` | `countyiq-instance-status` | CloudWatch alarm |
| 16 | `countyiq-high-cpu` | `countyiq-high-cpu` | CloudWatch alarm |
| 17 | `countyiq-high-memory` | `countyiq-high-memory` | CloudWatch alarm |
| 18 | `countyiq-high-disk` | `countyiq-high-disk` | CloudWatch alarm |
| 19 | `countyiq-monthly` | `countyiq-monthly` | Billing alarm |
| 20 | `countyiq-alerts` | `countyiq-alerts` | SNS topic |
| 21 | `CountyIQ/EC2` | `CountyIQ/EC2` | CloudWatch custom metric namespace |
| 22 | `/opt/countyiq` | `/opt/countyiq` | EC2 filesystem paths |
| 23 | `/countyiq/rds-` | `/countyiq/rds-` | SSM Parameter Store (DB creds) |
| 24 | `/countyiq/slack-webhook` | `/countyiq/slack-webhook` | SSM Parameter Store (Slack) |
| 25 | `/countyiq/dagster` | `/countyiq/dagster` | CloudWatch log group |
| 26 | `/countyiq/system` | `/countyiq/system` | CloudWatch log group |
| 27 | `countyiq` | `countyiq` | Python package/imports |
| 28 | `countyiq` | `countyiq` | Catch-all for remaining |

**Context-sensitive exclusions:** Rules 27-28 must NOT match inside:
- `county_config.py` data entries (the `"york"` key and its values)
- Test fixture files (`.csv`, `.json`)
- Test assertion strings that validate county config values (e.g. `assert config.name == "York County"`)
- `old_docs/` directory
- `docs/superpowers/plans/` directory
- Alembic migration version file comments

---

## Verification

After all renames:

1. **Import check:** `cd pipelines && uv run python -c "from countyiq.definitions import defs; print('OK')"` passes
2. **Tests pass:** `docker compose down -v && docker compose up -d postgres-test` (new DB name), then `DATABASE_URL="postgresql://dagster_admin:localtest@localhost:5433/countyiq" uv run alembic upgrade head`, then `uv run pytest tests/ -v` — all pass
3. **Pipeline code clean:** `grep -rni "countyiq" --include="*.py" pipelines/ | grep -v county_config | grep -v fixtures/ | grep -v "York County"` returns zero matches
4. **Terraform clean:** `grep -rni "york.county" --include="*.tf" --include="*.sh" infra/` returns zero matches (case-insensitive catches `YorkCounty` too)
5. **DB name gone:** `grep -rn "countyiq" . --include="*.py" --include="*.md" --include="*.tf" --include="*.ini" --include="*.yml" --include="*.toml" --include="*.sh" | grep -v old_docs/ | grep -v superpowers/plans/` returns zero matches
6. **Docs clean:** `grep -rni "york.county" docs/ | grep -v superpowers/plans/ | grep -v "York County"` returns only references to the actual county (data source descriptions, not platform names)
7. **CLAUDE.md clean:** `grep -ni "york" CLAUDE.md` returns zero matches except where "York County" appears as a data description (e.g. "building for York County PA")

---

## Risk

- **Low risk:** This is a rename, not a behavior change. All functionality is preserved.
- **Docker Postgres:** The local DB name changes from `countyiq` to `countyiq`. Existing containers need `docker compose down -v && docker compose up -d` to recreate with the new name.
- **Terraform state:** The Terraform state backend bucket name changes in code, but since we haven't run `terraform apply` yet (Phase 5), there's no existing state to migrate.
- **uv.lock:** Auto-regenerated when `pyproject.toml` changes. Do not manually edit.
