# Quick Reference: File Inventory

When the MVP is complete, your repository should contain:

```
countyiq/
├── .github/
│   └── workflows/
│       ├── ci.yml                          # PR checks (lint, type check, tests)
│       └── deploy.yml                      # Build Docker images, push to GHCR (Watchtower auto-pulls on VPS)
│
├── docker/
│   ├── docker-compose.yml                  # Production services: postgres, dagster, api, caddy, watchtower
│   ├── docker-compose.dev.yml              # Local dev overrides
│   ├── Caddyfile                           # Reverse proxy config
│   ├── .env.example                        # Environment variable template
│   ├── backup.sh                           # pg_dump → R2 backup script
│   └── setup.sh                            # Initial VPS provisioning
│
├── pipelines/
│   ├── pyproject.toml                      # Dependencies (dagster, playwright, etc.)
│   ├── setup.py                            # Package installation
│   ├── docker-compose.yml                  # Local Postgres for testing
│   │
│   ├── alembic/                            # Schema migrations
│   │   ├── alembic.ini
│   │   ├── env.py
│   │   └── versions/
│   │       └── 001_initial_schema.py
│   │
│   ├── countyiq/                        # Main Python package (Dagster code location)
│   │   ├── __init__.py
│   │   ├── definitions.py                  # Dagster top-level definitions
│   │   │
│   │   ├── resources/                      # Shared connections
│   │   │   ├── database.py                 # Postgres connection (psycopg2)
│   │   │   └── storage.py                  # R2/S3-compatible client for raw archival
│   │   │
│   │   ├── assets/                         # Data assets by source type
│   │   │   ├── arcgis/                     # Sources 1, 5, 13
│   │   │   ├── bulk/                       # Sources 2 (flood), 4 (PA Open Data)
│   │   │   ├── scrapers/                   # Source 3 (Assessment)
│   │   │   └── enrichment/                 # Entity resolution, vector tiles
│   │   │
│   │   ├── jobs/                           # Job definitions
│   │   ├── schedules/                      # Cron schedule definitions
│   │   ├── sensors/                        # Alerting + enrichment trigger sensors
│   │   │
│   │   └── lib/                            # Shared utilities
│   │       ├── arcgis_client.py            # ArcGIS REST API pagination
│   │       ├── playwright_utils.py         # Browser session management
│   │       ├── s3_archive.py               # Raw response archival
│   │       ├── slack.py                    # 3-channel Slack webhook helper
│   │       ├── scd.py                      # SCD Type 2 upsert helper
│   │       └── parsers/                    # Per-source parsing functions
│   │
│   └── tests/                              # Pipeline tests (outside package)
│       ├── conftest.py
│       ├── fixtures/
│       └── test_*.py
│
├── api/
│   ├── main.py                             # FastAPI app
│   ├── Dockerfile                          # Container image for production
│   ├── requirements.txt                    # Python dependencies
│   ├── routes/
│   │   ├── parcels.py                     # /api/parcels endpoints
│   │   ├── owners.py                      # /api/owners endpoints
│   │   ├── search.py                      # /api/search endpoints
│   │   └── ops.py                         # /api/ops/health endpoint
│   └── lib/
│       ├── database.py                    # Postgres connection (env var pattern)
│       └── schemas.py                     # Pydantic response models
│
├── frontend/
│   ├── package.json
│   ├── vite.config.js
│   ├── index.html
│   └── src/
│       ├── App.jsx                        # Router + layout
│       ├── components/
│       │   ├── Map.jsx                    # MapLibre + Deck.gl
│       │   ├── SearchBar.jsx
│       │   ├── ParcelDetail.jsx
│       │   ├── OwnerDetail.jsx
│       │   └── OpsHealth.jsx
│       └── lib/
│           └── api.js                     # API client helper
│
├── .gitignore
└── README.md
```
