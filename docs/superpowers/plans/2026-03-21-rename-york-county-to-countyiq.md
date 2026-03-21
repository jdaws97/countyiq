# Rename york_county to countyiq — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the Python package from `york_county` to `countyiq` and standardize all York-specific platform naming to `countyiq` across the entire repo.

**Architecture:** Mechanical search-and-replace organized by file category: pipeline package first (directory rename + import rewrite), then infra defaults, Terraform, docs, and CLAUDE.md/SKILL.md. Each task produces a self-contained commit. Verification after each batch.

**Tech Stack:** git mv, sed/grep, uv, pytest, Alembic, Docker Compose

**Spec:** `docs/superpowers/specs/2026-03-21-rename-york-county-to-countyiq-design.md`

---

## File Map

| Category | Files | Action |
|----------|-------|--------|
| Python package | 23 files in `pipelines/york_county/` | `git mv` directory to `pipelines/countyiq/` |
| Pipeline imports | ~15 `.py` files under `pipelines/` | Replace `york_county` → `countyiq` in imports |
| Pipeline config | `pyproject.toml`, `alembic.ini`, `docker-compose.yml` | Replace names/defaults |
| Pipeline resources | `database.py`, `storage.py`, `slack.py` | Replace defaults/SSM paths |
| Test files | 5 test `.py` files | Replace imports + DB name defaults |
| Terraform | 15 `.tf` files + 1 `.sh` file | Replace all `york-county-*`, `york_county_intel`, `YorkCounty/EC2`, SSM paths |
| Docs | 39 `.md` files | Replace all platform naming patterns |
| CLAUDE.md | 1 file at repo root | Replace all references |
| SKILL.md | 2 files (`.claude/` and `.agents/`) | Replace all references |

---

### Task 1: Rename Python package directory

- [ ] **Step 1: Rename the directory**

```bash
cd /home/jdaws/countyiq
git mv pipelines/york_county pipelines/countyiq
```

- [ ] **Step 2: Update all imports in the package itself**

Every `.py` file under `pipelines/countyiq/` that imports from `york_county` needs updating. Run:

```bash
cd /home/jdaws/countyiq
find pipelines/countyiq -name "*.py" -exec sed -i 's/from york_county/from countyiq/g; s/import york_county/import countyiq/g' {} +
```

Files affected:
- `pipelines/countyiq/definitions.py`
- `pipelines/countyiq/assets/arcgis/parcels.py`
- `pipelines/countyiq/assets/bulk/plcb.py`
- `pipelines/countyiq/schedules/__init__.py`
- `pipelines/countyiq/sensors/alerting.py`

- [ ] **Step 3: Update all imports in test files**

```bash
find pipelines/tests -name "*.py" -exec sed -i 's/from york_county/from countyiq/g; s/import york_county/import countyiq/g' {} +
```

Files affected:
- `pipelines/tests/test_parcels_parser.py`
- `pipelines/tests/test_parcels_integration.py`
- `pipelines/tests/test_plcb_parser.py`
- `pipelines/tests/test_plcb_integration.py`
- `pipelines/tests/test_county_config.py`

- [ ] **Step 4: Update pyproject.toml**

In `pipelines/pyproject.toml`:
- Line 2: `name = "york-county-pipelines"` → `name = "countyiq"`
- Line 48: `include = ["york_county*"]` → `include = ["countyiq*"]`

- [ ] **Step 5: Reinstall the package**

```bash
cd /home/jdaws/countyiq/pipelines
uv pip install -e ".[dev]"
```

- [ ] **Step 6: Verify import**

```bash
cd /home/jdaws/countyiq/pipelines
uv run python -c "from countyiq.definitions import defs; print('OK')"
```

Expected: `OK`

- [ ] **Step 7: Commit**

```bash
cd /home/jdaws/countyiq
git add -A
git commit -m "refactor: rename Python package york_county → countyiq"
```

---

### Task 2: Update pipeline infrastructure defaults

- [ ] **Step 1: Update database.py defaults**

In `pipelines/countyiq/resources/database.py`:
- Docstring: `york_county_intel database` → `countyiq database`
- Line 63: `"york_county_intel"` → `"countyiq"`

- [ ] **Step 2: Update storage.py defaults**

In `pipelines/countyiq/resources/storage.py`:
- Docstring line 12: `s3://york-county-raw/` → `s3://countyiq-raw/`
- Line 16: `bucket: str = "york-county-raw"` → `bucket: str = "countyiq-raw"`
- Line 48: `"york-county-raw"` → `"countyiq-raw"`

- [ ] **Step 3: Update slack.py SSM paths**

In `pipelines/countyiq/lib/slack.py`:
- Docstring lines 8-10: `/york-county/slack-webhook-*` → `/countyiq/slack-webhook-*`
- Lines 21-23: all three SSM param paths `/york-county/` → `/countyiq/`

- [ ] **Step 4: Update docker-compose.yml**

In `pipelines/docker-compose.yml`:
- Line 5: `POSTGRES_DB: york_county_intel` → `POSTGRES_DB: countyiq`

- [ ] **Step 5: Update alembic.ini**

In `pipelines/alembic.ini`:
- Line 4: `york_county_intel` → `countyiq` (in the connection string)

- [ ] **Step 6: Update test DB connection defaults**

In `pipelines/tests/test_plcb_integration.py`:
- Lines 14, 39: `dbname="york_county_intel"` → `dbname="countyiq"` (appears in `_pg_available` and `test_plcb_parser_to_staging`)

In `pipelines/tests/test_parcels_integration.py`:
- Line 21: `"york_county_intel"` → `"countyiq"` (DATABASE_NAME default)

- [ ] **Step 7: Recreate Docker Postgres with new DB name and verify tests**

```bash
cd /home/jdaws/countyiq/pipelines
docker compose down -v
docker compose up -d postgres-test
sleep 3
DATABASE_URL="postgresql://dagster_admin:localtest@localhost:5433/countyiq" uv run alembic upgrade head
uv run pytest tests/ -v
```

Expected: All tests pass.

- [ ] **Step 8: Commit**

```bash
cd /home/jdaws/countyiq
git add -A
git commit -m "refactor: update pipeline defaults york-county → countyiq"
```

---

### Task 3: Update Terraform files

Apply all substitution rules to every `.tf` and `.sh` file under `infra/`. Order matters — most specific patterns first.

- [ ] **Step 1: Run substitutions**

```bash
cd /home/jdaws/countyiq

# Ordered most-specific first
find infra -type f \( -name "*.tf" -o -name "*.sh" \) -exec sed -i \
  -e 's/york-county-terraform-state/countyiq-terraform-state/g' \
  -e 's/york-county-terraform-locks/countyiq-terraform-locks/g' \
  -e 's/york-county-frontend/countyiq-frontend/g' \
  -e 's/york-county-tiles/countyiq-tiles/g' \
  -e 's/york-county-raw/countyiq-raw/g' \
  -e 's/york-county-intel/countyiq/g' \
  -e 's/york_county_intel/countyiq/g' \
  -e 's/york-county-api-keepalive/countyiq-api-keepalive/g' \
  -e 's/york-county-api-lambda/countyiq-api-lambda/g' \
  -e 's/york-county-api/countyiq-api/g' \
  -e 's/york-county-dagster-health/countyiq-dagster-health/g' \
  -e 's/york-county-dagster/countyiq-dagster/g' \
  -e 's/york-county-github-actions/countyiq-github-actions/g' \
  -e 's/york-county-deploy-policy/countyiq-deploy-policy/g' \
  -e 's/york-county-instance-status/countyiq-instance-status/g' \
  -e 's/york-county-high-cpu/countyiq-high-cpu/g' \
  -e 's/york-county-high-memory/countyiq-high-memory/g' \
  -e 's/york-county-high-disk/countyiq-high-disk/g' \
  -e 's/york-county-monthly/countyiq-monthly/g' \
  -e 's/york-county-alerts/countyiq-alerts/g' \
  -e 's|YorkCounty/EC2|CountyIQ/EC2|g' \
  -e 's|/opt/york-county|/opt/countyiq|g' \
  -e 's|/york-county/rds-|/countyiq/rds-|g' \
  -e 's|/york-county/slack-webhook|/countyiq/slack-webhook|g' \
  -e 's|/york-county/dagster|/countyiq/dagster|g' \
  -e 's|/york-county/system|/countyiq/system|g' \
  -e 's/york-county/countyiq/g' \
  {} +
```

- [ ] **Step 2: Verify no york references remain**

```bash
grep -rni "york.county" --include="*.tf" --include="*.sh" infra/
```

Expected: Zero matches.

- [ ] **Step 3: Commit**

```bash
cd /home/jdaws/countyiq
git add infra/
git commit -m "refactor: rename Terraform resources york-county → countyiq"
```

---

### Task 4: Update docs

Apply the same substitution rules to all markdown files in `docs/` (excluding `docs/superpowers/plans/`).

- [ ] **Step 1: Run substitutions on docs**

```bash
cd /home/jdaws/countyiq

find docs -name "*.md" -not -path "docs/superpowers/plans/*" -exec sed -i \
  -e 's/york-county-terraform-state/countyiq-terraform-state/g' \
  -e 's/york-county-terraform-locks/countyiq-terraform-locks/g' \
  -e 's/york-county-frontend/countyiq-frontend/g' \
  -e 's/york-county-tiles/countyiq-tiles/g' \
  -e 's/york-county-raw/countyiq-raw/g' \
  -e 's/york-county-intel/countyiq/g' \
  -e 's/york_county_intel/countyiq/g' \
  -e 's/york-county-api-keepalive/countyiq-api-keepalive/g' \
  -e 's/york-county-api-lambda/countyiq-api-lambda/g' \
  -e 's/york-county-api/countyiq-api/g' \
  -e 's/york-county-dagster-health/countyiq-dagster-health/g' \
  -e 's/york-county-dagster/countyiq-dagster/g' \
  -e 's/york-county-github-actions/countyiq-github-actions/g' \
  -e 's/york-county-deploy-policy/countyiq-deploy-policy/g' \
  -e 's/york-county-instance-status/countyiq-instance-status/g' \
  -e 's/york-county-high-cpu/countyiq-high-cpu/g' \
  -e 's/york-county-high-memory/countyiq-high-memory/g' \
  -e 's/york-county-high-disk/countyiq-high-disk/g' \
  -e 's/york-county-monthly/countyiq-monthly/g' \
  -e 's/york-county-alerts/countyiq-alerts/g' \
  -e 's|YorkCounty/EC2|CountyIQ/EC2|g' \
  -e 's|/opt/york-county|/opt/countyiq|g' \
  -e 's|/york-county/rds-|/countyiq/rds-|g' \
  -e 's|/york-county/slack-webhook|/countyiq/slack-webhook|g' \
  -e 's|/york-county/dagster|/countyiq/dagster|g' \
  -e 's|/york-county/system|/countyiq/system|g' \
  -e 's/york_county/countyiq/g' \
  -e 's/york-county/countyiq/g' \
  {} +
```

- [ ] **Step 2: Verify — only York County data references remain**

```bash
grep -rni "york" docs/ --include="*.md" | grep -v "superpowers/plans/" | grep -v "York County" | grep -v "yorkcountypa.gov" | head -20
```

Expected: Zero matches (only "York County" as a proper noun and York-specific URLs should remain).

- [ ] **Step 3: Commit**

```bash
cd /home/jdaws/countyiq
git add docs/
git commit -m "docs: rename york-county → countyiq across all architecture docs"
```

---

### Task 5: Update CLAUDE.md and SKILL.md

- [ ] **Step 1: Run substitutions on CLAUDE.md**

```bash
cd /home/jdaws/countyiq

sed -i \
  -e 's/york-county-frontend/countyiq-frontend/g' \
  -e 's/york-county-tiles/countyiq-tiles/g' \
  -e 's/york-county-raw/countyiq-raw/g' \
  -e 's/york_county_intel/countyiq/g' \
  -e 's|/opt/york-county|/opt/countyiq|g' \
  -e 's|/york-county/slack-webhook|/countyiq/slack-webhook|g' \
  -e 's/york_county/countyiq/g' \
  -e 's/york-county/countyiq/g' \
  CLAUDE.md
```

- [ ] **Step 2: Run substitutions on both SKILL.md files**

```bash
cd /home/jdaws/countyiq

for f in .claude/skills/countyiq/SKILL.md .agents/skills/countyiq/SKILL.md; do
  sed -i \
    -e 's/york-county-frontend/countyiq-frontend/g' \
    -e 's/york-county-tiles/countyiq-tiles/g' \
    -e 's/york-county-raw/countyiq-raw/g' \
    -e 's/york_county_intel/countyiq/g' \
    -e 's|/opt/york-county|/opt/countyiq|g' \
    -e 's|/york-county/slack-webhook|/countyiq/slack-webhook|g' \
    -e 's/york_county/countyiq/g' \
    -e 's/york-county/countyiq/g' \
    "$f"
done
```

- [ ] **Step 3: Verify CLAUDE.md is clean**

```bash
grep -ni "york" CLAUDE.md | grep -v "York County"
```

Expected: Zero matches.

- [ ] **Step 4: Verify SKILL.md files are clean**

```bash
grep -ni "york" .claude/skills/countyiq/SKILL.md | grep -v "York County" | grep -v "yorkcountypa.gov"
grep -ni "york" .agents/skills/countyiq/SKILL.md | grep -v "York County" | grep -v "yorkcountypa.gov"
```

Expected: Zero matches (only "York County" as proper noun and York-specific data source URLs remain).

- [ ] **Step 5: Commit**

```bash
cd /home/jdaws/countyiq
git add CLAUDE.md .claude/ .agents/
git commit -m "docs: rename york-county → countyiq in CLAUDE.md and SKILL.md"
```

---

### Task 6: Final verification

- [ ] **Step 1: Full import + test verification**

```bash
cd /home/jdaws/countyiq/pipelines
uv run python -c "from countyiq.definitions import defs; print('OK')"
uv run pytest tests/ -v
```

Expected: Import OK, all tests pass.

- [ ] **Step 2: Repo-wide audit**

```bash
cd /home/jdaws/countyiq

echo "=== Pipeline code (should be 0) ==="
grep -rn "york_county" --include="*.py" pipelines/ | grep -v county_config | grep -v fixtures/ | grep -v "York County" | grep -v old_docs | wc -l

echo "=== Terraform (should be 0) ==="
grep -rni "york.county" --include="*.tf" --include="*.sh" infra/ | wc -l

echo "=== DB name (should be 0) ==="
grep -rn "york_county_intel" . --include="*.py" --include="*.md" --include="*.tf" --include="*.ini" --include="*.yml" --include="*.toml" --include="*.sh" | grep -v old_docs/ | grep -v superpowers/plans/ | wc -l

echo "=== Docs platform names (should be 0) ==="
grep -rni "york" docs/ --include="*.md" | grep -v "superpowers/plans/" | grep -v "York County" | grep -v "yorkcountypa.gov" | wc -l

echo "=== CLAUDE.md (should be 0) ==="
grep -ni "york" CLAUDE.md | grep -v "York County" | wc -l
```

Expected: All counts are 0.

- [ ] **Step 3: Final commit (if any stragglers found and fixed)**

```bash
cd /home/jdaws/countyiq
git add -A
git commit -m "refactor: final cleanup — rename york-county → countyiq complete"
```
