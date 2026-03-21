# Schema Migrations (Alembic)

### What Alembic does

Alembic is a database migration tool for Python. Every time you need to change the database structure — add a table, add a column, rename something, change a data type — you create a migration file. Each file has two functions: `upgrade()` (apply the change) and `downgrade()` (reverse it). Alembic tracks which migrations have been applied and runs them in order.

### Why Alembic over raw SQL files

- **Reversible:** Every migration can be rolled back with `alembic downgrade -1`. If a migration breaks something, undo it instantly.
- **Automatic tracking:** Alembic maintains a `alembic_version` table in the database that records which migration was last applied. No manual bookkeeping.
- **LLM-friendly:** The structured `upgrade()`/`downgrade()` format gives LLMs a clear template to work within. You describe the change in English, the LLM generates the migration file.
- **Integrates with Dagster:** Migrations can be run as part of the Dagster pipeline startup or as a separate pre-deploy step.

### Project structure

```
york-county-pipelines/
├── alembic/
│   ├── alembic.ini              # Alembic configuration
│   ├── env.py                   # Migration environment (DB connection setup)
│   ├── script.py.mako           # Template for new migration files
│   └── versions/                # Migration files live here
│       ├── 001_initial_schema.py
│       ├── 002_add_parcels_table.py
│       ├── 003_add_assessment_table.py
│       └── ...
├── docker-compose.yml           # Local Postgres for testing
└── ...
```

### How a migration file looks

```python
"""Add permit_status column to permits table

Revision ID: a1b2c3d4e5f6
Revises: 9z8y7x6w5v4u
Create Date: 2026-04-15 14:30:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'a1b2c3d4e5f6'
down_revision = '9z8y7x6w5v4u'

def upgrade():
    op.add_column('permits',
        sa.Column('permit_status', sa.String(50), nullable=True),
        schema='public'
    )

def downgrade():
    op.drop_column('permits', 'permit_status', schema='public')
```

You don't need to write this yourself. You describe what you want ("add a permit_status column to the permits table") and the LLM generates the file. You review it — even without deep SQL knowledge you can see it's adding a column called `permit_status` to the `permits` table — and then run it.

### Common Alembic commands

| Command | What it does |
|---|---|
| `alembic upgrade head` | Apply all pending migrations (bring database up to date) |
| `alembic downgrade -1` | Undo the last migration |
| `alembic history` | Show all migrations and which have been applied |
| `alembic current` | Show which migration the database is currently at |
| `alembic revision -m "description"` | Create a new empty migration file |

### Testing migrations locally with Docker Postgres

Since RDS doesn't have a "branching" feature like Neon, you test migrations on a throwaway local Postgres database before applying them to production. This is the equivalent of Neon's branching — you get a fresh copy of the schema, test your migration, and throw it away if it breaks.

**`docker-compose.yml` (in your project root):**

```yaml
services:
  postgres-test:
    image: postgis/postgis:16-3.4
    environment:
      POSTGRES_DB: york_county_intel
      POSTGRES_USER: dagster_admin
      POSTGRES_PASSWORD: localtest
    ports:
      - "5433:5432"
    volumes:
      - pgdata-test:/var/lib/postgresql/data

volumes:
  pgdata-test:
```

This spins up a PostGIS-enabled Postgres 16 instance on your machine — identical to RDS in every way that matters for migrations.

### Migration testing workflow

Here's what the process looks like end-to-end when you need to make a schema change:

**Step 1: Start local Postgres**
```bash
docker compose up -d postgres-test
```

**Step 2: Bring local database up to current state**
```bash
# Point Alembic at the local database
export DATABASE_URL="postgresql://dagster_admin:localtest@localhost:5433/york_county_intel"
alembic upgrade head
```

**Step 3: Create and test the new migration**
```bash
# Generate a new migration file (or have an LLM write one)
alembic revision -m "add permit_status column"

# Edit the generated file (or paste in LLM-generated code)
# Then apply it to the local database
alembic upgrade head

# Verify it worked
psql -h localhost -p 5433 -U dagster_admin -d york_county_intel \
  -c "\d public.permits"

# Test the rollback too
alembic downgrade -1

# Re-apply if rollback worked cleanly
alembic upgrade head
```

**Step 4: Apply to production (RDS)**
```bash
# Point Alembic at production (via Session Manager port forward)
# In terminal 1:
aws ssm start-session \
  --target <instance-id> \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters '{"host":["<rds-endpoint>"],"portNumber":["5432"],"localPortNumber":["5434"]}'

# In terminal 2:
export DATABASE_URL="postgresql://dagster_admin:<password>@localhost:5434/york_county_intel"
alembic upgrade head
```

**Step 5: Clean up local test database**
```bash
docker compose down -v    # -v removes the volume (fresh start next time)
```

### Alembic environment configuration (`env.py`)

The `env.py` file reads the database connection from an environment variable, so the same Alembic configuration works against both local Docker Postgres and production RDS — you just change the `DATABASE_URL`:

| Environment | DATABASE_URL |
|---|---|
| Local testing | `postgresql://dagster_admin:localtest@localhost:5433/york_county_intel` |
| Production (via port forward) | `postgresql://dagster_admin:<password>@localhost:5434/york_county_intel` |
| On EC2 (direct) | `postgresql://dagster_admin:<password>@<rds-endpoint>:5432/york_county_intel` |

### Migration naming convention

Migrations are auto-numbered by Alembic using revision IDs (hex hashes). For readability, always include a descriptive message:

```
001_initial_schema.py              # Base tables, extensions, schemas
002_add_parcels_table.py           # Parcel polygons + attributes
003_add_assessment_table.py        # Assessment/tax data
004_add_owners_table.py            # Owner entities from deeds
005_add_spatial_indexes.py         # GiST indexes on geometry columns
...
```

### Integration with deployment

When you deploy new pipeline code to the EC2 instance, the deployment process should include:

```bash
# After pulling new code
cd /opt/york-county/pipelines
git pull origin main

# Run any pending migrations
alembic upgrade head

# Restart Dagster
sudo systemctl restart dagster-webserver
sudo systemctl restart dagster-daemon
```

This ensures the database schema is always in sync with the pipeline code. If a pipeline expects a new column, the migration that adds that column runs before the pipeline does.

---
