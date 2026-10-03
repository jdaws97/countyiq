# Local public-source worker

CountyIQ can acquire approved public feeds from an operator's PC and import them
through the VPS's normal Dagster assets. This is useful when PennDOT, PA DEP, or
the county website is reachable from the PC but times out from the VPS.

The PC needs this repository's locked pipeline environment, internet access, and
the operator's existing SSH access. It does not need the production database
password, R2 credentials, an exposed database port, or a local database. Runs are
manual while the PC is online; there is no background schedule or paid service.

## Supported sources

| Asset | Snapshot |
| --- | --- |
| `penndot_roads_arcgis` | State road segments filtered to the configured county |
| `penndot_projects_arcgis` | All four configured transportation project layers |
| `traffic_counts_arcgis` | State traffic counts filtered to the configured county |
| `pa_dep_environmental_diligence` | Regulated tank facilities and cleanup locations |
| `tax_claims` | The original county delinquent-tax PDF |

Source URLs, county filters and spatial bounds come from `county_config.py`.
The manifest records the complete request, retrieval times, row counts, policy
receipt fingerprints and SHA-256 hashes. ArcGIS acquisition checks source counts
before and after downloading every page and rejects duplicate object IDs.

## Run

Use the same source contract version on the PC and VPS. Replace the SSH target
and identity path below with the operator's configured connection. Keep SSH host
verification enabled. The examples run from the repository root on the PC.

1. Ask the VPS to check current policy and issue a bounded acquisition permit.
   Select fewer assets when only one source needs recovery.

   ```bash
   ssh -i ~/.ssh/jdawskey -o BatchMode=yes ubuntu@15.204.255.199 \
     'sudo -n docker exec countyiq-dagster-webserver python scripts/local_source_worker.py authorize --assets penndot_roads_arcgis penndot_projects_arcgis traffic_counts_arcgis pa_dep_environmental_diligence tax_claims' \
     > /tmp/countyiq-source-permit.json
   ```

2. Fetch on the PC. The locked environment is installed with
   `uv sync --project pipelines --locked`. No production environment file is
   copied to the PC.

   ```bash
   pipelines/.venv/bin/python pipelines/scripts/local_source_worker.py fetch \
     --permit /tmp/countyiq-source-permit.json \
     --output /tmp/countyiq-source-bundles \
     > /tmp/countyiq-source-receipt.json
   ```

   Standard error reports progress. The JSON receipt contains `bundle_id`,
   `manifest_sha256`, and `directory`. Retain the digest from this receipt;
   do not recalculate trust from files after transfer. Failed acquisitions leave
   a hidden `.partial` directory that cannot be submitted.

3. Transfer only the completed bundle directory using `scp -r`. Stage it under
   the SSH user's home directory, then use `sudo` to place it under
   `/var/lib/countyiq/source-inbox/<bundle_id>`. Give UID/GID `10001:10001`
   ownership, directory mode `0700`, and file mode `0600`. Do not overwrite an
   existing bundle. The pipeline containers mount the inbox read-only.

4. Submit on the VPS, substituting the exact ID and digest from the local
   receipt:

   ```bash
   sudo docker exec countyiq-dagster-webserver \
     python scripts/local_source_worker.py submit \
     --bundle-id <bundle_id> \
     --manifest-sha256 <manifest_sha256>
   ```

   Submission rechecks current source policy. Dagster queues the selected source
   assets under the existing single-run concurrency limit. A returned run ID is
   not a successful import: inspect its terminal status, asset checks, per-asset
   counts and source health before considering the source recovered. The normal
   assets archive raw evidence, parse it, and preserve SCD2 history. They attach
   the bundle ID, trusted digest and acquisition time to their materializations.
   Submitting the same bundle again returns its existing run ID and status. If
   that run failed, acquire a new bundle for the failed assets.

5. Run the applicable deterministic enrichment job after successful imports if
   derived screening needs rebuilding. Do not enable paid inference to complete
   a source refresh. Verify a real property's relevant evidence and timestamps.

## Failure and retention behavior

Permits and snapshots expire after 24 hours. Import rejects altered files,
symlinks, unexpected files, unknown sources, county-contract changes, oversized
payloads, missing required layers, and count mismatches. Schema checks use the
captured layer metadata. They do not make the failed VPS network path a hidden
requirement of offline import.

A snapshot cannot replace an asset materialized after its acquisition began.
Acquire a new snapshot for any failed assets when retrying a partly successful
run. Existing successful assets retain their data. An older tax report cannot
replace a newer imported report. Each load commits its acquisition watermark in
the same database transaction as its staging rows. A failed run cannot lose that
protection after a successful database write. Different snapshots acquired before
a subsequent database publication are held, including overlapping acquisitions.
The manifest digest identifies an identical retry. The two environmental layers have
separate transactions and watermarks; this workflow does not promise an
all-or-nothing transaction across layers or sources.

Source snapshots are operator-controlled evidence, not a public upload API. The
policy permit and its digest are transferred through trusted SSH; they are not
cryptographic publisher signatures. Source authorization is checked again by
each asset before import. The original publisher's fields and report dates keep
their meaning; retrieval time does not make an old source record current.

After verifying the import and normal raw archive, delete that specific inbox
bundle and its PC/staging copies. Keep the small receipt with the operational
run record. Do not remove another in-progress run's bundle. Failed snapshots
remain private and should be removed after diagnosis, within the source's
reviewed retention policy. No raw snapshots are committed to Git or exported in
customer packets.
