# Architecture Overview

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           PUBLIC INTERNET                                │
│                                                                          │
│   Users ───▶ CloudFront ───▶ S3 (React + MapLibre + Deck.gl)            │
│                  │                                                       │
│                  └──▶ API Gateway ───▶ Lambda (FastAPI) ──┐              │
│                                                           │              │
└───────────────────────────────────────────────────────────┼──────────────┘
                                                            │
┌───────────────────────────────────────────────────────────┼──────────────┐
│                           AWS VPC                         │              │
│                                                           ▼              │
│   ┌──────────────┐                              ┌──────────────┐        │
│   │  EC2 t3.micro│                              │ RDS Postgres │        │
│   │  Amazon Linux│                              │ + PostGIS    │        │
│   │              │                              │              │        │
│   │  ┌─────────┐ │                              │ countyiq  │        │
│   │  │ Dagster  │ │─────────────────────────────▶│ _intel (app) │        │
│   │  │ webserver│ │                              │              │        │
│   │  │ daemon   │ │                              │ dagster (meta)│       │
│   │  │ workers  │ │                              └──────────────┘        │
│   │  └─────────┘ │                                                      │
│   │       │      │     ┌──────────────┐                                 │
│   │       ▼      │────▶│ S3 Buckets   │                                 │
│   │  Scrapers:   │     │ - raw data   │                                 │
│   │  - requests  │     │ - static site│                                 │
│   │  - Playwright│     └──────────────┘                                 │
│   │  - pdfplumber│                                                      │
│   └──────────────┘                                                      │
│         │                                                               │
│         ▼                                                               │
│   ┌──────────────┐                                                      │
│   │ Data Sources  │                                                      │
│   │ (outbound)   │                                                      │
│   └──────────────┘                                                      │
└─────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│                          YOUR MACHINE                                    │
│                                                                          │
│   AWS CLI ──── Session Manager ────▶ EC2 (Dagster UI on localhost:3000)  │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

**Two access patterns:**

1. **Public (frontend):** Users hit CloudFront → static React app from S3 + API calls routed through API Gateway → Lambda → RDS. No EC2 involvement for public requests.
2. **Private (admin):** You access Dagster UI via Session Manager port forwarding. Dagster + scrapers run on EC2, writing to the same RDS database.

**Key design:** The public frontend (Lambda) and the private backend (EC2/Dagster) share the same RDS database but are completely decoupled. Scraper jobs running at 3am don't affect API response times. A traffic spike on the public site doesn't slow down pipeline execution.

---
