---
name: package_renamed_to_countyiq
description: Python package renamed from york_county to countyiq; all platform naming uses countyiq convention
type: feedback
---

The Python package was renamed from `york_county` to `countyiq` on 2026-03-21. All platform naming (S3 buckets, DB name, Terraform resources, SSM paths, EC2 paths) now uses `countyiq` instead of `york-county`.

**Why:** User wants correct multi-county naming from the start, not legacy York-specific names that get confusing at scale.

**How to apply:**
- Import from `countyiq.*`, not `york_county.*`
- Dagster entry point: `-m countyiq.definitions`
- DB name default: `countyiq` (not `york_county_intel`)
- S3 bucket: `countyiq-raw` (not `york-county-raw`)
- All new infra resources use `countyiq-*` prefix
- County-specific data (config entries, URLs, filter strings) still references "York" — that's data, not naming
