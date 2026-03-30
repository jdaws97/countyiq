# Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                   Cloudflare                         │
│  DNS + CDN + DDoS + WAF (free tier)                 │
│                                                      │
│  /* (default) ──→ Cloudflare Pages (React SPA)      │
│  /tiles/*     ──→ Cloudflare R2 (vector tiles)      │
│  /api/*       ──→ Hetzner VPS (proxied)             │
└──────────────────────┬──────────────────────────────┘
                       │ HTTPS
┌──────────────────────▼──────────────────────────────┐
│            Hetzner VPS (Docker Compose)              │
│                                                      │
│  ┌──────────┐  ┌───────────┐  ┌──────────────────┐  │
│  │  Caddy   │  │  FastAPI   │  │     Dagster      │  │
│  │  :80/443 ├──▶  :8000    │  │  webserver+daemon │  │
│  └──────────┘  └─────┬─────┘  └────────┬─────────┘  │
│                      │                  │            │
│                ┌─────▼──────────────────▼─────┐     │
│                │  PostgreSQL 16 + PostGIS      │     │
│                │  :5432 (internal only)        │     │
│                └──────────────────────────────┘     │
│                                                      │
│  Watchtower (polls GHCR, auto-restarts containers)  │
│  Cron: pg_dump → R2 daily                           │
└─────────────────────────────────────────────────────┘
```

## Access Patterns

**Public path:** Users reach CountyIQ through Cloudflare. Static frontend assets (React + MapLibre + Deck.gl) are served directly from Cloudflare Pages -- the VPS is never involved for page loads. API calls (`/api/*`) are proxied through Cloudflare to the VPS, where Caddy routes them to the FastAPI container. Vector tiles load from Cloudflare R2. The frontend is fully decoupled from the backend.

**Private path:** Developers access the VPS via SSH. The Dagster UI is not publicly exposed -- use an SSH tunnel (`ssh -L 3000:localhost:3000 countyiq`) to access it locally. Postgres is also internal-only, accessible via SSH tunnel for ad hoc queries.

**Resource isolation:** All services run on one box, but in separate Docker containers. FastAPI serves API requests in its own container with dedicated resources. Pipeline jobs (Dagster + Playwright scrapers) run in a separate container. A scraper running at 3am doesn't affect API response times. With 4 GB RAM, there is ample headroom for concurrent Playwright browsers, Dagster scheduling, and API serving -- eliminating the memory contention that constrained the original 1 GB design.

**Data flow:** Dagster scrapes public data sources (GIS, tax records, court records) on schedule. Raw responses are archived to Cloudflare R2 for replay and audit. Parsers extract structured data into staging tables (SCD Type 2). Entity resolution links records by PIDN into `public.properties` (a VIEW). The FastAPI container reads from Postgres to serve the frontend. The frontend calls the API and loads vector tiles from R2.
