# Production launch record — September 5, 2026

The private application is live at **https://app.countyiq.net** on commit
`6b661c4adae1c7f84d64e6d6faa2aa83a23de88d`, deployed at 21:44:34 UTC. All six
services are running; authenticated public readiness returns HTTP 200 with
`{"status":"ok"}`. The same service credential receives a customer challenge
on `/api/session` (302), so it cannot access customer workspaces. **Full
backfill is not approved.** The user authorized product iteration, bounded canaries, commits,
pushes to main and deployment; full backfill remains a separate user decision.

The immutable release receipt is
`/var/lib/countyiq/releases/20260905T214434Z-6b661c4adae1c7f84d64e6d6faa2aa83a23de88d.env`.
Its rollback backup is `20260905T214301Z-pre-deploy-6b661c4adae1`. PostgreSQL
and the API have no host port; Dagster is bound only to loopback.

## Data and recovery

The real local revision-061 database was checksum-verified, restored to an
isolated VPS candidate and initially migrated to revision 065. The spatial-fact
release subsequently applied revision 066. Promotion preserved the
original empty database as `countyiq_preimport_20260905`. The live data contains
175,928 current parcels and 6,459 current proceedings. No evaluation results
were imported as accepted production intelligence.

The original candidate-pair refresh was quadratic. Migration 065 uses a
municipality/name GIN index and an indexed lateral lookup, preserving the
strict similarity threshold. The full refresh took 4 minutes 48 seconds on the
VPS. All 19,870 owner-name pairs exactly match the original local result:
SHA-256 `fe485e5ae14c3710b56c088472d5a47027f72c50cad1f4df62930676e1a5ee48`.
The pipeline role owns this rebuildable view, while source tables remain
administrator-owned. Three intelligence-integrity discrepancy counts are zero.

All 1,110 raw source files, totaling 2,738,271,652 bytes, are stored in private
R2 under their original relative paths. A full download comparison found no
differences. Protected local and VPS copies of the source database dump and raw
archive remain available. The off-host empty baseline is
`20260905T180740Z-preimport-empty-baseline`.

Database backups have seven-day lifecycle retention and a three-day lock. The
cost guard enforces the configured 8,000,000,000-byte total storage ceiling.
The fresh post-deployment backup `20260905T191857Z-restore-drill` is verified
in R2. Its isolated restore passed for both databases at 19:26:09 UTC, recovering
175,928 properties and 22 Dagster tables. The receipt is
`/var/lib/countyiq/restore-drills/20260905T192609Z-20260905T191857Z-restore-drill.env`.
The daily timer is enabled and active. Its installed systemd service passed
with exit 0 and verified backup `20260905T192726Z-scheduled`; the next run is
September 6 at 04:00 UTC plus up to 15 minutes of randomized delay. Storage
use after this verification is 3,890,664,204 bytes against the 8 GB ceiling. The installed backup service now matches the committed unit,
including write access to the cost-guard state directory.

Evidence: `output/production-readiness-2026-09-05/live-release-receipt.log`,
`offhost-restore-drill.log` and `scheduled-backup-verification.log`. Main CI
passes in [run 33986989659](https://github.com/jdaws97/countyiq/actions/runs/33986989659);
the CodeQL limitation appears in
[run 33986989674](https://github.com/jdaws97/countyiq/actions/runs/33986989674).

## Infrastructure findings resolved

- The old rclone build exposed the backup credential in debug output. The log
  was redacted, the user rotated the backup secret, and a hidden-input helper
  verified rejection of the old secret before encrypting and publishing the
  replacement. Raw-archive and infrastructure credentials were kept separate.
- Upstream rclone 1.75.1 is checksum-pinned in Ansible. It fixes false HTTP 501
  errors from the older uploader; first-attempt uploads and download checks pass.
- Empty `COUNTYIQ_COUNTY_CONFIG_DIR` now selects the bundled county directory.
  Docker's empty value previously made Dagster parse `pyproject.toml` as a
  county manifest. The deployed-environment import regression now passes.
- The Tunnel token uses a read-only file mount. Its parent is root-only 0700;
  the file is root-owned, group 65532, mode 0440. The container runs as UID/GID
  65532. A real container check proved readable access and denied writes.
- Public readiness allows six bounded attempts for transport/5xx startup
  failures. Redirects, authentication failures and wrong response bodies still
  fail immediately. This addresses the delay between container startup and
  Cloudflare Tunnel registration.

Cloudflare manages the edge TLS certificate for `countyiq.net` and
`*.countyiq.net`; the inspected certificate is valid September 4–December 3,
2026. Tunnel encrypts the route to the VPS; HTTP is confined to the private
Docker hop. SOPS uses the Ed25519 SSH recipient in `.sops.yaml`. Its decryption
key is the local `/home/jdaws/.ssh/jdawskey`, which is not copied to the VPS.

## Customer experience reviewed

The product is one York County investigation workspace for local developers
and acquisition teams. The promise is “Follow local development. See the
evidence.” The [product direction](../products/real-estate-intelligence.md)
defines the pilot; $79/month is an unpublished hypothesis, not validated demand.

Playwright reviewed the current source at `http://app.localhost:5180/` against
the real API and county data. Port 5173 is an older built UI and 5175 is synthetic.
The browser checks cover desktop and 390px phone widths:

- Address search, property evidence, owner navigation, watch persistence and
  useful empty states. Assessed value and recorded transfer amounts are labeled.
- Map selection fits and highlights the parcel; clicks select, drags pan. The
  light default, dark theme, optional layers, legend and mobile controls work.
  Viewport requests cover the actual canvas, split at the API's span limit,
  deduplicate parcels and refresh after a layer is re-enabled.
- Property pages lead with separate opportunity, momentum and site scores.
  The map panel gives key facts and a direct route to the evidence.
- Nearby parcels show five initially, expand to forty and use readable mobile
  cards. Print packets expand evidence and nearby parcels, then restore the UI.
- Missing mapped structures are described as a vacancy screen requiring
  verification, never established current use.

Screenshots and the final print packet are under `output/playwright/production-*`.
These are local review artifacts, not marketing assets. Live authenticated
workspace and cross-session persistence verification remain outstanding.

## LLM qualification and cost

The [model comparison](../research/model-comparison-2026-09-05.md) contains the
current source reviews and preserved raw results: 207 evaluation-only calls,
$0.314540116 total. None issued a quality receipt or wrote serving intelligence.

The harness now uses explicit model-appropriate reasoning and sampling settings.
Removing factual examples from the shared citation prompt materially improved
DeepSeek's brief-format results. This confirms that earlier failures were not
all model capability failures. Unknown references remain rejected.

GLM 5.3 Flash is the strongest lower-cost challenger so far. DeepSeek still has
long/variable latency and unsupported interpretations. Luna is not qualified
for full backfill merely because its format scores are higher. The 11/12-neighbor
discrepancy is resolved: other-owner counts and all-neighbor acreage describe
different populations, now labeled in the prompt. Pass 0 source fingerprints
are caller-owned; replay checks retain the original source binding. New canaries
still expose agenda/decision-scope errors and incorrect repeated numeric facts.
Models and frozen labels have not been silently changed. Reduce unnecessary
model narration before another broad comparison; full backfill remains disabled.

The current harness uses synchronous OpenRouter Chat Completions. Parcel-level
“batching” in Pass 2 is unrelated to the discounted provider Batch API. Direct
Luna Batch pricing must be considered, but the user has only OpenRouter and no
direct OpenAI billing/key. Eight identical P2/P3 cases are prepared, unsubmitted,
with a $0.10 cap and conservative $0.050425 bound. No direct account was created.
The offline transport prototype was not accepted or added to production.

All paid passes, optional AI search, county narratives, judges and escalation
remain disabled. Bounded canaries and source review must precede any request
for full-backfill approval.

## Validation and remaining release work

Recorded checks include 1,357 pipeline unit/regression tests, 104 database
integration tests, 120 API unit tests, 108 API integration tests, and 30 frontend
tests. TypeScript, lint and production build pass. Later startup fixes pass 19
county-config tests, 21 deployment/account unit checks, five deployment recovery
integration cases and eight HTTP readiness cases. Ansible syntax, targeted
secret scanning and whitespace checks pass. These are actual local checks;
GitHub Actions on the deployed commit passed pipeline, frontend and secret
checks but exposed API import-path, Compose env-file and CodeQL permission
configuration errors. Commit `da8be7286571bc8dda1047a6f8bbde591c6a4145` fixes
those workflow settings; all six main CI jobs pass remotely. The separate
CodeQL analyses ran, but GitHub rejected their result upload because code
scanning is disabled for this private repository. No clean CodeQL result is
claimed. Enabling a supported code-scanning setup remains an open operational
item; no paid GitHub feature or subscription was enabled. The corrected API
commands pass 120 unit and 108 integration tests locally.

Remaining: verify the live customer sign-in/workspace flow, resolve the optional
CodeQL upload configuration, complete the LLM canaries/source review,
and establish a working pilot inquiry path. `hello@countyiq.net` is intended but
not configured or published. The apex marketing Access gate stays in place until
contact and live customer checks are complete. No billing or outreach was sent.
## Latest private-alpha access and LLM review

The live apex and app Access policies now allow `thowe095@gmail.com` and
`tyler.j.daws@gmail.com` alongside the existing operator address. Each invitation
changed only the two email policies; both subsequent plans showed no drift.
The friend's change is committed as `7f74243`; its main CI passed. The brother's
address was added after the user's follow-up. No invitation email was sent.
A browser remains at the Cloudflare sign-in screen, so successful live
customer authentication and account-workspace persistence are still unverified.

The source-context simplification and its 21-call diagnostic repeat brought the
release review to **195 calls / $0.283666540**, before the ownership follow-up. All outputs were reviewed against
their frozen records; source and action-consistency failures remain across the
candidate models. The full backfill is **not approved**, no quality receipt was
issued, and production LLM flags remain disabled. See the updated
[model comparison](../research/model-comparison-2026-09-05.md) for evidence,
measured call reduction and limitations. These source-policy and brief changes
are included in the production revision recorded above.

The deployed property report now presents the accepted brief's action: investigate,
watch, or no clear development lead. It reads that action from the same inference
history that authenticates its text. It removes the old opportunity assessment badge, repeated rationale and
duplicate citation badges. Source links and questions remain. API contract and
brief provenance tests passed (57), as did frontend type checking, lint and the
production build. Browser-only fixtures exercised all three action labels and
legacy null, opened source evidence at 1440px and 390px with no horizontal
overflow, and were removed afterward. No fixture was written to the database or
published as a real brief. Screenshots are
`output/playwright/research-brief-390-fixture.png` and
`output/playwright/research-brief-1440-fixture.png`.

That walkthrough exposed inconsistent zoning selection and fragmented soil
cards on PIDN `54000HJ012400`. The deployed revision-066 helpers now share
spatial selection between API reports and source signals, preserve contributing
source IDs and calculate soil coverage from unioned geometries. The municipality
appears in the report header; detailed soil units expand on request. See the
[spatial-fact review](../research/spatial-fact-review-2026-09-05.md).

The first production deterministic refresh computed all replacement signals but
rolled back when `RESTART IDENTITY` required sequence ownership. The previous
363,146-row snapshot remained readable. The current release removes that
unnecessary reset; all four publication/rollback integration cases pass under
the restricted pipeline role. All six main CI jobs pass in
[run 33993768168](https://github.com/jdaws97/countyiq/actions/runs/33993768168).
The production retry completed at 21:56:56 UTC in 677.05 seconds. It published
361,293 unique PIDN/key signals and refreshed 162,886 scored parcels. The changed
zoning and soil PIDN sets exactly match the reviewed local rebuild: zoning
13,351 → 11,569 (1,782 removed); soil 38,701 → 38,735 (62 added, 28 removed).
Current parcels remain 175,928; accepted evidence remains zero; current Pass 2
eligibility is 3,160. The example report and cached source signal both use
zoning record 1706 and MOD soil coverage 25.2% across source IDs 810/16498.
Public authenticated readiness passed during both attempts and after completion;
the readiness credential still cannot access customer sessions. Evidence is
under `output/production-readiness-2026-09-05/spatial-facts/`.

The later ownership-context changes are committed on main as `50a28db` and
are not yet in the deployed revision above. They remove unused generated
portfolio arithmetic, defer oversized components before spending or graph writes,
and make the estimate report context deferrals. Their nine matched canaries
bring the total to **204 calls / $0.304713606**. Luna and GLM each pass the
three reference gates with source-supported record groupings; GLM costs about
77% less in this small comparison. DeepSeek returns one truncated response and
two responses rejected for identifier/citation formatting. Corporate lookup
provenance wording and repeatability remain under review. No model default or
full-backfill approval changed; all production paid passes remain disabled.

The subsequent three-model York City minutes canary cost $0.009826510. It found
an actual validator false rejection: all models recognized recorded advisory
votes, but the retained agenda template caused three records to be dropped.
Saved-response replay after the source-bound vote and building-reuse fixes
retains all four applications and two of three reference discovery matters.
Unsupported narrative next steps, one wrong passage citation, and a resolved
zoning correction treated as an identity conflict remain qualification issues.
The current [metadata cleanup plan](../research/proceeding-metadata-review-2026-09-05.md)
is unapplied. Dispatch now requires current-version metadata; production paid
passes remain disabled throughout this review.
