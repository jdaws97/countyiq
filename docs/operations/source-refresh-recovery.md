# Source refresh diagnosis — October 3, 2026

Production inspection found current heartbeats for all six Dagster daemons,
seven enabled schedules, and functioning run sensors. The 23 source warnings
were not evidence of a stopped daemon. The September 28 Grafana datasource
errors separately reported HTTP 500 responses from its query service.

The September 27 county GIS steps failed certificate validation at
`arcweb1.ycpc.org`. PennDOT and DEP requests timed out connecting from the VPS.
The October 1 bulk run failed downloading the county tax PDF, while its PLCB
asset completed successfully. The September 20 grouped GIS runs also contained
successful county assets and failed state assets. Whole-job status incorrectly
made those successful sources look as old as September 2.

Migration 087 and the run sensors now maintain `meta.asset_refresh_status`.
Only explicit positive source materialization counts advance successful-refresh
time. Missing, malformed and zero-count receipts remain unverified; a failed
attempt preserves the previous successful timestamp. Composite sources require
all contributing assets. Incremental entity and municipal coverage contracts
remain separate. The API uses job outcomes only before the ledger is installed.

After deploying migration 087 and the updated images, preview retained receipts
inside the Dagster environment:

```bash
python /opt/pipelines/scripts/reconcile_asset_refreshes.py --days 45
```

Review the bounded receipt counts, then run the same command with `--apply`.
This only reconciles derived health evidence; it does not rerun acquisition or
change source records. Replaying is idempotent. Verify `/api/ops/health` and the
Grafana `countyiq_source_status_info` series afterward. A corrected timestamp
does not resolve a later failed attempt.

The shared ArcGIS client also rejects malformed HTTP-200 responses, invalid
counts and empty pages that claim more data. They cannot silently become empty
or truncated snapshots used by SCD expiry.

## Remaining acquisition issues

- Keep TLS verification enabled. A fresh October 3 probe from the production
  Dagster container received HTTP 200 from county GIS with valid TLS. The
  certificate failures were recorded in the September 27 runs. Retry the county
  assets and verify their materializations before claiming recovery.
- Official PennDOT services at `gis.penndot.pa.gov/gis/rest/services` respond
  locally with valid TLS. Roads returned 2,272 York records; traffic returned
  1,819. The VPS cannot establish TCP connections to either the old or current
  host. A URL-only change does not repair that connection failure.
- Use the current official PennDOT URLs. All four selected project categories
  were checked: layers 1, 2, 4 and 5 returned 8, 34, 129 and 97 York features.
  Under Construction Points uses `PROJECT_ID` and `PROJECT_CLASS`, unlike the
  other categories. The parser and geometry lookup now preserve these projects.
  Its `CRNT_CNTRCT_AM` stays in the source payload; it is not substituted for
  `PHS_EST_COST_AM`. Validate every selected layer before publishing a snapshot.
- DEP and the county website also need successful VPS connectivity before a
  refresh can be claimed. The official county sitemap identifies
  `/1184/Delinquent-Tax-Claim-Listing-PDF` as a current tax listing; parser and
  redirect validation are still required before adopting it.
- Of 112 active municipal bodies inspected, 60 reported `ok` and 14
  `not_modified`. Remaining results include budget, robots, source-policy,
  partial-error and empty-listing gaps. A successful grouped scraper run cannot
  establish complete municipal coverage.

This diagnosis does not claim those upstream issues are repaired. Dataset
status, source publication dates and acquisition timestamps must remain distinct
in customer research packets.

The read-only `pipelines/scripts/check_source_connectivity.py` probes the same
public URLs from any host. On October 3 all five probes answered locally;
county GIS and GitHub answered from the VPS, while PennDOT, DEP and the county
website timed out. A packet capture confirmed outgoing PennDOT SYNs without
replies. The host firewall permits outbound traffic. This narrows the problem
to the external path or IP access, without establishing which party drops it.
The dedicated GitHub workflow supplies a separate network comparison before
deciding whether an ingestion worker or a full migration is justified.
