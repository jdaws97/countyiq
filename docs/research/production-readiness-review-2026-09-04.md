# CountyIQ comprehensive review — 2026-09-04

## Verdict

CountyIQ has a credible private-alpha foundation, but production readiness has not been demonstrated end to end. Its strongest customer proposition is finding a property or municipal action, verifying the evidence, understanding nearby/ownership context, and retaining the investigation. More surfaces and more generated prose will not compensate for missing feed coverage or unreliable saved work.

This review inspected the existing dirty worktree, exercised local browser workflows, ran application and database tests, inspected infrastructure and recovery code, and implemented the defects listed below. Existing changes were preserved. No production deployment, paid inference, source collection, account change, or customer outreach was performed. This is a broad engineering/product review, not a claim that every line or possible failure has been audited.

Latest quality evidence: the revised 40-document municipal evaluation completed
for $0.14069727 and still failed release acceptance. Only five matters survive
after the offline date correction. See [revised evaluation](municipal-llm-v2-results-2026-09-04.md).
The immediate product priority is simplifying and evaluating the evidence contract,
not expanding backfill volume.

## Live plan

Completed baseline passes:

- [x] Inventory product, runtime, infrastructure and existing changes.
- [x] Establish API, pipeline, database, frontend and dependency baselines.
- [x] Exercise desktop/mobile Radar, property, watch, search and map workflows.
- [x] Inspect security, deployment/recovery, IaC, ingestion and intelligence boundaries.
- [x] Fix verified defects and add behavioral regression checks.
- [x] Assess customer value and maintenance priorities.
- [x] Finish baseline image/HTTP checks and record remaining launch gates.

Outstanding acceptance work for the current, subsequently changed code:

- [ ] Validate complete upstream provenance and invalidation for cached narratives.
- [ ] Finish metadata classifier/repair review and verify reviewed real-data repair.
- [ ] Establish representative accepted project inventory and recurring update coverage.
- [ ] Verify live authenticated customer journeys and account configuration.
- [ ] Apply approved host fixes and verify release/restore evidence on the target host.
- [ ] Build and verify the final current release candidate after concurrent changes settle.

Recommended product follow-up: validate the documented customer-value hypotheses
with observed investigations. This is not an engineering acceptance gate or
authorized customer outreach; the requested feature/value assessment is recorded
below with its evidence limits.

A checked baseline pass is not acceptance evidence for later changes. The dated
continued-review sections below record what each subsequent check actually covers.

## Customer value assessment

These are hypotheses grounded in implemented behavior and the stated investor/developer buyer, not validated customer research. The product documents report no customer conversations. Pricing and willingness-to-pay statements should remain hypotheses.

| Feature | Customer value | Value loss / maintenance risk | Decision |
|---|---|---|---|
| Address/owner/parcel search | Fast entry into an existing investigation; real address query returned the intended parcel first | Fuzzy matches need clear labels; PIDN/public-organization wording adds friction | Keep deterministic search; customer-facing wording simplified |
| Property report and source receipts | Consolidates diligence inputs and lets a customer verify claims | An absent delinquency match or inferred vacancy must not read as a guarantee | Core surface; softened those claims and retain source dates/caveats |
| Municipal proceedings and project timelines | Potentially strongest differentiation for developers tracking hearings, decisions and competitors | Empty or stale coverage breaks the central promise; a paused body must not look inactive | Prioritize evidence-contract simplification and quality acceptance before backfill; retain source-level freshness |
| Feed | Useful triage across many sources | Initial local review found an empty feed despite populated parcel/radar data; recurring useful coverage still needs acceptance evidence | Core, but do not market demonstrated early-warning performance until observed |
| Radar opportunity and site screening | Explains why parcels warrant further inspection; populated results and reason chips are useful | Four modes, score jargon and ranked precision can imply prediction; exempt/public land can consume attention | Keep, lead with buyer intent and evidence; validate default filters with actual buyers |
| Momentum and Movers | Helps repeat users find changing activity | Overlap with Feed; little standalone value until regular history refreshes exist | Keep secondary; test whether users act on score movement |
| Map and nearby parcels | Valuable spatial context for site and corridor work | Two graphics systems, large bundle, many overlays and a 1,456-line page | Keep as supporting workflow; defer a rewrite until measured usage/performance justifies it |
| Entity/owner portfolios | Helps find connected holdings and investigate organizations | Entity resolution is not proof of beneficial ownership; careless labels can overstate certainty | Keep evidence and unresolved states; do not promise who “really owns” every LLC |
| Municipality views | Strong fit for developer territory monitoring | Can duplicate Feed/Radar controls | Keep as a filtered investigation entry point rather than a separate analytics product |
| Watch, saved searches and comparison | Core retention and shortlist workflow; account-backed sync, local edits and saved-copy recovery are implemented | Account setup, conflict recovery and dual local/account states add support cost; live authentication remains unverified | Keep the existing account-backed workflow; make recovery truthful and reliable before adding sharing, teams or more notification channels |
| CSV and print packets | Practical handoff to an analyst or colleague | Formula injection and claim portability; private-alpha links require recipient access | Keep; CSV hardened, explain evidence dates and Access requirements |
| Generated briefs / cross-signal insights | Can reduce reading effort on ambiguous source material | Model cost, eval/rubric maintenance and false confidence; sparse processed coverage | Selective synthesis after deterministic evidence; no bulk expansion just to fill pages |
| Pass 4 narratives and natural-language search | Possible future convenience | Weak marginal benefit over filters/receipts; paid paths and another quality surface | Keep default-off; remove only after confirming no accepted customer workflow depends on them |
| Legacy license/distress/assemblage/project browsing | Little incremental navigation value beside current investigation flow | Duplicate routes, tests and mental models | Existing consolidation/redirect work is sensible; do not restore standalone screens without demand |
| Operations health | Essential operator visibility | Technical details distract customers; broadly exposed health can reveal internals | Keep an operator surface; review access scope before broader public access |

Recommended trial: have investors/developers bring a real target property and a municipality they monitor. Observe whether they can find evidence, understand the ranking, save a shortlist, and return after a refresh. Measure successful investigations and useful discoveries, not page count or generated-word volume. Do not build billing, team seats or another county before validating this loop.

## Implemented defects and improvements

| Priority | Before | Change and evidence |
|---|---|---|
| P1 | Same-day raw archive reruns wrote the same R2 key; the new bucket lock rejects overwrites | Unique remote object keys for payload and streamed uploads; regression simulates overwrite rejection. Local archive layout is preserved. |
| P1 | SSH hardening in a 99- include could lose to earlier cloud-init settings | Load in 00-, remove the superseded include, inspect effective `sshd -T` settings before reload, and restrict the reviewed OS range to Ubuntu 24.04. Syntax checked; effective host behavior remains a launch gate. |
| P1 | Public deploy readiness accepted an Access login redirect or unrelated HTML as success | Require HTTP 200 plus the expected health JSON. Optional root-owned curl config carries Access credentials. Ordinary deployment requires that config before stopping services. Six real local HTTP response regressions pass. |
| P1 | Workspace import wrote watches before validating the rest; quota errors were swallowed | Validate the entire portable format and saved destinations before mutation; batch writes restore prior values on failure. If storage also refuses rollback, report that explicitly. No cross-tab transaction or cloud durability is implied. |
| P2 | Watch/save/compare controls could claim success after failed persistence | Preserve/report the previous state and show a storage error. Tests cover denied writes and quota failures. |
| P2 | Valid JSON with the wrong shape crashed saved-search, comparison or triage readers | Validate stored shapes and filter records; malformed storage falls back safely. |
| P2 | Source text in CSV could be interpreted as a spreadsheet formula | Neutralize formula-like string prefixes and quote carriage returns as well as commas/newlines/quotes; numeric values remain numeric. |
| P2 | Connection return failure could leak a semaphore permit and progressively exhaust API capacity | Release the permit in a nested finally; regression proves capacity remains available. |
| P2 | Missing JavaScript chunks could receive the SPA HTML fallback with immutable caching | Dedicated asset handling returns 404; missing assets are not cached. HTML revalidates; real assets retain immutable caching. |
| P2 | Static production responses had no compression | Enable gzip/zstd; actual HTTP response verified gzip for the entry bundle. |
| P2 | Homepage record total summed monetary values depending on driver numeric types and double-counted delinquency subsets | Count explicit record categories; deterministic regression. |
| P2 | Cost allowlist silently ignored indented resources and `.tf.json` | Recognize indentation and reject unsupported JSON configuration; regressions cover both. This remains a source guard, not a substitute for reviewing the resolved plan. |
| P1 | Fresh test volumes could not initialize because Compose omitted required role credentials | Add dedicated test-role credentials and loopback binding; a new isolated instance initialized, migrated through all 54 revisions, and passed 32 integration tests. CI now runs database contracts. |
| P2 | Production environment regression fixture omitted the now-required tunnel token | Add a synthetic token while retaining fail-closed validation. |
| P2 | Moderate humanfs advisory in frontend dev dependencies | Update compatible lockfile dependencies; clean container install reports zero vulnerabilities. |
| UX | Homepage claimed a speed advantage without evidence; property labels overstated certainty | Narrow homepage promise, qualify empty feed/vacancy/tax status, use owner/parcel wording, add a visible homepage search submit button, and explain browser portability in customer terms. |
| Maintenance | Obsolete page requests continued in the browser | Abort superseded/unmounted requests in the shared fetch hook. |
| Maintenance | Build context included unrelated infrastructure/state and review directories | Exclude those directories; frontend behavior tests now run in CI and the web image build. |

Key files: `api/lib/database.py`, `api/routes/stats.py`, `docker/Caddyfile`, `docker/deploy.sh`, `docker/lib/operations.sh`, `infra/ansible/playbooks/bootstrap.yml`, `infra/cloudflare/check-cost-policy.sh`, `pipelines/countyiq/resources/storage.py`, and frontend browser-storage/investigation modules. All modifications remain uncommitted for review.

## UI/UX observations

- At 390×844, Radar navigation wraps coherently and results adapt into readable rows/cards. The header and four mode selectors consume much of the first screen. Avoid another global nav item; consider moving Compare to shortlist actions and presenting two primary Radar intents after observing customer use.
- The first real Radar result linked into its property report; Watch retained it and comparison selection worked. The production address search ranked that parcel first. Source dates, reasons and entity links help users assess results.
- The local Feed and watched evidence sections were empty. Empty does not prove no activity; customer coverage/freshness needs to be prominent. The review did not validate a populated live proceedings/project timeline or a complete recurring alert cycle.
- Map renders in the clean production build without JavaScript errors. Development StrictMode reproduced a known luma.gl ResizeObserver/initialization race. Keep this recorded rather than adding a fragile library monkey-patch or disabling StrictMode to hide it.
- The map remains expensive: approximately 826 KB plus 1,025 KB of map JavaScript before compression, or about 492 KB gzip combined. It is already lazy-loaded. Replacing deck.gl overlays with MapLibre layers could remove a renderer and reduce maintenance, but it needs parity tests for picking, overlays and styling; do not rewrite on bundle size alone.
- Nearby parcel tables are wide, comparison and property reports are dense, and several pages contain implementation-language copy. A task-based mobile trial and keyboard/screen-reader audit remain needed. This browser review is not a WCAG conformance audit.

## Infrastructure verdict

The single-host Compose plus Cloudflare Tunnel/Access design is proportionate for a private alpha. Separate API/pipeline/admin credentials, read-only API transactions, bounded pools/timeouts, private networks, loopback management ports, resource limits, image digests, exact-SHA deployment, verified backup manifests and migration quiescence are useful controls. OpenTofu validates against the installed providers; Ansible syntax checks; the web image builds from clean locked dependencies.

The architecture is not highly available: the host is a single failure domain. That can be an explicit alpha tradeoff. Kubernetes, another orchestration layer or managed services everywhere would add maintenance without proving customer value.

Remaining launch gates:

1. Apply/review the SSH fix on the actual host and prove effective settings plus a second key-authenticated session before closing the first. Verify provider firewall and exposed ports independently; a playbook syntax pass cannot establish these.
2. Configure and test a narrowly scoped Access service credential for readiness. The current IaC allowlist is for human OTP users; adding a curl config alone does not authorize a service token. Keep the application protected. Confirm invited/uninvited behavior externally.
3. Perform first deployment from a clean reviewed commit, including schema head, runtime role grants, a backfill import if needed, app readiness, and actual frontend route checks. No production release was made in this review.
4. Perform a complete off-host backup and disposable restore drill and retain receipts. Test host loss as well as restore into the same surviving host. Daily backup/RTO/RPO, alert delivery and restart behavior need demonstrated results.
5. Validate feed backfill and recurring refresh coverage, including municipal bodies that are paused/stale. Inspect sample source-to-event receipts and known-negative cases; tests cannot establish actual source completeness or model accuracy.
6. Review the storage guard tradeoff: an R2 listing failure hard-stops the entire application and stops its timers. This prioritizes spend containment over availability and should be an explicit owner decision. It is not a billing cap: in-flight writes, other clients, stored bytes and operations can still incur charges.
7. Bound archive growth and disk usage under repeated reruns. Unique keys fix lock compatibility but retain each attempt; the existing guard samples usage and is not an atomic quota reservation for all writers.
8. Inspect the resolved IaC plan and provider state for drift and exposure. The text allowlist is intentionally limited; it cannot prove cost or policy correctness for every valid HCL expression. Protect state/plan files as secrets and keep the remote-state recovery path available.
9. Confirm frontend production hosting/runbook consistency. Current Compose serves frontend assets through Caddy; older docs still describe Pages/Hetzner while infrastructure docs describe an OVH host. The runtime frontend row was corrected; consolidate the remaining deployment narrative around the reviewed actual host.

No secrets were printed, decrypted, committed, or copied into images by this review. Dependency advisory scans and Bandit are limited checks, not a penetration test.

## Simplification and maintenance priorities

1. **One customer investigation loop.** Keep Search/Feed/Radar as entry points, case files as evidence, Map as context, Watch as retention. Stop adding separate browsers for each source type.
2. **One persistence implementation.** The new browser-storage commit helper centralizes rollback. Keep one portable format and validate it at the boundary. Consider IndexedDB or server persistence only when cross-tab atomicity/device sync becomes a real requirement.
3. **One data-fetching pattern.** Continue migrating hand-written fetch effects to the shared abortable hook, with explicit retry/error/empty states. Do not add a cache framework merely to replace a small hook; adopt one when actual cache invalidation needs appear.
4. **Break large modules along tested boundaries.** MapView (~1,456 lines), parcel routes (~1,025), Pass 1 (~1,018), LLM harness (~923), and batched Pass 2 (~895) are concentrated maintenance risks. Extract pure query builders, layer definitions, request adapters and validation functions incrementally. Preserve PIDN identity and transaction boundaries.
5. **Keep deterministic decisions deterministic.** Retain source-backed ranking/filtering/diffs and keep the paid synthesis boundary narrow. Do not simplify by removing provenance, rejection ledgers or contradiction quarantine. Remove duplicate model paths only after replaying accepted fixtures and confirming caller parity.
6. **Make CI cover the full release contract.** A dedicated database-integration job now bootstraps and migrates Postgres, runs the API contracts, and runs pipeline integration tests. The same fresh migration path and all 32 pipeline contracts passed locally. A previous-release upgrade fixture and automated browser smoke job remain useful follow-ups.
7. **Reduce operational knobs carefully.** Compose exposes many pass-level overrides and several shell scripts. Keep credential domains separate, centralize validation and avoid more wrappers. Do not introduce another deployment tool beside OpenTofu, Ansible and the release script without removing an equivalent responsibility.
8. **Separate exploratory research from the shipping contract.** Large model fixture/rubric files and research documents should have clear promotion status. Historical notebooks and generated artifacts must not look like validated product behavior or deployment inputs.
9. **Fix development ownership at its source.** Existing `dist` and parts of `node_modules` are root-owned. Avoid container commands that write host-mounted artifacts as root. The clean web image proves the lockfile works; broad ownership changes were deliberately not made to the user's environment.

## Verification ledger

- API unit tests: 81 passed.
- API database contracts: 29 passed against `countyiq_test`.
- Pipeline unit tests: 910 passed, integration tests intentionally deselected.
- Pipeline integration tests: 32 passed both against the existing test database and a fresh isolated database migrated from base through revision 054, with the live-database guard enabled; one existing Dagster `context.run_id` deprecation warning.
- Dagster definitions import: passed.
- Frontend: 8 workspace regressions passed; TypeScript, ESLint and the clean production web image build passed after final changes.
- API/pipeline pip-audit: no known vulnerabilities; the local CountyIQ package has no PyPI advisory entry and was skipped.
- Frontend clean `npm ci`: zero vulnerabilities after the compatible humanfs lockfile update.
- Bandit high-severity application/pipeline scan: no findings.
- OpenTofu validate: passed. Ansible syntax check: passed. Changed shell scripts parse; Cloudflare source cost policy passes. Final Caddy image validates. Actual HTTP checks confirm HTML `200/no-cache`, missing chunks `404/no-store`, and compressed immutable real assets.
- A combined API pytest invocation hit duplicate `test_development_radar.py` module names. Separate suites, as run in CI, both pass. Importlib-mode consolidation is a maintenance follow-up, not a product failure.
- Browser/HTTP artifacts are under `output/playwright/`; normal browser data was not used. Review servers use read-only transactions against local backfill data. Integration fixtures use a separate database.

## External technical evidence

- [OpenSSH configuration semantics](https://man.openbsd.org/sshd_config): the first obtained keyword value generally wins; effective config matters more than a late include filename.
- [Cloudflare R2 bucket locks](https://developers.cloudflare.com/r2/buckets/bucket-locks/): locks prevent overwriting as well as deletion, explaining same-day archive failure.
- [Cloudflare Access service tokens](https://developers.cloudflare.com/cloudflare-one/access-controls/service-credentials/service-tokens/): authenticated machine checks require a corresponding Access policy and credentials.
- [Upstream luma.gl initialization issue](https://github.com/visgl/luma.gl/issues/2487): matches the development-only ResizeObserver error reproduced here.

## Final scope and acceptance

The implemented fixes have **1,060 passing tests** across separate API, pipeline and frontend suites (81 + 29 + 910 + 32 + 8). This total does not count repeated runs. Fresh migrations, the clean web image, Caddy response checks, dependency scans and IaC syntax checks add separate evidence. `git diff --check` passes. The hosted CI job itself has not run in this session.

The code review and local hardening pass is complete; the broader production-readiness goal remains open until the external launch gates above are demonstrated. No claim of production deployment, successful off-host recovery, full accessibility compliance, complete source coverage, or customer-validated value is made.

## Continued review: recovery ownership and cost-guard execution

The previous local-hardening pass was progress, not proof of full production readiness. A subsequent inspection of the current worktree found and fixed these additional operational defects:

- **P1 — Cross-database restore collisions:** a custom Dagster database name could equal the primary restore target (or the reverse). Restore validation now requires every live and temporary name to be distinct, not merely each corresponding pair.
- **P1 — Unowned restore cleanup:** the drill previously dropped pre-existing target databases and could delete them even after an early download failure. It now refuses occupied names, records ownership only after successful creation, and cleans up only the database created by that run. Container scratch dump names are per-process.
- **P1 — Scheduled backup sandbox:** the backup service invokes the guard, which updates `/var/lib/countyiq/cost-guard`; that directory was missing from its systemd write allowlist. The service now grants that specific path.
- **P1 — Pipeline sentinel permissions:** the guard directory was root-only, while application containers run as UID 10001. They could not traverse it to check the trip file. Root retains write ownership, directory mode is now 0755, and application mounts remain read-only. Trip-file content remains private.
- **P2 — False stop success:** manual trips previously returned success when Docker or timer stops failed. The persistent stop still records first, but failed stop operations now return failure and explicitly require host verification. Status describes a latched stop rather than asserting that services are stopped.
- **P2 — Ignored environment threshold:** the guard captured the hard limit before loading the production environment. Scheduled checks now reload and validate the configured limit before deciding whether to trip.

Verification for this continuation: **28 affected tests passed**, including real shell-script execution in network-isolated containers with fixture Docker/R2 commands. Cases include early download failure, occupied restore targets, failure after creation, successful cleanup, Docker/timer stop failures, real UID-10001 sentinel access, and 3 GB versus 8 GB thresholds with the same measured usage. Shared public-readiness checks also pass. Changed shell scripts parse, Ansible syntax checks, and `git diff --check` passes. These checks do not claim that the production host has applied the changes or that a real off-host restore has succeeded.

Live next steps remain: review deployment/recovery concurrency and interruption behavior; extend browser verification to populated project/feed cases and accessibility; establish actual deployment, recovery and recurring data-coverage evidence. Existing staging and unrelated worktree edits were left intact.

## Continued review: deployment failure recovery and operation locking

Further progress on the operational launch boundary:

- Failed Alembic schema probes now propagate failure rather than returning `base`. A probe failure stops deployment before quiescing services; it cannot be used as evidence that the schema is unchanged.
- The deployment records that stopping services has begun before calling Compose, so a partially failed stop enters recovery handling.
- Recovery refuses to restart prior services when a cost stop is latched. Startup checks the guard again before PostgreSQL/application startup and after application startup. These checks do not turn the sampled cost guard into a transactional billing cap.
- Deployment retains the backup lock through migration and release receipt promotion. Its pre-deploy backup reuses the inherited lock descriptor, while independent scheduled backups are excluded.
- Restore drills take the deployment lock so verification does not overlap migration or deployment-driven service changes.

Verification: **37 affected operations checks pass**. Tests include actual deployment-script execution in network-isolated containers for failed schema probes, partial stop failure, and a stop failure accompanied by a latched guard. A cross-process lock test proves inherited nested use, rejection of an independent contender, and release after the holder exits. Edited shell scripts parse and `git diff --check` passes. No actual deployment or production operation was performed.

The next review work remains populated Feed/project workflows, accessibility and error-state UX, followed by stronger full-release and external host evidence. Production readiness remains unproven; this section records additional fixes rather than closing those gates.

## Continued review: Feed queue reliability and accessible status

This pass used Firefox with controlled API fixtures against the current frontend. It found and corrected:

- **P1 — Hidden remaining work:** reviewing all loaded events removed the pagination control even when the server reported more events. Load more is now independent of visible cards, and the empty message no longer claims the entire queue is clear when unloaded pages remain.
- **P2 — Pagination stuck after changing filters:** an aborted request could leave the loading flag set. Cleanup now aborts pagination on filter changes/unmount and releases the flag for the corresponding request.
- **P2 — Stale results after failed filtering:** an initial-page error could retain cards from the previous query. Failed filter requests now clear those cards and pagination; successful pagination clears its previous error.
- **P2 — URL and filters diverged:** Feed kept five duplicate filter states initialized only at mount. It now derives filters directly from URL parameters. Same-route navigation and saved search links update both the controls and request.
- Shared loading/success messages now expose a status role; failures expose an alert role.

Verification: six controlled browser assertions completed: fully reviewed first-page continuation, cancellation without a stuck button, subsequent pagination, failed-filter stale-card removal, same-route URL navigation, and successful error recovery. TypeScript, ESLint, eight workspace tests, and diff whitespace checks pass. Reproduction script: output/playwright/feed-regressions.cjs; mobile capture: output/playwright/feed-populated-mobile.png.

The 390 px mobile capture is readable without horizontal overflow, but the first card begins near the bottom of the first viewport because navigation, description, summary and filters precede it. Collapsing secondary filters is still a customer-workflow simplification candidate. The fixtures deliberately do not establish production coverage, source quality, populated project-case correctness or full accessibility compliance. The broader production-readiness goal remains open.

## Continued review: project verification and printable evidence

The current project case response includes recorded decision scope and source labels. The page now displays them alongside the conservative status, conditions and milestones, so a reader can distinguish a preliminary-plan decision from a broader permission claim.

Fixed workflow defects:

- Summary/condition/milestone links now expand their target timeline event. Readers can collapse it afterward.
- The sticky navigation obscured fragment targets on mobile. Navigation now reports its actual height to document scroll padding, including after responsive resizing.
- Collapsed project timeline cards previously omitted their details from printed packets. Project cards now retain printable evidence, and the report print lifecycle opens receipts temporarily and restores their prior state afterward.
- Printed receipts include original HTTP(S) source URLs. Watch/export controls are omitted from project print views.
- Project loading and errors use the shared accessible status component.

Verification: Firefox checked the populated fixture case, visible decision scope, summary-to-event navigation, manual collapse, condition-to-event navigation, original source URL, mobile anchor clearance, print-media evidence visibility, and restoration of the previous screen state. Captures were visually inspected. This verifies print media and lifecycle behavior; it is not a physical-printer or paginated-PDF certification. API project chronology tests (3), frontend workspace tests (8), TypeScript and ESLint pass. Browser script and captures are under output/playwright/project-evidence-check.cjs, project-evidence-mobile.png and project-print-evidence.png.

Customer implication: an evidence case file adds value when a reader can verify and share the exact decision and its scope. A headline status without accessible receipts creates misplaced confidence. This pass improves that existing workflow rather than adding another product surface. Production coverage, host deployment/recovery, and remaining release-wide verification still need evidence.

## Continued review: watch inbox boundaries and consequential changes

Fresh release-wide unit checks found an important regression introduced during the recommendation vocabulary transition: the auto-resolution helper compared a two-value change with a four-value set. No recommendation reversal could satisfy that equality. Consequential parcel/owner changes could therefore be automatically resolved.

**P1 fixed:** classification now compares opposite recommendation groups. Current investigate/insufficient-evidence reversals and historical pursue/pass/none reversals require human review in both directions, even during a version upgrade and even when the judge favors the challenger. Renaming within the same group does not create a false reversal. Twenty-two new parameterized regression cases cover those boundaries; the related policy documentation now matches the executable identity, signal and brief rules.

Watch inbox review also strengthened pagination: the API reads a 101st lookahead row, serves at most 100 candidates through the existing source-policy filter, and emits a cursor only when another candidate page exists. A fully filtered page still has a usable cursor. Notification/cursor identifiers outside PostgreSQL bigint bounds are rejected during request validation. Five independent API tests cover an entirely hidden first page, a visible older event, preservation of the lookahead record, the exact full-page boundary, and invalid identifiers.

The watch UI and API were changing concurrently during this pass. Overlapping UI edits from this review were removed; existing concurrent work was preserved. These tests establish the isolated pagination contract, not completed browser synchronization or production workspace isolation.

Fresh results on the current worktree: **90 API unit tests pass; 950 pipeline unit tests pass, with 44 integration tests deselected**. The initial pipeline run had two failures; both are fixed, and the complete unit suite was rerun successfully. TypeScript, ESLint and diff whitespace checks pass. These counts supersede the earlier unit-count snapshots; historical database integration evidence remains separate and was not refreshed in this pass.

## Continued review: fresh database, production build and live host evidence

Database isolation is now configurable through COUNTYIQ_TEST_DATABASE_PORT and COMPOSE_PROJECT_NAME. The standard port remains 5433. This review created the separate countyiq-review-release-20260904 project on loopback port 5434, with a new named volume, and verified schema revision 055 after migration.

- API database contracts: 32 passed on the fresh database.
- Additional real-role privilege checks: 4 passed. Explicitly writable API transactions cannot INSERT/UPDATE/DELETE/TRUNCATE source/intelligence tables, attempted deletes are denied by PostgreSQL, and subsequent pooled transactions return to the read-only default.
- Pipeline integration: 44 passed. One existing Dagster context.run_id deprecation warning remains in development_momentum.
- Current production web image builds successfully with workspace tests, lint, TypeScript and Vite. Caddy validates. Actual HTTP checks pass for HTML 200/no-cache, missing assets 404/no-store and real assets 200/immutable/gzip. The remaining map chunks are large but lazy loaded.
- The first local HTTP probe used the wrong container port; the service listens on 8080. Correcting the disposable test mapping produced the successful checks above.

**Read-only production-host observations, 2026-09-04:**

The host from the checked-in Ansible inventory is reachable using the configured key with strict host-key checking. Ubuntu 24.04.4 LTS is installed. UFW is active with default inbound deny and only SSH allowed (IPv4 and IPv6). No application containers are running. The cost-guard timer is enabled/active; the backup timer is disabled/inactive. No release or restore-drill receipt files were found.

**P1 deployment drift remains:** effective sshd settings report passwordauthentication yes. The host still has 50-cloud-init.conf enabling passwords before 99-countyiq-hardening.conf attempts to disable them; the repository's earlier 00-prefixed fix is not applied. Effective root login is disabled and public-key authentication is enabled. This establishes enabled password authentication, not that a usable account password exists.

**P1 deployment drift remains:** the host cost-guard directory is mode 0700, so application UID 10001 cannot traverse it. The repository already corrects this to 0755, but host application remains outstanding.

No production configuration was changed and no application was deployed. The read-only inspection replaces several previously unknown host facts with concrete remaining gates; it does not establish release readiness. The isolated local containers were stopped after verification and their named test volume retained. The shared port-5433 database and existing UI were not reset or stopped.

## Continued review: enforce host readiness and repair recovery instructions

The two observed host defects were previously outside deployment's enforced preflight. Actual deployment now calls a read-only host gate before image builds or service changes. The independent docker/check-host.sh checks effective default SSH authentication, root ownership/mode of the cost-guard directory, and real UID-10001 traversal without write access. Portable deploy --check is explicitly labeled configuration preflight.

Network-isolated tests exercise accepted settings, password/interactive/root/public-key policy failures, bad directory modes and an inaccessible parent directory. A live read-only invocation on the inventory host exits 1 with the expected passwordauthentication-no requirement. No remote files, settings or services were changed.

The operations runbook now matches the current deployment: protected /etc/countyiq/production.env, root operator shell, explicit Compose file, container-local Postgres access, cost-guard stop/restart controls, authenticated readiness, and retained Caddy image rollback. Removed stale Pages rollback and host-port database instructions, and replaced the misleading generic SCD repair recipe with incident-specific verification requirements.

The affected operational test set passes 46 checks, including a deployment-level assertion that failed host policy prevents image builds and service changes. Host remediation and actual release/recovery remain outstanding; the gate makes that missing work enforceable rather than treating the written plan as evidence.

## Continued review: search simplification and measured product coverage

Search used an unbounded plain-object cache plus separate state for mode,
description, rows and aggregate values. A search for constructor resolves an
inherited object property instead of a cache entry and crashes the route; this
was reproduced in Firefox before the change.

Search now uses the existing cancellation-safe JSON hook. Removing the duplicate
cache/state also clears stale aggregate results and descriptions on failed or
too-short queries, and aborts obsolete requests. The shared hook now supports an
explicit reload; retrying the same failed query works without a page reload.
Five browser scenarios pass: constructor, stale aggregate removal, retry,
obsolete-response protection and short-query clearing. The project evidence
and print checks also pass after the shared-hook change. TypeScript, ESLint and
eight workspace tests pass.

Read-only local backfill snapshot at 2026-09-04T21:01:43Z:

| Data surface | Rows |
|---|---:|
| Current property view | 175,928 |
| Owners | 148,461 |
| Radar projection | 162,897 |
| Stored public proceedings, including any historical versions | 7,414 |
| Proceeding extractions | 0 |
| Parcel briefs | 0 |
| Owner briefs | 0 |
| Intelligence events | 3,638, all delinquency_event |

The snapshot is local, not production. It establishes substantial search/map/
screening inputs but does not establish customer-useful development events,
project case files, briefs or recurring change coverage. Raw proceedings alone
are not extracted intelligence. A nominal event count must not be used to claim
a populated development feed. The production host has no application release.

Product priority remains a reliable discovery-to-evidence workflow with measured
coverage. Generated briefs and development alerts cannot be treated as validated
customer value until representative source-backed outputs and recurring updates
are demonstrated. Coverage evidence is saved in output/playwright/local-product-coverage.json.

Explicit approval to apply the two verified live-host fixes has been requested.
No host mutation or deployment was performed while that question is pending.

## Continued review: Radar filter integrity and pagination

Radar previously discarded a selected municipality if the municipality-options
request returned no matching entry. That silently broadened a customer search
to the county. It now retains the selected municipality, displays it even when
the options list is empty, and reports the scoped empty result.

Radar filters now derive from URL parameters. Updating filters updates the URL;
same-route navigation and refresh retain the selection. Each view starts with
its default score when switching views. Duplicate per-view filter state has
been removed, and hidden filters for other modes are cleared on view changes.

Pagination advances only after a successful response. Failed pages keep existing
results and remain retryable at the same offset; an empty final page removes the
pagination button. Appended rows are deduplicated by PIDN, and outstanding
pagination requests are aborted on a filter change or unmount.

Six controlled Firefox scenarios pass: preserved empty municipality scope,
retained results after pagination failure, same-offset retry, end-of-results
pagination removal, cleared retry error, and URL navigation/refresh persistence.
The 390 px mobile viewport was visually inspected. TypeScript, ESLint, eight
workspace tests and diff whitespace checks pass. Reproduction/capture:
output/playwright/radar-reliability.cjs and radar-filters-mobile.png.

Concurrent work has added workspace, organization and sign-in surfaces plus
account/authentication code and migration 056. These are additional current
review scope. Earlier schema-055 integration and web-image evidence do not
certify those newer changes. The live-host approval question remains pending.

## Continued review: account authentication and synchronization

The new account flow verifies Cloudflare Access RS256 application tokens against
configured issuer, audience and signing keys, and identifies accounts by verified
provider/issuer/subject rather than an email header. Empty-subject service tokens
are rejected. The token model was checked against Cloudflare's primary
[application token documentation](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/application-token/)
and [JWT validation guidance](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/validating-json/).
This code review does not establish that the production Access application and
origin boundary have been configured or tested.

Installed PyJWT refreshes signing keys on an unknown key ID. A per-client,
per-worker verification limiter now runs before that lookup (60/minute, burst
20). Regression tests verify that excess unknown-key requests do not trigger
further lookups, a verified identity is reused within one request, and a service
token cannot provision a human workspace. This bounds each worker's lookup
pressure; it is not a distributed edge rate limit.

Delayed 401 and 409 responses from a previous account could previously expire or
mark a newer account as conflicted. Error handling now checks the account
generation before changing session state. Conflict mutation occurs after that
check rather than inside the shared request helper.

Local edits made during the first account snapshot load now persist a review
marker immediately. Automatic synchronization preserves those edits across a
delayed response, retry and page reload. It asks the customer to export local
work or explicitly load the saved account copy before synchronization resumes.
Explicit replacement clears the marker. This avoids silently overwriting either
copy before a baseline version is known.

Fresh checks: 12 frontend runtime tests, TypeScript and ESLint pass; 103 API unit
tests and 42 API database integration tests pass on the isolated review database
with schema 056. The account database tests exercise ownership and cross-account
boundaries, version conflicts and request identity protections. Running both
pytest directories in one invocation encountered duplicate test module names;
the supported separate suite invocations above passed. No caches or user test
volumes were deleted to bypass collection.

These results cover the current account code, not an authenticated production
browser journey, live Access configuration, a deployed application release or a
production restore drill. The two requested host changes still await explicit
approval.

## Continued review: workspace replacement and clearing

Clearing the account previously left automatic synchronization unguarded during
DELETE, allowing a save to overlap the clear. Explicit saved-copy loading also
applied its delayed snapshot without checking whether the customer had edited
the local workspace since confirmation.

Both actions now share one guarded replacement path. The guard spans deletion
and the follow-up snapshot load. A changed local revision preserves local work
and sets a durable review marker instead of overwriting edits. A successful
DELETE sets that marker before fetching the new version, so a failed refresh
cannot automatically upload the old copy and undo the clear. Explicit saved-copy
loading resolves the marker after successful storage replacement.

Four additional regression cases cover edit-during-load, edit-during-clear,
ordinary successful clearing, and refresh failure after successful deletion.
All 16 frontend runtime tests, TypeScript and ESLint pass. A Firefox fixture
exercise reached the visible recovered workspace state after simulated DELETE
success/GET failure and explicit saved-copy reload. The script is
output/playwright/workspace-clear-reliability.cjs; its API data is synthetic and
does not verify production authentication. No live workspace was cleared.

## Continued review: unread inbox navigation

Background synchronization previously replaced an older inbox page with the
newest page every refresh. Customers also had no explicit newest-page control.
The inbox now retains its cursor across synchronization, exposes a newest-page
action, and ignores obsolete navigation/refresh responses. Acknowledgment sends
only the displayed IDs and reloads that page instead of unexpectedly jumping
back to the beginning. Account changes and workspace clearing reset the cursor.

Empty pages now distinguish policy-filtered entries with older pages available
from the end of the visible unread results. An empty page is not evidence that
the customer has no watches.

Five new runtime regressions cover refresh persistence, obsolete navigation,
page-specific acknowledgment, retry after failure, and a refresh started during
navigation. All 21 frontend tests, TypeScript and ESLint pass. Firefox exercised
hidden-page guidance, older navigation, synchronization while on an older page
and returning to newest using output/playwright/inbox-navigation.cjs. These
checks use synthetic inbox records and do not establish live notification
coverage or delivery.

## Continued review: account deployment preflight

Compose forwards the new account environment variables, but the production
validator did not check their consistency. An ordinary release could enable
workspace sync with authentication disabled, or configure an app/origin pair
that rejects browser writes despite a healthy process/database probe.

The shared production validator now checks supported provider and boolean
values, Cloudflare team issuer shape, nonempty/non-placeholder audience, and
the current single-host app/origin configuration against DOMAIN. Disabled
authentication remains supported when saved-work synchronization is disabled.
A future host split must change this gate alongside the routing/Access rollout;
it is not silently allowed by broad origin matching.

Twelve account configuration tests and five existing unit deployment checks
pass. Five network-isolated tests of the actual deployment entry point also
pass, including proof that invalid account configuration is rejected before
build/start/stop operations. Shell syntax and whitespace checks pass. No
production configuration or services were changed.

This gate checks configuration consistency only. It does not validate a real
Access application audience, a live human login, recurring source coverage,
production deployment or restore completion.

## Continued review: wrong-county proceedings containment

The separate project-data evaluation found six York source configurations on
domains belonging to Penn Township, Butler County, and Paradise Township,
Lancaster County. Rechecked official evidence:
[Penn Township](https://penntownship.org/) and the
[Paradise zoning notice](https://paradisetownship.org/wp-content/uploads/2025/02/ZHB-Notice-01152026.pdf).
This is material customer-value loss: geographically wrong proceedings can
produce misleading projects, watches and location associations.

Removed the six acquisition entries. Forward migration 057 pauses the matching
policies, disables acquisition/derived-product/export use, and records the
jurisdiction evidence. Retained source records and raw evidence are not deleted.
Downgrade refuses to re-enable known incorrect sources; resumption requires a
reviewed forward correction.

Configured coverage is now 107 entries, 105 distinct listing URLs, 66
municipalities with at least one source and 64 with a governing-body source.
After migration, policy inventory remains 122 rows across 72 municipalities,
with 107 conditional and 15 paused. These are source configuration counts,
not complete, current or correctly extracted municipal coverage.

Verification on isolated schema 057: 42 API integration tests, nine schema
integration tests and 16 county configuration tests pass; Dagster definitions
validate. The first migration attempt exposed a removed schema-054 column;
corrected before the successful migration. Coverage assertions were updated to
the reduced inventory rather than preserving misleading counts.

Migration 057 has NOT been applied to the real local dataset or production.
Affected stored proceedings and any downstream derivatives still require
quarantine/re-versioning review, and replacement York sources need jurisdiction,
board, document-date and acquisition review before resumption. This containment
does not make the project feature ready for broad backfill.

## Continued review: retained extraction context policy

Pausing acquisition alone was insufficient for retained extractions. The shared
parcel context query checked municipal derived permission only in its address
matching branch; exact PIDN matches bypassed that check. The entity context query
had no equivalent municipality check. These paths could reuse paused evidence
in later generated briefs.

Both queries now require current non-paused derived-use policies for the global
proceedings source and the proceeding body before any match is admitted. Entity
context also excludes internal underscore-prefixed extraction records, matching
the parcel query. A shared SQL predicate keeps these requirements aligned.

Six transactional PostgreSQL cases exercise both real queries with allowed,
paused, expired, denied, unknown-body and globally-paused policy states.
Fifteen schema integration tests and 48 context unit tests pass. Broad pipeline
verification passes 963 tests with 61 integration tests deselected. Four stale
month-only filename expectations were reconciled with the concurrent parser
change that correctly returns no exact date instead of inventing the first day.
No model calls or real-data writes were made.

This closes the shared context-query bypass. It does not certify every cached
brief/event serving path; the downstream serving audit and historical
wrong-county record repair remain outstanding.

## Continued review: persisted event serving policy

The feed previously checked global source permissions but not a proceeding
event's municipal policy. A previously generated event could therefore remain
visible after its municipal source was paused. Project case files, directory
search and watch inboxes share this feed path.

The feed now requires each proceeding event to resolve to a retained extraction,
a current proceeding and a current non-paused municipal policy permitting
derived use. Unknown bodies, missing provenance, expired permission and internal
extraction rows fail closed. This happens in SQL before ordering/pagination;
non-proceeding events keep their existing behavior.

Five real API cases verify immediate exclusion for paused, expired, denied,
retired and unknown-body states across feed/project detail/project search.
Restoring valid policy restores the unchanged event without a rebuild. An
authenticated inbox test verifies a previously stored notification disappears
after a municipal pause. All 48 API database tests and 103 API unit tests pass.
The synthetic fixture now names a reviewed body so it supplies genuine policy
provenance instead of relying on an unreviewed body being admitted.

Concurrent migration 058 arrived during verification, adding metadata review
history and three further source pauses. API coverage expectations now match
its 104 conditional and 18 paused municipal policy rows. Integration verification
used schema 058; this does not certify the new metadata-repair workflow.
No migration was applied to the real local or production databases in this pass.
Cached brief serving and complete metadata/quarantine propagation remain open.

## Continued review: metadata readiness propagation

Migration 058 introduced metadata review status, but downstream queries did not
consume it. A review-required proceeding could still be selected for Pass 0,
included in parcel/entity context, projected into an event and served.

The pipeline now shares one proceeding eligibility predicate: metadata status
ready plus current derived-use permission at global and municipal levels.
Pass 0 selection, parcel/entity context and event generation use that predicate.
The API's serving check also requires ready metadata. Unreviewed, review-required
and quarantined records cannot be used merely because a retained extraction or
event already exists. Synthetic fixtures explicitly establish readiness.

Nine real-database policy/status cases exercise all four pipeline SQL queries;
API cases cover all three non-ready statuses through feed/project detail/search.
Fresh results: 984 pipeline tests pass (64 integration deselected), 18 schema
integration tests pass, 51 API integration tests pass, and Dagster definitions
validate. One existing Dagster run_id deprecation warning remains.

The audit test now compares the decision receipt's policy version to the actual
current version instead of assuming version 1 forever. Migration-058 policy
inventory assertions were reconciled. Concurrent source-config edits reduced
active configuration to 104 entries/102 URLs across 64 municipalities, with 62
governing-body municipalities; fresh configuration tests pass.

No real-data metadata review was applied. Existing unreviewed data intentionally
requires review before intelligence processing. This verifies propagation of the
review result, not the metadata classifier's accuracy, repair-script retry
behavior, cached-brief handling or production release.

## Continued review: incremental metadata repair

Repair duplicate detection originally considered only the current unreviewed
batch. Once the first copy was reviewed and excluded from subsequent input
selection, an identical later document could be accepted again.

Repair planning now loads current ready records from the same review version
as a comparison baseline. Exact normalized text is compared within the same
verified body and meeting date; the previously retained record wins. Baseline
IDs and source fingerprints are included in the reviewable plan, so apply-time
recomputation rejects changed baseline evidence. Apply locks these baseline
rows alongside candidate rows/policies. Console summaries omit the potentially
large baseline list; the plan retains it for review.

Verification: 22 focused quality tests and six real-schema repair integration
tests pass. A two-batch test proves the later duplicate is quarantined while
the earlier ready replacement remains current. Existing tests verify original
source bytes/metadata preservation, append-only review history and refusal to
repair records with existing extractions. The integration fixture now explicitly
refuses any database other than countyiq_test.

No real-data repair was performed. Cross-version deduplication and the
classifier's source/date/body accuracy still require review; exact-text
deduplication does not establish that translated or slightly changed packets
describe distinct meetings or projects.

## Continued review: cached brief citation validity

Parcel and owner brief routes previously served cached narratives even if a
directly cited signal had been rejected or removed. Owner receipts could still
describe that signal as validated, creating false confidence.

Serving now requires every stored signal citation to resolve to evidence with
confirmed, upgraded or downgraded validation status. Parcel citations resolve
within that parcel; owner signal citations resolve within the brief's cited
parcels. If a citation cannot be supported, the optional brief becomes null while
the property/owner record remains available. No model call is triggered.

Real API tests reject and temporarily remove a cited signal, verify both brief
surfaces disappear, restore the signal, and verify the unchanged briefs return.
All 53 API database integration tests and 103 API unit tests pass.

This validates direct cited signal availability only. Existing brief references
do not capture complete versioned municipal dependency graphs; an upstream
source pause can still require signal invalidation and cached narrative repair.
Do not treat the direct-citation check as complete transitive provenance or
freshness verification.

## Continued review: operator documentation consolidation

The LLM release note retained actionable access-code and migration-055 instructions
after that flow was replaced. Removed those obsolete steps, linked the account
guide and operations runbook as the maintained configuration/deployment sources,
and labeled the original test log as historical. The review's top-level plan now
exposes the current outstanding acceptance work instead of showing only completed
baseline passes. Relative documentation links and whitespace were checked; this
documentation-only pass changes no runtime behavior.

## Continued review: metadata source-origin verification

Metadata planning checked policy permission but omitted its allowed_origins.
Recognizable board/date text could receive ready status even when a retained
listing or document URL came from an unapproved origin.

Planning now loads approved origins and checks both URLs with the same origin
normalizer used by acquisition policy. Unknown, empty, relative, deceptive-host
and wrong-scheme origins remain review-required. Separately reviewed document
hosts continue to work. The review version advances to proceeding-metadata-2 so
older reviewed rows are eligible for re-evaluation rather than skipped forever.

Fresh checks: 31 metadata quality tests and six repair integration tests pass.
Concurrent additions to the quality suite are included in that current count.
No source collection, paid inference or real-data metadata application occurred.

Advancing the review version does not itself change previously stored ready
annotations. Operators must regenerate/review/apply the new plan; records with
existing extractions still require derivative review before repair. Complete
real-data revalidation remains a launch gate.

## Continued review: real local metadata state revalidated

Read-only inspection at 2026-09-04T22:05:20Z found the real local countyiq database
on migration 058 with all current proceedings annotated under
proceeding-metadata-2. This supersedes earlier observations that real metadata
application had not occurred. It was not performed by this review pass.

A fresh read-only version-2 plan contains zero pending rows. That means the
current version has been applied, not that all records are ready. Current state:

| State | Count |
|---|---:|
| Ready and eligible under current source policy/date checks | 3,267 |
| Distinct bodies represented by eligible records | 74 |
| Eligible documents dated in 2026 through observation time | 501 |
| Current records still requiring review | 3,192 |
| Proceeding extractions | 0 |

The largest overlapping review reasons are unverified primary board (1,964),
unverified exact date (1,660), insufficient text (1,204), and conflicting header
dates (585). Issue counts overlap and must not be added as distinct documents.
The ready count is a deterministic eligibility result, not a manual correctness
audit or a count of useful projects.

Artifacts: output/metadata-review-v2-20260904T220450Z.json and
output/metadata-coverage-20260904T220450Z.json. The plan contains no source-text
copy; its baseline fingerprints bind current ready records. No database writes,
model calls, source collection or production changes occurred in this pass.
Representative source validation and a separately authorized extraction canary
remain necessary before any claim of a populated project discovery workflow.

## Continued review: sampled metadata false positives

Inspected the first 1,800 text characters of six currently eligible 2026
documents selected by md5(id::text). Four headers supported the recorded body
and date. Two exposed metadata-readiness errors:

- Record 2226 is an East Manchester supervisors/planning-commission joint
  workshop, but had ready status under one board.
- Record 7531 has a Hallam header dated January 5 while its document slug says
  january-6th-2026. Spelled month dates separated by hyphens were not recognized,
  so the conflict was missed.

Joint meeting/workshop/session headers now require review. Exact spelled month
dates support spaces, hyphens and underscores, exposing header/filename
conflicts without inventing dates for month-only names. Metadata review version
advances to 3 so prior rows can be re-evaluated. No real record was changed.

Re-evaluating those exact source rows holds both problematic records and leaves
the other four ready. Evidence, original/current review results, URLs and source
fingerprints are saved in output/ready-metadata-sample-20260904.json. This limited
header sample is not a statistical countywide accuracy estimate and does not
validate the full packets or extraction output.

Verification: 105 focused parser/quality tests and 998 broader pipeline tests
pass (71 integration tests deselected in the broad run). The previous 3,267
eligible count remains an observation of stored version-2 status, not proof
that every record passes the stronger current classifier. Version-3 real-data
review/application remains outstanding.

## Continued review: verified local holds for sampled defects

Prepared output/verified-metadata-holds-20260904.json for records 2226 and 7531
after confirming unchanged source fingerprints and zero dependent extractions.
The plan proposed annotation-only holds for joint_meeting and
header_filename_date_conflict, without changing source fields or validity.

The attempted local transaction encountered the audit ledger's uniqueness
constraint because version-3 reviews had already been applied by concurrent
work. The transaction rolled back; it was not retried. Fresh read-only inspection
confirmed both current records already have the intended review-required status,
unchanged source fingerprints, and append-only version-3 audit entries dated
2026-09-04T22:08:54Z.

Executed the actual shared eligibility predicate and Pass 0 selection against
the real local database: neither held record is returned. This verifies these
two specific false positives are contained in current local data. It does not
certify the rest of the corpus or production. No write from this attempted
transaction committed, and no source text or record identity was changed.

## Continued review: current web release image

Built countyiq-web:review-current-20260904 from the current worktree using the
production Dockerfile. The build ran and passed 21 frontend runtime tests,
ESLint, TypeScript and Vite production bundling. Caddy configuration validation
passed. Image ID:
sha256:83dfa99ad2a6fd350bce83d9f677a1161086299dc295000d29fa08eacefca676.

Actual loopback HTTP checks on that image verified /app and /organizations
return the SPA with no-cache, the entry JavaScript returns immutable caching
and gzip, and a missing chunk returns 404/no-store rather than HTML. Checked
nosniff, frame-ancestors and removed Server headers. Captured response evidence
is output/web-release-http-20260904.json.

The entry JS is 327.67 kB minified / 103.44 kB gzip. Lazy map chunks remain
826.09 kB / 220.17 kB gzip and 1,025.12 kB / 272.16 kB gzip; the build retains a
large-chunk warning. These are artifact sizes, not measured load-time or
Core Web Vitals results.

The image and HTTP checks cover static packaging/serving. They do not prove a
live Access login, an API-backed customer journey, current backend image
correctness, restored production data or production deployment. The local
review container was stopped after verification; the built image is retained.

## Continued review: current API release packaging

Built countyiq-api:review-current-20260904 using the locked production dependency
set. PyJWT 2.13.0 and cryptography import successfully in the resulting image.
Image ID:
sha256:4561209b9b1cdad380d790743d8b09f263853672d0213cf84ffda5f8dbacbe13.

Started the real two-worker entry point as UID 10001 with a read-only root
filesystem, restricted temporary filesystem, all capabilities dropped,
no-new-privileges and no network. Actual HTTP checks from inside the container:
liveness 200; readiness 503 with database unavailable; unauthenticated session
GET 200; session POST 401; API docs 404. Session responses are no-store and the
Server header is absent.

Evidence: output/api-release-runtime-20260904.json. The temporary API container
was stopped after checks; the image is retained. This proves packaging and
fail-closed startup behavior without a database. It does not prove a connected
database journey, live Access token verification, production deployment or
restore readiness.

## Continued review: packaged API with restricted database role

Connected the previously built API image to the isolated review database using
countyiq_api_test, under the same read-only filesystem/capability restrictions
used for the offline runtime check. Actual HTTP requests returned 200 for
readiness, metadata, address search, property report (including its valid cached
brief), development feed and organization directory.

Inside the packaged application, verified current_user=countyiq_api_test,
transaction_read_only=on, no DELETE privilege on staging.parcels, and process
UID 10001. Image identity remains
sha256:4561209b9b1cdad380d790743d8b09f263853672d0213cf84ffda5f8dbacbe13.
Evidence: output/api-connected-runtime-20260904.json.

This establishes connected packaging for the sampled public API paths with
synthetic data and the restricted role. It does not establish live Access
authentication, production networking, source coverage or restore evidence.
Only the review API and isolated review database containers were started; they
were stopped after verification, retaining the database volume and image.

## Continued review: unnecessary feed source dependencies

The feed required global parcel, tax, sheriff and municipal permissions for
every request. A municipal pause therefore disabled parcel-only browsing, and
tax/sheriff pauses disabled development-only browsing despite those sources not
contributing events to the requested category.

Category-specific requests now check only their relevant event-source policies,
plus the parcel source needed for linked property context. Mixed requests retain
their existing complete policy checks. This reduces unnecessary availability
coupling without allowing events from a required paused source.

Five real API regressions verify unrelated-source availability and required-source
503 behavior. All 58 API database integration tests and 103 API unit tests pass.
No real source policy was changed; fixtures were confined to countyiq_test and
restored afterward. The earlier packaged-image evidence predates this source
change and is not a new image verification.


## Continued review: cached narrative provenance trace

Confirmed the remaining limitation in the generation path. Pass 2 gathers
proceedings into its context and hashes that context with
pass2_source_fingerprint. However, format_proceedings_context retains descriptive
fields and a source URL without the proceeding/extraction row identity.
signal_validation_batched records evidence_refs from model cross_references,
whose validator accepts signal references. Brief history similarly stores
signal-key references. These are not immutable versions of the upstream inputs.

The existing API direct-citation checks therefore remain useful but incomplete:
a current accepted signal with the same key can satisfy a cached brief even
though the upstream inputs or accepted inference have changed. The context hash
supports regeneration decisions; it does not establish serving-time dependency
validity. Complete upstream invalidation remains an open release requirement.

A repair needs explicit immutable dependencies recorded when accepting each
inference, checks that those dependencies remain current/usable, and a defined
legacy-cache transition. Acceptance should include changing a cited proceeding,
pausing its policy, replacing an accepted signal under the same key, and checking
both parcel and owner narratives before any regeneration. Do not treat a new
signal-key existence check as completion of this requirement.

## Continued review: extracted meeting-date whitespace regression

The recent addition of hyphen/underscore support restricted spelled-date
separators to spaces and tabs. This lost the previous recognition of dates split
across lines or containing nonbreaking spaces, which occur in extracted document
headers. Restored general whitespace support while retaining filename separators.

Added a regression for newline, CRLF and nonbreaking-space dates. It failed
before the fix (January newline 6 comma newline 2026 returned no date).
All 106 parser and metadata-quality tests pass afterward. This is a code fix;
no stored source record or metadata review was changed by this check.


## Continued review: preserve proceeding dependency identities

Implemented the first prerequisite from the provenance trace. Both shared
proceeding-context queries now select the proceeding ID and accepted extraction
inference ID alongside the existing extraction ID. The context formatter
preserves all three rather than discarding them. Pass 2 fingerprints therefore
distinguish replacement source versions even when their descriptive text matches.

Pass 2 history now also records deterministic proceeding:, extraction: and
inference: references from the gathered proceeding context, in addition to
validated model signal citations. These describe supplied context, not a claim
that the model cited every row. Prompt renderers retain their descriptive output;
the new identifiers are audit data. Missing legacy identifiers are not invented.

Verification: 56 focused context/validation tests, all 1,000 non-integration
pipeline tests, Dagster definitions load validation, and 18 real database schema
integration tests pass. The regression substitutes each source identity while
holding descriptive text constant and requires a changed fingerprint. Database
checks used only the isolated review countyiq_test instance on port 5434; it was
stopped afterward with its volume retained.

This does not yet implement serving-time transitive invalidation or migrate
legacy history. It provides source identities for the next dependency checks.
No inference invocation, source repair or production migration was performed.


## Continued review: serving checks for recorded proceeding dependencies

Added a shared API SQL predicate to the parcel and owner brief citation checks.
When supporting signal history records extraction dependencies, each extraction
must still resolve to a current, metadata-ready proceeding, a permitted and
unexpired global/municipal policy, and the recorded active extraction inference.
Internal extraction rows and quarantined supporting validation history cannot
satisfy the check. A removed active extraction inference is also invalid.

Six real database/API cases verify paused municipal policy, retired proceeding,
unreviewed metadata, replaced extraction inference, removed extraction inference,
and an extraction changed to an internal marker. Both brief endpoints first
serve valid evidence, hide the narrative after the change, and recover after
fixture restoration, without running regeneration. Parent property/owner
responses remain available. All 64 API integration tests and 103 API unit tests
pass. The review-only database was stopped afterward; its volume is retained.

The first focused run exhausted the shared owner-read test bucket; the test
module now installs a fresh limiter with production defaults for each case.
No production rate-limit behavior changed.

Scope remains explicit: this checks dependencies already recorded on the current
supporting signal validation. Legacy history without extraction references is
not certified, and a brief still needs to bind to the exact signal inference used
at generation rather than whichever accepted signal currently shares its key.
Complete narrative provenance remains open; these tests do not prove it.


## Continued review: bind briefs to original signal versions

Parcel and owner brief generation now retains each supplied signal's active
inference ID in the source fingerprint and records signal-version references
containing PIDN, signal key and inference ID. All supplied signal context is
bound, including signals not explicitly cited in prose. Missing or malformed
inference identity raises before the paid brief invocation instead of generating
a narrative with an invented dependency.

Both API brief checks verify these recorded versions against current accepted
evidence and the proceeding dependency predicate. Replacing a validated signal
under the same key therefore invalidates an older versioned brief even when its
text and status are unchanged. Owner source hashing now includes inference
identity; the old rendered-prompt comment was corrected to match actual behavior.

Verification: 65 API integration tests, 103 API unit tests, all 1,001 pipeline
non-integration tests and Dagster definitions validation pass. The new real API
regression holds signal text/key constant, changes only the active inference ID,
and requires both cached briefs to disappear while parent responses remain 200.
A pipeline unit test checks parcel/key/version binding and rejects legacy or
malformed IDs. An initial test failure was a missing pytest import in the new
test, corrected before the successful run.

No LLM invocation, live migration or production deployment occurred. The isolated
review database was stopped with its volume retained. Legacy briefs lacking
signal-version references remain an explicit unresolved transition requirement;
this change does not retroactively certify their generation inputs. Complete
provenance for other supplied context (portfolio, entity and source fundamentals)
also remains to be assessed.


## Continued review: inference acceptance and subject integrity

Found and corrected a gap in the new serving predicate: a matching referenced
extraction inference ID was sufficient even if that history entry was
quarantined, described another output kind, or belonged to another proceeding.
Supporting signal history likewise needed kind, pass and subject checks.

The shared predicate now requires supporting history to be Pass 2 signal
validation for the supporting PIDN, and referenced extraction history to be an
accepted Pass 0 proceeding extraction for the actual proceeding ID. Existing
policy, metadata, projection-version and citation checks remain in place.

Five new real API regressions deliberately keep reference IDs and projection IDs
consistent while supplying quarantined extraction history, the wrong extraction
kind/subject, or the wrong signal kind/subject. All five served a brief before
the fix and hide it afterward. The earlier extraction fixture was corrected to
use actual Pass 0/proceeding history identity rather than a signal-history stub.

All 14 brief validity tests, all 70 API integration tests and 103 API unit tests
pass. Test mutations were restored in countyiq_test; immutable synthetic history
was appended, not rewritten. The isolated database container was stopped after
verification. No real data or production configuration was changed.

Legacy histories without version receipts and provenance of non-signal context
remain open requirements; these results do not establish full narrative or
production readiness.


## Continued review: legacy brief serving transition

Changed brief serving from an absence-of-invalid-references check to a positive
requirement: accepted Pass 3 brief history must exist, contain signal-version
references, and pass current dependency checks. Missing history, empty receipts
and old signal-key-only receipts no longer certify cached narrative text.
Stored rows/history remain intact; parent property and owner responses remain
available. No generation is triggered by reads.

Read-only local countyiq coverage inventory found zero parcel briefs and zero
owner briefs at this check. Evidence: output/brief-version-coverage-20260904.json.
That observation is local, not a production inventory. An environment with
legacy rows will hide those narratives until authorized versioned regeneration;
do not backfill dependency IDs from today's evidence as if they were original
generation inputs.

Contract fixtures now explicitly attach accepted synthetic validation and brief
history. Three new real API cases cover missing history, empty receipts and
signal-key-only receipts, prove stored text is preserved, and confirm valid
serving after restoration. Earlier provenance cases rebind their synthetic brief
receipts when isolating an invalid upstream history, so a mismatched brief ID
cannot accidentally make those tests pass for the wrong reason.

All 73 API integration tests and 103 API unit tests pass. The isolated test
database was stopped after verification with its volume retained. No real
database row, production configuration or inference budget was changed.

This closes the permissive legacy-brief serving fallback. It does not certify
legacy signal validations or complete provenance for non-signal context such as
portfolio facts and entity verification. Those remain separate acceptance work.


## Continued review: brief history must match its projection

Closed an additional identity gap: accepted history with valid signal references
could authorize a cached brief for another subject or the other brief type.
The shared predicate now requires an exact output-kind and subject match supplied
by the route. Parcel history uses the PIDN; owner history uses the generator's
existing owner_brief: plus truncated SHA-256 canonical-name identity.

Four real API regressions clone valid history while changing only its subject
or brief kind, attach that history to a projection, and require the narrative to
be hidden. All four failed before the fix and pass afterward. Valid history
restoration makes the brief visible again. Contract/legacy fixtures now use the
correct owner history subject so unrelated identity errors cannot accidentally
satisfy legacy-reference tests.

All 77 API integration tests and 103 API unit tests pass. After tightening the
legacy fixture identity, all 21 brief-validity tests pass again. The isolated
review database was stopped, retaining its volume. No production deployment,
real-data mutation or inference invocation occurred.


## Continued review: owner context invalidation and acceptance scope

Owner briefs use canonical owner identity, entity type, portfolio PIDNs and parcel
count in addition to signal context. Generation now records a canonical
owner-context fingerprint in immutable history. Serving reconstructs that same
owner/portfolio context and requires a matching fingerprint. Missing legacy
owner-context receipts cannot certify a portfolio narrative.

Three real API cases change entity type, replace a portfolio member while keeping
the count constant, and add a portfolio member. The owner brief disappears
without changing signal IDs or running generation; the property's independent
brief remains available. Restoring the context restores owner brief serving.

All 80 API integration tests, 103 API unit tests, 1,010 non-integration pipeline
tests and Dagster definitions validation pass. The isolated review database was
stopped with its volume retained. No real-data change or paid inference occurred.
This covers owner identity/portfolio inputs; municipality facts rendered with
signal context and the separate parcel brief context remain to be validated.

Corrected the live plan's scope: observed customer interviews are a recommended
product follow-up, not an engineering acceptance gate or authorized outreach.
The requested customer-value assessment remains in this review, explicitly
identified as evidence-based hypotheses rather than customer research. The
production readiness, UI/UX, simplification, infrastructure and bug-fix scope
remains intact.


## Continued review: owner brief municipality context

Confirmed a stale-context defect: correcting the current municipality for a
signal parcel did not hide its cached owner narrative, even though that label is
rendered directly in the owner prompt. The new real API regression failed before
the fix.

Owner context v2 now includes the PIDN-to-municipality mapping for all supplied
signal parcels, alongside owner identity and portfolio membership/count/type.
Serving reconstructs labels for the recorded signal PIDNs and requires the same
fingerprint. Unknown labels normalize consistently, and signal ordering does not
change the fingerprint. Generation's source hash includes this expanded context,
so an older receipt cannot prevent regeneration through an unchanged-input skip.

All 81 API integration tests, 103 API unit tests, 1,011 non-integration pipeline
tests and Dagster definitions validation pass. The municipality case proves
invalidation and recovery without changing signal versions or invoking inference.
A pipeline regression also verifies changed labels alter the fingerprint while
row order does not. The isolated database was stopped, retaining its volume.

The v2 receipt supersedes the earlier owner-only receipt; no retroactive
dependencies were invented and no real cached rows were rewritten. Separate
parcel-brief inputs and upstream signal context still require completion of the
provenance review.


## Continued review: coherent snapshots for model context

Found a concurrency prerequisite while tracing parcel context: DatabaseResource
dict_cursor explicitly uses autocommit, so multi-query context gathering could
combine property, entity, portfolio and signal data from different committed
database states. A later fingerprint would not establish a coherent original
input snapshot.

Added DatabaseResource.read_snapshot using a short REPEATABLE READ, READ ONLY
transaction with dictionary rows. Pass 2 context gathering and both Pass 3 brief
generators now use it. The scope ends before prompt/model work; no database
snapshot is retained through inference. Existing transaction cleanup restores
autocommit on success and error.

A real two-connection regression commits an update during the first snapshot and
proves repeated reads retain the original value, then proves the next snapshot
sees the new value. It also rejects writes, verifies autocommit restoration after
the rejection, and verifies continued connection usability. Its uniquely named
test-only table was dropped afterward.

All 1,011 non-integration pipeline tests, 19 schema integration tests and Dagster
definitions validation pass. The isolated database was stopped with its volume
retained. No production data or schema was changed. This resolves mixed-state
input gathering; full parcel-context fingerprinting remains the next dependency
work rather than being claimed complete by the snapshot check.


## Continued review: shared parcel brief source context

Migration 059 centralizes parcel brief non-signal inputs in
meta.parcel_brief_sources: current property facts, selected entity graph/version,
resolved owner names, portfolio membership, aggregate assessed value and current
portfolio tax total. Its companion fingerprint function hashes the same JSONB
using PostgreSQL SHA-256. Both functions use caller permissions (no security
definer). The migration changes no source records.

Generation now formats the returned facts, replacing its separate property,
entity, owner-name and portfolio queries, and records the exact source fingerprint
in parcel-context:v1 history. Its existing read snapshot also covers the validated
signals query. Serving requires the stored fingerprint to equal the current
database-defined fingerprint. The API therefore does not duplicate the name
resolution or portfolio aggregation algorithm. Legacy briefs missing this receipt
remain stored but hidden; API reads do not generate new text.

Five real API cases change property assessment, entity type, owner aliases,
portfolio ownership and tax total while retaining signal versions. Each hides
the cached parcel brief, with recovery after source restoration. A pipeline/
database integration test checks the gathered values and exact fingerprint
agreement, then verifies an assessment change updates both value and fingerprint.

Verification: 86 API integration tests, 103 API unit tests, 1,011 pipeline
non-integration tests, 20 schema integration tests and Dagster definitions
validation pass. Migration 059 was upgraded, downgraded to 058 and upgraded again
only in the isolated countyiq_test database on port 5434. The isolated database
was stopped with its volume retained. Real local countyiq and production were
not migrated, and no inference was invoked.

This covers the parcel brief's directly supplied non-signal context. Complete
upstream validity of signal/entity validations, projection/history payload
agreement and final release/host evidence are not established by this check.


## Continued review: consistent profile serving snapshots

Property and owner profile routes now request a REPEATABLE READ, READ ONLY
snapshot from the API connection pool. Previously each query could observe a
different committed state, allowing policy/history checks, source fingerprints
and displayed profile facts to straddle a concurrent refresh. The optional
snapshot mode is limited to these multi-query profiles; write cursors retain
their existing behavior. Combining snapshot and write mode is rejected before
a connection checkout.

A real two-connection API test using the restricted role verifies stable reads
across a committed concurrent property update, visibility of that update in the
next snapshot, refusal of writes, and restoration of normal read/write and
read-committed settings on a later write-mode checkout. Transaction options do
not leak through the pool.

All 88 API integration tests and 103 API unit tests pass. The isolated test
database was stopped with its volume retained. No real-data or production
configuration change occurred. Consistency is relative to each request snapshot;
this does not claim a response can reflect a commit made after its snapshot.


## Continued review: packaged API with context validation

Built countyiq-api:review-context-20260904 from the current API Dockerfile.
Image identity:
sha256:b8f80afe04eb7f64b0a7a13ea98547e579ea9559fd2987b1f75b4f9a51448333.
Ran it with a read-only root filesystem, bounded /tmp tmpfs, dropped capabilities,
no-new-privileges and UID 10001, connected only to the isolated review database.

Actual HTTP requests returned 200 for liveness, readiness, metadata, development
feed and valid parcel/owner briefs. Changing the fixture property's assessment
hid its parcel brief; restoring the assessment restored serving. Changing the
fixture owner type hid its owner brief; restoration restored serving. No
generation ran. The synthetic database mutations were restored.

Inside the packaged application, confirmed countyiq_api_test, read-only
repeatable-read profile transactions, permission to execute the new fingerprint
function, no DELETE privilege on staging.parcels, and UID 10001. Server response
headers were absent. These direct-origin public routes did not include
Cache-Control; the inspected Caddy /api/* handler supplies no-store at the proxy,
while the API itself supplies it for session/workspace routes.

Evidence: output/api-context-runtime-20260904.json. The review API and isolated
database containers were stopped; image and database volume were retained.
This is packaged local behavior against synthetic data and migration 059, not
production deployment, live Access authentication, restore or real-source
coverage evidence.


## Continued review: workspace recovery UX and current product value

Refreshed the feature assessment to reflect implemented account-backed workspaces
instead of recommending server persistence as future work. Saved investigations
remain a core retention feature; the next value comes from reliable recovery and
useful recurring coverage, not more account/team surfaces.

Found an account error-state bug: a failed initial session request produced a
null account and the workspace page described sign-in as disabled on a local
preview. It now distinguishes unavailable account status, offers an explicit
retry, and recovers to the configured invited-account sign-in state.

Firefox verified synthetic 503-to-success recovery and absence of the misleading
disabled message. Mobile visual inspection also exposed a shared negative margin
pulling research buttons over the sign-in panel border. Workspace-specific
spacing fixes the overlap; the repeated browser run asserts at least 12px
separation at 390px width.

Verification: TypeScript build checking, lint and all 21 frontend tests pass.
Browser artifacts: output/playwright/workspace-account-recovery.cjs,
workspace-account-unavailable.png and workspace-account-recovered-mobile.png.
The temporary Vite server and review browser were stopped. These were synthetic
session responses, not live authentication; no account was changed. The prior
packaged web image predates these UI changes.


## Continued review: atomic signal replacement and validation retraction

Found an inter-job stale-evidence window: development_signals committed its
replacement facts while validation retraction waited until a later Pass 2 job.
Cached briefs and momentum consumers could therefore still find old accepted
evidence between those jobs.

Moved the existing retraction SQL to intelligence_common and reused it inside
the deterministic signal rebuild transaction, before commit. Source replacement
and removal of validations for changed/missing signals now commit together.
Pass 2 retains its defensive retry-time cleanup using that same rule. Rebuild
metadata reports the number of retracted validations.

A lifecycle regression verifies retraction precedes commit, and retraction
failure rolls back the rebuild and restores connection mode. A real database
case verifies changed/missing signal evidence is deleted while age-counter-only
changes retain validation. Test setup initially violated PIDN length and a
required source_table field; both fixture issues were corrected before the
passing checks.

All 1,012 non-integration pipeline tests, 21 schema integration tests and Dagster
definitions validation pass. The database regression rolled back its fixture and
the isolated database was stopped afterward. No real signal rebuild or paid
inference was run.

This closes the gap between a completed rebuild and later validation startup.
An older validation already in flight can still need publication-time freshness
checks; that separate concurrency boundary is not claimed solved here.


## Continued review: validation publication freshness

Pass 2 previously wrote a completed inference's evidence projection without
checking whether its gathered inputs changed while inference was running.
An older completion could therefore republish evidence after a deterministic
signal rebuild had correctly retracted it.

Before deleting or upserting evidence, publication now starts a repeatable-read
transaction, acquires a shared lock on development_signals, re-gathers the parcel
context and compares its source fingerprint with the original inference input.
A mismatch raises before projection mutation and follows the existing persisted
error/retry path. Signal replacement cannot interleave between this check and
commit. The lock has a five-second acquisition timeout and is held only for
database gathering/publication, never during inference.

A real two-connection test changes source evidence after initial gathering and
proves publication is rejected. With current context, it proves the exclusive
lock used by signal replacement cannot be acquired during publication, then can
be acquired after publication exits. Connection mode is restored and test signal
rows are removed afterward.

All 1,012 non-integration pipeline tests, 22 schema integration tests and Dagster
definitions validation pass. The isolated test database was stopped afterward.
No real signal publication or paid inference ran.

This closes the late-publication race against deterministic signal replacement.
The snapshot provides coherent other-source reads at publication, but does not
lock every upstream source against later changes; ongoing upstream invalidation
remains distinct from this transaction guarantee. The proposal history remains
an immutable record of the completed inference even when projection publication
is deferred.


## Continued review: pilot attribution and migration integration

The municipal pilot report now supplies concrete evidence for the product-value
assessment. Thirty frozen documents produced 108 candidate outputs; only 32
survived the whole-document evidence gate. Street-only references attached
unrelated parcels, agenda templates sometimes became false completed actions,
and related documents frequently split project identity. Project discovery can
save customer research time, but incorrect parcel attachment, stage and date
claims can erase that value. These findings support keeping document evidence
visible and withholding unverified project conclusions from publication. The
pilot is a qualitative diagnostic sample, not a measured customer outcome or a
representative accuracy benchmark. See municipal-llm-pilot-results-2026-09-04.md.

A conservative address-specificity function was added in migration 060. A
concurrent task introduced the broader structured evidence/parcel matcher and
renumbered its migration to 061, following 060. The initially proposed removal
of duplicate 060 and isolated database history rewind was rejected by automatic
approval review. The user subsequently approved that isolated cleanup, but the
concurrent renumbering made deletion and rewind unnecessary: both migrations
were retained and 061 was applied normally to countyiq_test on port 5434.
No real source database or production migration was changed by this review.

Read-only replay of the initial conservative function against 108 archived pilot
references reduced matched outputs from 29 to 24, removing 22 parcel links from
five outputs. Replay of the concurrent structured matcher increased matched
outputs from 29 to 45, changing 26 outputs. This increase reflects additional
address/ID handling; it is not proof that the new links are accurate. The replay
artifacts are output/municipal-pilot-2026-09-04/address-specificity-replay.json
and structured-address-replay.json. No new inference or publication ran.

Integration checks now cover broad streets, ambiguous duplicate addresses,
municipality boundaries, explicit multiple parcel IDs and actual event/context
queries. Policy fixtures were corrected to include a current parcel in the
source jurisdiction. API fixtures now explicitly associate their synthetic
proceeding bodies with the synthetic parcel municipality, preserving existing
policy-revocation tests. The API source count includes this one synthetic body.

Fresh verification: 1,025 non-integration pipeline tests passed; 33 schema and
attribution integration tests passed with the isolated database explicitly
selected; Dagster definitions validation passed; 88 API integration tests and
103 API unit tests passed. The two API directories must currently run separately
because they contain duplicate pytest module basenames. One Dagster run_id
deprecation warning remains in the integration run. The isolated database is
stopped after verification, with its volume retained.

Remaining work includes reviewing the newly linked pilot records for precision,
validating corrected extraction on held-out documents, and resolving the live
host readiness issues already recorded above. Retaining both migrations also
leaves the older address helper present although application queries now use
the structured matcher; any later removal should be an explicit ordered schema
change. These checks establish integration compatibility, not overall production
readiness or permission to publish pilot output.


## Continued review: attribution method follows the actual match

The property report and municipal signal query used the shared structured
matcher to select parcels, but independently guessed the match method from the
legacy free-text reference. A structured list of explicit parcel IDs could
therefore attach correctly while claiming an address match. This affected the
customer evidence explanation and the evidence supplied to later validation.

Both consumers now join the shared matcher and use its returned match_method.
The API retains its existing pidn/address response vocabulary; deterministic
signals retain pidn/normalized_address. This removes duplicate attribution
logic without changing that public contract. A real API regression supplies a
structured multi-ID reference whose legacy text contains no ID and verifies a
pidn label. A transaction-scoped signal regression verifies both explicitly
identified parcels retain pidn evidence. Existing address tests still pass.

Fresh verification: 89 API integration tests, 104 API unit tests, 11 attribution
integration tests and 1,027 non-integration pipeline tests passed. Concurrent
app-subdomain deployment edits briefly left two older fixture expectations
failing; their author updated those fixtures and the final broad run passed.
All database checks used the isolated review database on port 5434. It was
stopped afterward with its volume retained. No production deployment or paid
inference ran. New pilot matches still require accuracy review; correct method
labels alone do not establish that every extraction or project conclusion is
correct.


## Continued review: split-host development routing

Current Caddy, tunnel and release validation agree on marketing at DOMAIN and
product/API traffic at app.DOMAIN. The Vite router had two entry discrepancies:
the exact app-host /api path was rewritten to product HTML, while app-host
/index.html loaded marketing HTML. Public /app.html also bypassed the intended
redirect to the product host. Explicit API pass-through and entry handling now
match those production routes.

Four HTTP tests start the actual Vite server on an ephemeral port with a
synthetic upstream API. They verify API root/descendant forwarding, public-host
API rejection, public product-entry redirects, and product HTML for app index
and nested routes. All 25 frontend tests, TypeScript, lint and the production
build pass. The existing large map chunk warning remains. A Firefox navigation
from localhost:5174/app.html landed at app.localhost:5174/ with the workspace
shell; app.localhost:5174/index.html also rendered the workspace. This check had
no review API running, so API fetch failures were expected and it is not live
account acceptance evidence. The dedicated browser and Vite process were
stopped after inspection. No production routing or deployment was changed.


## Continued review: receipts must not invent verification

Property proceeding receipts and normalized legacy feed receipts claimed that
CountyIQ had verified the displayed excerpt against the source. The legacy feed
normalizer receives neither source text nor an authoritative verification receipt;
its inputs alone cannot establish that claim. Property receipt construction also
made the same unconditional assertion. Current ingestion performs source-text
checks, but that does not certify every retained historical projection.

Both receipt methods now describe extraction and direct readers to the source
passage for context, without asserting an unproven verification step. Current
ingestion validation remains unchanged. The existing legacy-receipt unit test
previously required the misleading word; its expectation now reflects the actual
information available to the normalizer. All 109 API unit tests pass.

This is a customer-trust correction, not a substitute for validating legacy
publication eligibility. It makes no new guarantee of semantic accuracy, source
membership, current inference provenance or complete coverage. No database,
production or inference operation was performed for this correction.


## Continued review: property proceeding eligibility

The property report's linked_proceedings query checked current source rows and
parcel attribution but omitted metadata readiness, municipal policy expiry and
paused status. Thus records hidden from Feed after quarantine or policy changes
could still appear on a property. The shared parcel matcher checks jurisdiction
and derived permission; it is not the full publication policy boundary.

Property links now require ready metadata and a current, non-paused municipal
policy permitting derived use. The existing global source guard remains in the
same repeatable-read report transaction and continues returning 503 when the
whole source is unavailable. Obsolete municipality pattern construction and
unused query parameters were removed now that the shared matcher owns linking.

The existing eight policy/metadata integration cases now check property links
as well as Feed, case files and the project directory, proving immediate hiding
and restoration without a rebuild. Three additional cases verify the existing
global paused/expired/denied 503 behavior. All 92 API integration tests and 109
API unit tests pass. Checks ran on isolated port 5434; the review database was
stopped afterward, retaining its volume. No real records or production state
were changed. Full legacy inference/projection validity remains a separate
acceptance item.


## Continued review: environment publisher hostname drift

The production environment bootstrap and deployment validator require
COUNTYIQ_TRUSTED_HOSTS=app.countyiq.net after the split-host change. The publishing
script still required the marketing hostname countyiq.net, so it would reject
the correctly generated environment before upload. Its assertion now matches
the product hostname.

A command-level regression substitutes both SOPS and SSH with local executable
stubs and synthetic values. It proves that the product hostname reaches the two
expected SSH steps, the obsolete hostname fails before any SSH call, strict host
key checking remains in the command, and credentials are absent from output.
No real secret file is decrypted and no remote host is contacted. Sixteen
account/publisher checks and seventeen adjacent architecture, deployment,
restore and host checks pass; publisher bash syntax validation passes. These
checks validate local release tooling, not live secret publication or account
configuration. No production changes were made.


## Continued review: source audit of newly recovered pilot links

The newer held-out pilot artifact is a metadata-only selection manifest, not an
evaluation result. Held-out accuracy therefore remains unproven. Independent
read-only review of the archived structured matcher replay now checks all 21
newly matched outputs (24 parcel links): each address or explicit ID used for
linking occurs in the frozen source text after whitespace normalization; every
linked PIDN still exists as a current parcel; all 21 outputs agree with the
municipal source jurisdiction. Inspection of the 24 displayed parcel addresses
found correspondence with the reference addresses or explicit identifiers.
The detailed artifact is output/municipal-pilot-2026-09-04/new-link-source-audit.json.

One important partial match remains: source 6302 names three Long Level Road
parcels. Its explicit 35-000-JM-0002.C0-00000 identifier has no exact parcel row,
while 1698 LONG LEVEL RD exists under 35000JM000200. The other two explicit IDs
resolve. This discrepancy needs source clarification; the review did not alter
the source ID or add a guessed association. Customer coverage must distinguish
an unresolved explicit reference from an absent matter or a complete parcel set.

These findings strengthen the location-link evidence for this diagnostic sample
and explain the increase from 29 to 45 matched outputs. They do not establish
semantic correctness of decisions, complete project grouping, representative
recall, or held-out performance. The five removed ambiguous/street-only outputs
remain appropriately unattached. No inference, collection, publication or real
database writes ran. Next quality acceptance work should evaluate the corrected
extraction on held-out documents and explicitly review partial-reference display,
rather than treating more matches as sufficient product readiness.


## Continued review: project parcel scope and accessible links

The project connected-record section displayed only the first twenty parcels,
with a non-interactive additional-count badge. Customers could not open the
remaining parcel links from that section. Its plain Parcels label also did not
explain that attribution can be partial, as demonstrated by the Long Level Road
source-ID discrepancy.

The section now exposes every linked parcel, labels the list Linked parcels,
and explains that matched records do not define a complete project boundary.
It displays distinct structured parcel references from source receipts, falling
back to the legacy reference text when structured data is unavailable. Sources
with references but no matched parcels now have a visible no-linked-records
state. This supports comparison without inventing a replacement ID or claiming
an unresolved reference has been reconciled.

TypeScript and lint pass. A Firefox fixture at 390x844 verified all 21 parcel
links, the original unresolved reference and absence of horizontal overflow.
The changed linked-record section was visually inspected in
output/playwright/project-parcel-references-mobile.png. The fixture uses
synthetic API responses; it proves rendering/accessibility of the list, not
live project completeness. The review browser and Vite server were stopped.
No source data, publication, or production deployment changed.


## Continued review: project CSV preserves uncertainty and scope

Project CSV export previously filled a missing event date with detected_at,
making an undated source action appear dated in an external spreadsheet. It
also omitted the page's truncated-history warning and the actual source URLs.
Exports now separate Event date and Detected at, retain blank unknown event
dates, include distinct source document URLs, and describe whether additional
events exist outside the exported view. Even a non-truncated export explicitly
refers to loaded records rather than complete source coverage.

TypeScript, lint and all 27 frontend tests pass. A Firefox fixture with an
undated event and has_more=true exercised the actual Export CSV button; the
downloaded bytes preserve the blank event date, detection timestamp, original
PDF URL and partial-export scope. The check is reproducible through
output/playwright/project-csv-scope.cjs. The existing CSV formula escaping
remains in use. The browser and dedicated Vite process were stopped afterward;
no production or source-data changes were made.


## Continued review: packaged Caddy startup failure

Building the current web image succeeded, including 27 frontend tests, lint and
TypeScript/bundling. Running that image with Compose's read-only root filesystem,
cap_drop ALL and no-new-privileges failed immediately: exec /usr/bin/caddy:
operation not permitted. The pinned base image installs caddy with
cap_net_bind_service=ep. That executable capability conflicts with the dropped
capability bounding set, even though CountyIQ listens only on unprivileged 8080.

The web Dockerfile now removes this unnecessary file capability at build time.
The rebuilt image starts under the same restrictions. Twenty-one real HTTP
checks pass for separate marketing/product entries, deep-link redirects, public
API rejection, unknown-host rejection, health, bundled assets, missing-asset 404s
and cache/security headers. Inspection confirmed no remaining caddy file
capability. CI now starts the built web image with these production restrictions
and waits for health, failing early if the process exits; its ephemeral container
is removed afterward. Configuration validation alone did not exercise this bug.

Verified image: sha256:37c06f441f39217dce88d259029216022f99a117d99fb5ab0714c1a6161a72b7,
tag countyiq-web:review-packaged-20260904. HTTP evidence is recorded in
output/web-packaged-http-20260904.json. The review container was stopped after
verification. No production deployment occurred. This static packaged check has
no API upstream or Cloudflare Access, so live authenticated journeys and full
release/restore acceptance remain outstanding. The large map bundle warning
also remains.


## Continued review: CI release fixture matches current deployment contract

The deployment-config CI job retained DOMAIN=api.countyiq.test and the same
trusted hostname, conflicting with the split-host requirement app.DOMAIN.
Its inherited disabled-auth setting also conflicted with the current private
alpha requirement for Cloudflare Access. These failures would prevent CI from
reaching the packaged web checks even with correct production code.

The fixture now uses countyiq.test plus app.countyiq.test and explicit synthetic
Access issuer/audience/app-origin settings. The exact current environment
validator reproduced the stale hostname rejection, then the auth rejection;
after correction, validation and real Docker Compose config --quiet both pass.
Twenty-two account/deployment architecture regression tests pass. Temporary
synthetic environment files were used; the workspace .env was not overwritten,
real secrets were not read, and no deployment or remote call occurred.

The full deploy --check command correctly rejects this shared dirty worktree.
That protection remains intact. This verification exercises its environment
and Compose checks directly; it does not claim that the complete hosted GitHub
Actions workflow has run or that the current worktree is an approved release.


## Continued review: current host state and unified API verification

A fresh read-only SSH check confirmed the target still reports password
 authentication enabled, keyboard-interactive authentication disabled, root login
 disabled, and /var/lib/countyiq/cost-guard owned by root with mode 0700. The
cost-guard timer is active, the backup timer inactive, and docker ps lists no
running application containers. The prior host-fix approval remains unresolved;
this check changed no remote files, services or deployment state.

Locally, the API integration and unit directories had one duplicate pytest
module basename: test_development_radar.py. This caused collection failure when
both suites were invoked together. The unit file is now named
api/unit_tests/test_development_radar_unit.py, with its contents preserved.
Both suites run together successfully: 202 tests passed in one invocation against
the isolated review database on port 5434. The database was stopped afterward,
with its volume retained. Earlier notes requiring separate invocations are
superseded by this verified naming correction.


## Continued review: structured-only references and hidden parcel truncation

The current extraction schema permits parcel_reference=null while providing
valid structured parcel_references. Property reports, municipal signals and
event attribution nevertheless filtered out null legacy references before
using the shared matcher. Those obsolete filters are removed; the matcher now
determines whether any valid, municipality-scoped association exists.

The event attribution query also silently limited a matter to twenty matched
parcels. That backend cap defeated the UI's ability to show the complete linked
set. It is removed so every explicit matched parcel can reach the event. Street
specificity, unique-address matching, jurisdiction and source eligibility guards
remain unchanged; no guessed link is introduced.

A real database regression supplies 21 explicit IDs with no legacy reference
and verifies that all 21 reach both the event query and deterministic municipal
signals. The API regression checks structured IDs with null and populated
legacy text. Fourteen attribution integration tests, 1,032 non-integration
pipeline tests and 203 combined API tests pass. Database checks used isolated
port 5434, stopped afterward with its volume retained. Existing persisted events
need a normal rebuild to gain formerly omitted links; this review did not run
real publication, paid inference, or a production deployment.


## Continued review: packaged API behind the packaged proxy

The current API image was built and run as UID 10001 behind the previously
verified Caddy image, with read-only root filesystems, dropped capabilities and
no-new-privileges. The API used the isolated migrated countyiq_test database and
its restricted countyiq_api_test role. Seventeen API contract checks prepared
and verified that fixture before the packaged run.

Nine HTTP checks through Caddy pass: readiness and health return 200; session
reports configured but unauthenticated; unsigned property, feed and current
workspace requests return 401; a malformed Access assertion is rejected; the
marketing host returns 404 for API paths. Responses carry no-store. A direct
in-container database helper check confirms UID 10001, the expected restricted
role, read-only repeatable-read transaction settings and no DELETE privilege
on staging.parcels. The initial workspace probe used an unsupported GET root
and returned 405; the verified check uses the actual /api/watchspaces/current
endpoint.

API image sha256:dffe17d2532dbf3d32ce22b1c928fc325dcc5e0e2a8180df4d0a1c3f7d3a565a; <!-- gitleaks:allow -- public Docker image digest -->
web image sha256:37c06f441f39217dce88d259029216022f99a117d99fb5ab0714c1a6161a72b7.
Detailed evidence is output/packaged-api-proxy-20260904.json. All review containers
were stopped after verification; the database volume was retained. Synthetic
Access issuer/audience settings were used and no external identity verification
was attempted. This proves the local packaged denial/readiness boundary, not
live authenticated customer journeys, production networking or deployment.


## Continued review: missing signal validation history is already excluded

The supporting-proceeding predicate alone uses NOT EXISTS against invalid
history, which could appear to permit a missing history row. Inspection of the
complete serving path shows two additional controls: active inference IDs have
foreign keys, and a cached brief must match recorded non-null signal versions.
A null signal history reference therefore cannot satisfy the brief dependency.

A new actual-response regression removes only the fixture growth signal's
history reference while retaining its accepted status. Both parcel and owner
briefs disappear, their stored rows remain intact, and restoring the original
reference restores serving. All 31 provenance integration tests pass on isolated
port 5434. No redundant production predicate was added. This confirms this
specific missing-history boundary, not full payload-to-history agreement or all
upstream invalidation. The review database was stopped afterward with its volume
retained; no real records, inference or deployment were changed.


## Continued review: cross-signal summaries follow accepted evidence

The property's separate Cross-Signal Insight was served directly from a complete
meta.intelligence_passes row, without the dependency checks used by parcel and
owner briefs. A deterministic rebuild could retract evidence while leaving this
summary visible. The pass-status record alone is not publication evidence.

Serving now requires accepted Pass 2 signal-validation history with the same
parcel, input hash and summary text, a nonempty validation set, and a current
evidence row for every recorded validation under that inference ID. Validation
status and significance must still match; mixed inference versions are excluded.
Recorded proceeding dependencies use the existing current-source guard. Legacy
or malformed history without the required validation set does not qualify.
The existing accepted history supplies this identity, so no migration or extra
stored projection was introduced.

Five real-response cases remove a signal, remove its history reference, change
its validation status, change summary text, or change the pass input hash. Each
hides the summary and restores it after fixture restoration. The fixture now
models actual Pass 2 history rather than an empty synthetic payload. All 209
combined API tests pass, including 36 narrative/provenance cases. Checks used
isolated port 5434; the database was stopped afterward with its volume retained.
No real data, inference or deployment changed. The previously built API image
predates this fix and must be rebuilt for a release. Full upstream source and
payload consistency beyond these recorded dependencies remains distinct from
this summary-serving guarantee.


## Continued review: revised evaluation changes the product priority

The concurrent task completed the revised original and held-out evaluations:
40 documents, $0.14069727, no published extractions, no quality approval. The
tracked report now supersedes earlier statements that the held-out evaluation
was only a manifest. After the date-only correction, two nonempty documents and
five matters survive. All 40 outputs were schema-valid, but the evidence contract
rejected nearly all nonempty documents. The revised original sample cost about
55% more than the baseline. More fields and duplicated quotes increased burden
without establishing usable release yield.

The original/held-out results, sources and protocol artifacts were independently
checked against their recorded SHA256 hashes. An offline feasibility experiment
partitioned all forty unchanged source texts into 232 contiguous passages, each
at most 1,200 characters. It reproduced each source exactly by concatenating
passages. Of 292 existing evidence quotes, 277 mapped to passages and all fifteen
unsupported quotes remained unmapped. Those mapped quotes contain 67,922
characters, versus 2,853 characters in the corresponding passage-ID arrays;
the largest quote crossed three passages. This is a format comparison only,
not a measured token/cost saving: input label overhead and changed model behavior
are not measured. See output/municipal-passage-reference-feasibility-20260904.json.

Recommended smaller contract: identify passages deterministically within a source
hash; let each consequential field select bounded passage IDs; hydrate exact
source text server-side; derive the display excerpt instead of asking for another
copy. Unknown IDs, wrong source hashes and unsupported fields remain rejection
conditions. Preserve field-to-source association and semantic review; a paragraph
containing a claim's words does not prove its meaning. Preserve original model
responses and record hydration separately. Evaluate this as a new prompt/schema
identity before publication, without waiving the current gate.

Decision scope, milestone purpose, relevance and project continuity remain
independent failures that passage IDs cannot solve. Keep project, policy and
public-works investigation workflows because the reviewed records demonstrate
useful leads, but do not promote them as reliable early warning or start broad
backfill on the current results. The experiment made no model/provider calls,
source collection, database writes, or production contract changes.


## Continued review: reproducible passage-reference foundation

The proposed simplification now has an offline implementation in
pipelines/countyiq/lib/source_passages.py and a repeatable evaluator in
pipelines/eval/passage_contract_probe.py. Indexing preserves every original
Unicode character and exact offsets, with source identity bound to SHA256 of
UTF-8 bytes. IDs include the segmentation version and size; changing boundaries
cannot silently reinterpret an old ID. Resolution rejects wrong source hashes,
unknown IDs, malformed selections and duplicates. Non-contiguous passages remain
separate source excerpts. Source membership still does not establish entailment.

Nineteen new tests exercise reconstruction, long unbroken text, whitespace,
Unicode, wrong-source and changed-segmentation references, and invalid IDs.
Together with the unchanged production contract tests, 50 checks pass. The
archive probe verifies recorded file hashes before reading all forty original
responses and reconstructs all forty sources exactly. It maps 277 existing
quotes and leaves all fifteen unsupported quotes unmapped. Versioned ID arrays
use 5,389 characters for the 67,922 characters of mapped quotes; this supersedes
the shorter unversioned-ID experiment as implementation-specific format evidence,
not a measured token/cost saving. Results: output/passage-contract-probe-20260904.json.

No production prompt, schema, inference setting or gate changed. This foundation
is used only by offline evaluation so far. Remaining implementation includes the
smaller model-output schema, claim-to-passage hydration, decision scope and date
purpose, followed by a new evaluated identity before publication. No model calls,
database writes, collection or deployment ran in this step.


## Continued review: offline passage candidate schema and text hydration

The next simplification step is implemented under
pipelines/eval/passage_extraction_contract.py. Its candidate schema derives from
the current extraction schema, removes model-generated supporting_text and quote
strings, and asks for source-bound passage IDs with field assignments instead.
Hydration resolves only valid IDs, supplies exact original text, merges repeated
assignments to the same passage, and derives the display quote from a passage
supporting what_happened. Non-contiguous selected passages remain separate.
The original model payload is never rewritten in place.

Nine candidate tests cover exact text recovery into the existing output schema,
source identity, invalid/duplicate IDs, copied-quote rejection, unknown fields,
empty references, shared passages and retained decision safeguards. Together
with passage and production-contract checks, 59 tests pass. The full current
non-integration pipeline suite passes: 1,075 tests, 93 integration cases deselected.

This is an offline candidate only. No production prompt/schema, paid harness or
publication path was switched. Field-to-source assignments deliberately remain,
so this does not claim to solve the missing-assignment failures in the revised
evaluation. Selecting a broader passage can include unrelated facts; semantic
support, decision scope and relevance still require evaluation. The remaining
steps are a reviewed candidate prompt, end-to-end candidate evaluation with a
new identity, and production integration only after quality evidence supports it.
No model call, database change, collection or deployment ran.


## Continued review: frozen offline candidate package and migration reconciliation

Prepared forty previously evaluated documents for the passage-reference candidate
under output/passage-candidate-prepared-20260904. The package binds the exact
prompt, schema, request payloads and seven implementation files by SHA256.
Independent verification confirms all hashes and lossless source reconstruction
for all forty documents. These are regression inputs, not an unseen holdout.
The protocol is prepared_only, with no selected model or spend authorization.

The candidate prompt requests source-bound IDs instead of copied quotes and
retains explicit field assignments, decision-scope distinctions and conservative
date handling. It is not connected to production inference or publication.
Three preparation tests cover archive tampering, duplicate source rejection,
artifact binding and refusal to overwrite an existing package; all 31 focused
preparation, hydration and passage-indexing tests pass. Semantic accuracy and
cost remain unmeasured for this candidate. No model calls or database writes ran.

The user approved the previously proposed isolated duplicate-060 cleanup.
Inspection confirms concurrent reconciliation already established a single
061 Alembic head: 059 -> 060_specific_proceeding_addresses ->
061_proceeding_evidence_contract. The structured matcher now explicitly depends
on 060. The obsolete cleanup is unnecessary and would break this valid chain,
so no migration file or database version entry was removed.


## Continued review: ambiguous organization links and entity watches

The feed resolved organization names by repeatedly assigning a dictionary entry
for every matching owner. A canonical-name/alias collision therefore selected
whichever database row happened to arrive last. Entity filters and watch boosts
also accepted that same ambiguous mention for either owner. This could direct a
customer to the wrong organization and present unrelated activity as a watched
subject. Verification status of a candidate did not resolve the collision.

api/routes/feed.py now retains an owner link only when the normalized source
name identifies exactly one owner across canonical names and aliases. The shared
SQL helper applies the same uniqueness rule to owner filters and watch boosts,
removing the duplicated filter predicate. Matching consistently ignores outer
whitespace and case. Distinct names that identify one owner remain usable;
ambiguous names do not acquire an arbitrary identity.

A database-backed regression inserts a second organization with a conflicting
alias and verifies the project event remains visible while its owner link,
watch boost and owner-filter match disappear. Removing that fixture collision
restores the original link and watch behavior. All 19 focused feed/contract
checks and all 210 current API integration/unit checks pass against the isolated
countyiq_test database on port 5434. No production data or infrastructure changed.
The packaged API image must be rebuilt to include this change and the preceding
cross-signal freshness fix.


## Continued review: project chronology and condition adoption

The project summary accepted spelled-out dates through exact_date but then
compared and sorted their original strings. That internal inconsistency could
exclude a valid dated record or miss a same-day decision conflict. Normalization
now precedes chronology and produces consistent ISO receipt dates without
mutating caller data. Normal feed dates already arrive as ISO, so this closes
an accepted-input inconsistency rather than proving previously displayed live
project dates were wrong.

Conditions also used a weaker completion rule than decisions: a future or
undated record could receive the adopted-condition wording even while its
decision was excluded. Both now require a dated record on or before today;
scheduled and recommendation records remain excluded from completed decisions.
Unconfirmed conditions explicitly say adoption is not established.

Three regressions cover mixed-format chronological ordering, same-day conflict
detection and future/undated condition adoption. All eight summary tests and
all 25 combined summary/API contract tests pass against the isolated test
database. No frontend structure, production data or deployment changed.


## Continued review: missed east/west nearby-property matches

Both /api/parcels/near and the feed near_pidns filter used an approximate
radius/111000*1.2 degree bounding box before the geography distance predicate.
At latitude 40 degrees this longitude envelope is too narrow, so some parcels
within the requested distance were discarded. Removed both degree approximations
and retained ST_DWithin on geography, which measures meters and provides its
own index-aware bounding comparison (https://postgis.net/docs/ST_DWithin.html).
Migration 062 adds a partial GiST expression index on geom::geography for current
non-null parcel geometries. Existing geometry indexes remain for geometry queries.

Two database regressions position tiny parcel polygons 395 meters east and west
of a York-latitude anchor. Both nearby endpoints return them at a 400-meter
radius; the feed excludes them at 380 meters. All 215 API tests pass. The initial
regression invocation used an incorrect test URL (/nearby); corrected it to the
actual /near endpoint before verification. Migration 061 -> 062 applied only to
the isolated countyiq_test database. No production migration or deployment ran.

The new index requires storage and an ordinary transactional index build, which
can block writes while building. Measure the build and query plans on a
representative restored database before deployment; current fixture timings do
not prove production performance. This removes inaccurate custom distance math
from two customer-facing paths without changing the requested radius semantics.


## Continued review: representative nearby-query geometry benchmark

Copied all 175,928 current, non-null parcel geometries from the local countyiq
database using a read-only source connection into a temporary table in the
isolated countyiq_test database. The source database was unchanged; closing the
target connection removed the temporary table and index. The copy was 89,193,920
bytes of encoded geometry and took 0.98 seconds locally.

The equivalent partial geography GiST index built in 0.90 seconds and occupied
13,885,440 bytes (13.2 MiB). All nine EXPLAIN ANALYZE plans naturally selected
that index, without disabling sequential scans. Tests used nearby parcel
polygons around York, Hanover and rural eastern York County at 400, 800 and
3,000 meters. Warm spatial count queries ranged from 23 to 456 milliseconds.
These counts include the anchor itself and measure the spatial predicate only,
not the full endpoint joins, event filtering, response serialization or network.

The previous degree prefilter missed actual in-radius parcel geometries:
York 400m: 10 of 636; York 800m: 127 of 3,130; York 3,000m: 200 of 20,469.
Hanover: 16 of 600, 57 of 2,339, and 59 of 10,342 respectively.
Rural east: 1 of 43, 0 of 107, and 40 of 1,064 respectively.
This confirms the customer impact on representative local data, beyond the
synthetic boundary regression. These are parcel counts, not proven missed
customer notifications or accepted municipal events.

Artifact: output/nearby-geography-benchmark-20260904.json, including all nine
JSON plans and buffer measurements. Reproducible one-off script:
output/benchmark-nearby-geography-20260904.py. Production build duration, lock
impact and end-to-end endpoint latency still require target-environment checks;
a temporary local index build does not prove those deployment properties.


## Continued review: clean migration-chain and pipeline verification

The current non-integration pipeline suite passes: 1,078 tests, 93 integration
cases deselected. An initial schema integration run against the API fixture
database failed one seed-policy assertion (105 conditional municipality rows
versus the migration seed's 104). Inspection traced this to the API fixture's
synthetic Test Township policy and its Hanover municipality override, not 062.
Do not weaken the migration seed assertions to accommodate unrelated fixtures.

Created a separate local review PostgreSQL container on 127.0.0.1:5435 with
countyiq_test, the pinned PostGIS image and the repository's extension/schema
initialization SQL. The full fresh migration chain 001 through 062 completed;
all 23 schema integration tests passed (one database-safety unit test deselected).
Dagster definitions validate_loadable also passed, and Alembic reports a single
062 head. One existing AssetExecutionContext.run_id deprecation warning remains.
Both review database containers were stopped after verification.

This verifies fresh schema initialization and current pipeline contracts; it
does not establish a full production restore, authenticated live deployment or
LLM quality release. The schema suite must run on clean migrated seed state,
separately from API fixtures that deliberately alter governance data.


## Continued review: enforce database fixture isolation in CI

The workflow actually reused the API fixture database for pipeline integration
contracts, making the seed-state failure reproducible in CI rather than merely
a local invocation problem. The database-integration job now starts a separate
pinned PostGIS container on localhost:5434, initializes the repository extension
and schema SQL, migrates from base, and supplies both DATABASE_PORT and
TEST_DATABASE_URL so all pipeline database adapters target the same isolated
instance. An always-run cleanup collects logs and removes that job-owned
container and its anonymous volume. API fixtures retain their existing instance.

Parsed the current workflow and syntax-checked all shell run blocks. Executed
the exact new startup, migration, integration and cleanup step bodies locally
with their declared environments and working directories. Fresh migration to
062 succeeded; all 93 pipeline integration tests passed, with 1,078 tests
deselected and the previously recorded Dagster deprecation warning. Cleanup
completed. Expected database ERROR logs from append-only, read-only and locking
negative tests are evidence of the tested guards, not failing tests.
Hosted GitHub Actions execution remains unverified; no repository push ran.


## Continued review: independent applied metadata-repair replay

Read the local real-data database in a repeatable-read, read-only transaction.
It remains at migration 061, with 175,928 current parcels, 6,459 current
proceedings and zero extractions. Stored metadata statuses match the cleanup
report: 3,264 ready and 3,195 review_required. All 11,088 source IDs referenced
by the review ledger still exist and match every recorded source fingerprint;
there are no missing reviewed sources or fingerprint mismatches. This includes
originals and correction versions, not 11,088 distinct original documents.

However, replaying the current proceeding-metadata-3 classifier with the frozen
September 4 review date changes six stored-ready records to review_required:
11112, 11117, 11121, 11141, 11142 and 11149. All report conflicting header dates.
Stored annotations contain no explicit manual override reason. The normal
load_inputs path reports zero unapplied records because it skips records already
tagged with version 3, so that count alone does not establish reproducibility.

Source inspection shows several other dates concern prior minutes or executive
sessions; those need classifier-boundary review rather than automatic blanket
quarantine. Record 11121 has an actual header/body conflict: January 5, 2021 in
the title versus December 5, 2021 in the opening meeting sentence. The stored
ready annotation does not explain why that conflict was resolved. Preserve the
source and reconcile review behavior/version identity before closing metadata
repair acceptance. No source or review annotations were changed by this audit.

Artifact: output/metadata-repair-verification-20260904.json. Reproducer:
output/verify-metadata-repair-20260904.py. This establishes preserved evidence
and correct aggregate counts, while identifying a remaining six-record
classification/review reproducibility discrepancy.


## Continued review: versioned metadata date-boundary correction

Metadata version 4 recognizes attendance markers as the end of date-bearing
header text. Board identity detection retains the broader header so attendance
labels do not erase board evidence. This resolves five of the six previously
identified replay discrepancies, where prior executive-session/minutes dates
were incorrectly treated as competing meeting dates. Record 11121 remains held
for its actual January/December opening-date conflict. All 11,088 reviewed
source fingerprints still match. Five new regressions cover attendance forms
and preservation of a conflicting opening meeting date; 41 focused tests pass.

Read-only corpus replay: output/metadata-repair-verification-v4b-20260904.json.
A dry-run repair plan at output/metadata-v4-review-plan-20260904.json covers all
6,459 current records under the new version. It proposes 3,480 ready and 2,979
review_required, including 226 metadata supersessions and 6,233 annotations;
502 ready records are in the current-year eligible date range. This is a broader
behavior change than the six original discrepancies, so newly released records
and proposed date changes require review before apply. No real-data repair
was applied and no paid inference ran.

During broad verification, concurrent changes switched extraction prompt/schema
and project identity behavior. The run returned 1,073 passes and ten failures
in test_eval_protocol, test_municipal_pilot, test_proceeding_contract and
test_proceeding_extraction. Those failures are outside the metadata files edited
here and must be reconciled with the concurrent work before a release claim.
Do not treat the earlier 1,078-test green baseline as current acceptance.


## Continued review: version-4 repair impact inspection

Compared the dry-run plan with current stored annotations in a read-only
transaction. There are 217 newly ready records across eight boards: Windsor
Council 17, Glen Rock Council 18, Fawn Supervisors 1, North Codorus Supervisors
11, East Manchester Supervisors 151, East Manchester Planning 15, Shrewsbury
Council 3 and Codorus Supervisors 1. Eight are dated in 2026. The net ready
increase of 216 also includes moving conflicting record 11121 back to review.
The per-record headers and proposed metadata are preserved in
output/metadata-v4-newly-ready-20260904.json.

Inspected thirteen systematically spaced source headers across the newly ready
set, plus special-meeting header candidates and all nine supersessions outside
that set. The sampled releases have explicit meeting dates before attendance
and refer to past minutes/executive sessions in later business. This supports
the date-boundary change, but is not a claim of manual acceptance of all 217.
The other nine supersessions preserve review holds for filename conflicts,
unverified boards and contradictory opening meeting dates. Joint-board titles
on records 8731/8732 remain held by filename conflicts and should retain
independent scope protection if those filename issues are later resolved.

A separate false hold is visible in record 8485: March 22, 2017 minutes report
that the March 14 meeting was cancelled by snow. The whole-text cancellation
pattern marks the March 22 record cancelled. This is a customer-coverage loss,
not evidence that version 4 should broadly waive cancellation holds. Correct
the cancellation scope with positive/negative source-backed regressions before
claiming the metadata classifier review is complete. No repair was applied.


## Continued review: scope explicit dated cancellation references

Reviewed all sixteen current cancellation holds. They include genuine notices
(43 and 8860), a cancellation appended after an agenda (10973), and references
to other past meetings or boards. Restricting cancellation detection to a header
would incorrectly miss trailing notices, so the full 1,000-character check stays.
A new helper exempts only explicit named dates grammatically attached to a
cancelled meeting when the date differs from the document meeting date. It
does not exempt notices because an unrelated earlier date appears elsewhere.
Missing-year references compare month/day without publishing an inferred year;
invalid dates and ambiguous/same-date notices remain held.

Nine regression cases cover the verified historical cancellation, same-date
notices, unrelated dates, invalid dates and a trailing agenda notice. All fifty
focused metadata tests pass. Read-only replay of all sixteen current holds
changes only record 8485, whose March 22 minutes explicitly describe the March
14 cancellation. The other fifteen remain held. Some are apparent false holds
with different wording and require further scope handling; this is not a claim
that every cancellation case is now classified correctly.

Artifact: output/metadata-cancellation-replay-20260904.json. Version 4 remains
unapplied; the earlier version-4 dry-run plan predates this additional change
and must be regenerated and reviewed before apply. No real data changed.


## Continued review: combined-board metadata scope

The classifier previously held titles containing explicit joint meeting/workshop
wording but selected the first recognized board in titles such as BOARD OF
SUPERVISORS/PLANNING COMMISSION. It now also holds adjacent distinct board roles
connected by slash, ampersand or and. A separate guest-board reference does not
trigger this rule. Four new regressions cover those connectors and a guest
reference; all 54 focused metadata tests pass.

Regenerated the complete read-only version-4 plan after date, cancellation and
combined-board changes: output/metadata-v4-scope-review-plan-20260904.json.
The plan proposes 3,481 ready and 2,978 review_required current records, with
502 recent eligible documents. Thirteen additional records now have an explicit
joint_meeting hold; all thirteen were already held for other reasons, including
the reviewed East Manchester combined-board titles. This ensures fixing those
other issues cannot silently release them as single-board records.

Compared with the earlier version-4 plan, cancellation whitespace normalization
also adds a cancellation issue on already-held records 1897 and 8872, while
removing the verified false cancellation issue on 8485. The only status change
between these two version-4 plans is 8485 becoming ready. Exact changes are in
output/metadata-v4-scope-plan-diff-20260904.json. The plan remains unapplied;
this does not close manual acceptance of all newly eligible source records.


## Continued review: concurrent extraction baseline and address-like identities

A fresh broad pipeline run produced 1,088 passes, eight failures and 93
integration cases deselected while extraction changes continued. A subsequent
focused proceeding-contract run passed all 31 tests, confirming the source
changed during review; neither result is a settled release baseline.

Inspection found the distinctive-project predicate temporarily used an escaped
literal backslash-d instead of the digit regex. Concurrent work corrected that
expression and added a street-suffix guard before this review's conditional edit
could apply. The edit correctly aborted rather than overwriting the new code.
This review then fixed the remaining leading-whitespace bypass by stripping the
reference before the digit check. Four new tests cover address-like references
(including leading whitespace), absence of named aliases for those references,
and retained continuity for a distinctive development name. All 35 focused
identity/contract tests pass. Existing application aliases remain governed by
their own identity rules. No database, model call or publication ran.


## Continued review: rebuilt current API runtime

Built countyiq-api:review-current-20260904 with image ID
sha256:5d719b41303abeb6d836d200a3c02a83413f1f8ef5307216d9f66c0405ee9959.
All 34 packaged API Python files match current workspace SHA256 hashes, including
the recent summary freshness, unique-owner matching and nearby-query fixes.
The runtime starts with UID 10001 from the Dockerfile, read-only root, 64MiB
tmpfs, all capabilities dropped, no-new-privileges, init, 256 PID limit and 768MiB
memory. It uses the isolated migrated countyiq_test database and restricted API
role with synthetic Access configuration.

Direct HTTP checks: readiness/health/session 200; unsigned feed, watchspace and
nearby-property requests 401. This bypasses Caddy; no claim is made here about
proxy response headers or live identity-provider login. The direct session and
watchspace responses carry no-store; other checked direct responses do not.
The production proxy's API no-store behavior was checked separately earlier.
Artifact: output/packaged-api-current-r2-20260904.json, including code hashes.

The first chosen container name collided with a previously stopped review
container; it was preserved and a new r2 name was used. The new runtime and its
review database were stopped after verification. No production deployment ran.


## Continued review: scoped-event database contract and test boundaries

After concurrent extraction changes settled enough for verification, all 1,138
pipeline non-integration tests passed. The database suite then exposed a real
persistence blocker: scoped_decision violated the old event-type constraint.
The API and frontend already recognized that type. The original database
constraint also omitted policy_action, recommendation, withdrawn and removed.
Migration 063 expands the permitted types without rewriting events. Its
downgrade intentionally refuses existing newer types rather than deleting or
relabeling source-backed records. Both isolated databases migrated 062 -> 063.
The local real-data and production databases were not migrated by this review.

Five new schema persistence cases cover all added event types. Once persistence
worked, an existing new pipeline integration branch attempted to import FastAPI
from the pipeline-only environment. Moved its API visibility assertions into
api/tests/test_scoped_event_visibility.py with equivalent default-discovery,
explicit-history and explicit-category checks. Pipeline persistence, evidence,
milestone and signal-exclusion assertions remain in the pipeline suite. No API
runtime dependency was added to pipelines.

Final checks: all 99 pipeline integration tests pass on the clean seed database
at port 5435; all 219 API integration/unit tests pass on the separate API fixture
database at port 5434. The pipeline integration run retains one existing Dagster
run_id deprecation warning. Review databases were stopped after verification.
Migration 063 is now required before the new scoped-event publication path;
passing these checks does not establish model quality or approve publication.


## Continued review: current real-data inference preflight

Ran the actual Pass 0 preflight against local countyiq on port 5433 using its
read-only execution mode, sample size five and canary cap five. It refused
readiness: the real-data database remains at 061 while concurrent changes have
advanced the repository to 064. The integrity views were deliberately not
queried under the schema mismatch. A current model/prompt quality receipt and
explicit runtime controls are also absent. The report's hypothetical estimates
are not spend approval, measured quality or authorization to run inference.

Artifact: output/pass0-preflight-after-063-20260904.json. The filename records
this follow-up's starting context; its authoritative repository_heads field is
064. Concurrent work also updated the 063 contract after the earlier test pass.
Do not present earlier 063 checks or packaged images as final acceptance for
the subsequently changed repository. No database migration, enablement, paid
model call or deployment was performed by this preflight check.

Deployment code already migrates with application services stopped before
starting the release images. The intelligence preflight additionally compares
the database to the repository head. API /ready remains a database-connectivity
probe and cannot substitute for that release preflight or quality acceptance.


## Continued review: reject multiple database migration heads

The intelligence preflight checked only the first alembic_version row. If a
database retained another branch revision and happened to return the expected
head first, schema_at_repository_head could incorrectly pass. It now requires
exactly one recorded database revision before comparison and reports the sorted
full database_revisions list. Multiple revisions prevent integrity/history
queries and fail schema readiness regardless of row order.

Two regression cases cover both row orders with an expected head plus an
unexpected branch; all eight focused preflight tests pass. Existing old-schema
and fixture-contamination checks remain intact. This is a verified guard defect,
not evidence that the actual local database has multiple heads. No database
mutation, paid model call or deployment ran.


## Continued review: stable repair plan and rehearsal authorization

Regenerated the current version-4 plan and verified exact parsed equality with
the prior scope-review plan, including all 6,459 item decisions and source
fingerprints. The plan remains unapplied. Seven synthetic metadata database
integration tests pass against the isolated database, exercising the existing
repair guards without copying real records.

Proposed a full repair rehearsal by copying current local proceeding records
from read-only countyiq:5433 into countyiq_test:5435, applying in a transaction,
checking retained fingerprints/ledger/statuses and rolling back. Automatic
approval review rejected that command before execution because the bulk copy
is a data transfer requiring explicit authorization; rollback does not remove
its exposure risk. Requested approval for this exact local rehearsal. Do not
retry the copy through a different route or treat the broad goal as overriding
that rejection. No real-source transfer or repair rehearsal ran.


## Continued review: same-day withdrawal summary ordering

The new project-summary withdrawal/removed override inspected only the event
that sorted last by event key on the latest date. A same-day approval and
withdrawal could therefore display either an approval or a withdrawal solely
because of key order, without source evidence establishing a sequence.
The summary now considers states across all records on the latest date and
labels mixed withdrawal/removal actions as requiring scope and sequence review.
A withdrawal on a later date retains its clear label. Existing conflicting
decisions take precedence and cannot be hidden by a same-day withdrawal.

Four regressions cover both event-key orders, a later dated withdrawal and
conflicting same-day decisions plus withdrawal. All fifteen project-summary
unit tests pass. Individual decision receipts are preserved; no within-day
chronology is invented. No database or frontend structure changed. The current
API image must be rebuilt again to include this subsequent summary fix.


## Continued review: current frontend build and revision 064 contracts

The current frontend passes TypeScript project checking, ESLint, all 27 Node
tests and a production Vite build. The map warning remains: MapView is 826.22kB
minified / 220.22kB gzip, and MapLibre is 1,025.12kB / 272.16kB gzip. Combined
compressed size is 492.38 decimal kB (about 481KiB), before other dependencies
and map data. This is a bundle-size measurement, not a measured user load time
or evidence that unrelated routes download those lazy chunks. No warning
threshold was relaxed or arbitrary bundle split introduced.

Inspected migration 064, which adds update to the scoped municipal event types
and refuses downgrade while update rows exist. Applied 063 -> 064 only to the
isolated clean-schema database. All 100 current pipeline integration tests pass
(1,142 non-integration tests deselected); one existing Dagster deprecation
warning remains. This does not rerun or establish those 1,142 unit tests.
The isolated database was stopped after verification. No production migration,
publication or deployment ran. Browser behavior after the newest UI changes
still needs a rendered check; a successful build alone is not UX acceptance.


## Continued review: current scoped-project mobile receipt interaction

Used Firefox and a separate Vite instance on port 5176 with the existing clearly
labeled synthetic version-3 project fixture. At 390x844, verified Bond: Approval
recorded, separate bid-opening and completion milestones, and clicking the
completion source link opens synthetic-v3-source-2. The receipt heading lands
below the dynamically measured navigation; there is no horizontal overflow or
JavaScript page error during the fixture interaction. Visually inspected the
receipt screenshot. This is rendered interaction evidence, not live model
accuracy, real customer data or authenticated account acceptance.

The first assertion used the wrong label capitalization (Bid opening rather
than Bid Opening). An extra test-issued scroll initially produced an apparent
header overlap. Removed that artificial scroll and asserted the application's
actual landing position; it passed, so no speculative CSS fix was introduced.
Screenshots: output/playwright/review-current-scope-mobile.png and
output/playwright/review-current-scope-receipt-mobile.png. Reproducer:
output/playwright/review-current-scope.cjs. The isolated Vite process and named
review browser were closed; the other active Vite instance was preserved.


## Continued review: withhold unversioned county narratives

The property API still served Pass 4 county narratives solely on expiry and
affected_pidns membership. Unlike the hardened parcel and owner briefs, these
records have no immutable upstream dependency receipts or serving-time source
revocation checks. Default-off generation does not prevent old rows appearing.
An unexpired narrative could therefore outlive the evidence or permission that
supported it.

The API now returns an empty related_narratives list until a real Pass 4
provenance contract exists. Storage is preserved; there is no new bypass switch
and no fabricated dependency receipt. The existing conditional frontend section
will remain absent. This aligns with the feature assessment that Pass 4 is a
default-off, nonessential alpha surface, but is an explicit serving restriction,
not completion of the underlying provenance work or removal of stored evidence.

The existing property contract fixture contains an unexpired county narrative.
Its assertion now requires withholding that row while current validated parcel
brief and cross-signal evidence remain available. All 17 API contract tests
pass. No real-data mutation or frontend edit ran. Re-enablement requires
versioned upstream inputs, revocation/change tests and a legacy-cache transition;
a timer or a simple generation-enabled flag is insufficient.

### Migration cleanup approval reconciled with the current worktree

The delayed approval to remove the duplicate `060_specific_proceeding_addresses.py` was checked against the current files before action. The structured matcher now lives in `061_proceeding_evidence_contract.py` with `down_revision = "060"`; the duplicate revision no longer exists. `alembic heads` reports one head, `064`. No migration file was removed and no migration history or function was rolled back: the approved cleanup is obsolete and would break the current chain.

A fresh API route search found parcel and owner brief reads only in their guarded detail endpoints, and the cross-signal summary read in the guarded parcel endpoint. This search found no additional list/search brief-serving bypass. Fresh verification of `api/tests` and `api/unit_tests` against the isolated port-5434 fixture passed **223 tests**. This verifies the current source checkout, not a rebuilt deployment image or production authentication.

### Current packaged candidate rechecked after summary/provenance changes

Fresh pipeline verification passed **1,143 non-integration tests**, with 100 database integration cases deliberately deselected. The prior turn's fresh full API run passed 223 tests. Investigation of absent signal-history handling found no additional bypass: brief signal-version matching requires a non-null matching active inference ID, and the database foreign key prevents a dangling history reference. This does not extend certification to unrecorded dependencies.

Rebuilt both current Dockerfiles and exercised them together on the isolated test network, using the restricted API database role and synthetic Access configuration. The API ran as UID 10001; both containers used read-only roots, dropped capabilities, no-new-privileges, bounded memory/process counts and temporary writable runtime directories. All **15 HTTP checks passed**: marketing/product entry separation, marketing API rejection, preserved deep-link redirects, product deep-link HTML, unknown-host rejection, missing-asset 404/no-store on both hosts, API readiness/session responses, unsigned private-route rejection, API no-store through Caddy, and gzip/immutable caching for a real application asset. All 34 packaged API Python files matched current workspace SHA-256 values at acceptance.

- API image: `sha256:18536006ce021934ed2600549b7566d8ae3f38872b1685ed0027ef64f2ae6d8c`
- Web image: `sha256:f7d9ce14f852e99cd3329a8243407bbc92125fc3f78200c0b84d95aaaeb05f09`
- Detailed receipt: `output/packaged-current-r3-20260904.json`
- Build logs: `output/api-current-build-20260904.log`, `output/web-current-build-20260904.log`

Review containers and the isolated database were stopped afterward. Existing user containers were preserved. These local packaged checks cover the source snapshot at this point; concurrent edits can invalidate it. They do not establish live Access sign-in, accepted municipal inventory, a deployed target-host release, or restore acceptance, so the outstanding live-plan gates remain open.

### Actual PostgreSQL restore rehearsal on synthetic fixtures

Previous restore-script regressions fixture Docker and R2 commands. This review added real recovery evidence using PostgreSQL pg_dump custom format and pg_restore --exit-on-error --no-owner against isolated port-5434/countyiq_test synthetic fixtures. No records were copied from the real countyiq database.

A newly created sibling database received the 341,859-byte dump. All 19 checked tables matched source counts and sorted row-content hashes, including parcels, proceedings, events, evidence, owners, briefs, accounts, workspaces, watches, inference history and source policies. Migration head 064, extension versions and the properties view query matched. The API role retained properties SELECT without parcel DELETE permission. A second source inventory confirmed it unchanged.

The owned disposable database was dropped and the isolated container stopped. Evidence: output/synthetic-restore-20260904.json and output/synthetic-restore-20260904.dump. This is same-instance recovery with existing roles, not R2 transfer, target-host recovery, host-loss acceptance or an RTO/RPO measurement. The live restore gate remains open.

### Real restore verification added to the automated API database suite

Added api/tests/test_backup_restore.py, discovered by the existing CI database-contract command without a new workflow or service. It uses the established isolated countyiq_test fixture, PostgreSQL tools inside that fixture's Compose service, a unique new sibling database, and real custom-format dump/restore. Unlike the earlier one-time 19-table rehearsal, the test discovers every table in public/staging/meta and compares sorted row-content hashes and counts, plus extensions, the properties view query and the API SELECT/no-DELETE boundary. It also confirms the source inventory is unchanged. Cleanup runs only after successful creation and cannot reset an occupied database name.

Fresh focused verification: 1 passed in 4.26 seconds. Existing network-isolated shell tests continue to cover restore orchestration failures separately. This regression is same-instance PostgreSQL recovery with existing roles; off-host R2 transfer and target-host recovery remain unverified. No runtime source changed in this turn, so this addition does not stale the previously recorded API/web image hashes.


### Live host and app DNS revalidated

Read-only SSH verification still reports passwordauthentication yes, permitrootlogin no, kbdinteractiveauthentication no, and /var/lib/countyiq/cost-guard mode 0700 root:root. The cost-guard timer is active; the backup timer is inactive. No running application containers or current.env release/restore receipts were found in the checked host directory. The previously requested host-change approval remains separate from the obsolete migration cleanup approval. No host setting was changed.

An actual browser navigation to https://app.countyiq.net failed with ERR_NAME_NOT_RESOLVED. An independent Resolve-DnsName query to public resolver 1.1.1.1 confirmed NXDOMAIN; the apex countyiq.net returned Cloudflare A/AAAA addresses. The current IaC defines product DNS and Access resources, but its historical initial-apply report is not evidence of their deployment. Updated the account guide and infrastructure README to label intended routing and the pending app-host rollout accurately. Live authentication acceptance is blocked before the login screen, not merely untested credentials. The existing guarded rollout order remains the next operational step; no DNS, Access, Tunnel or public-exposure change was applied.


### Date-first cancellation notices corrected in metadata version 5

Read-only inspection of the 16 previously audited cancellation records confirmed several prior-meeting references still caused holds. Extended exact named-date comparison to date-first notices (including public meeting), preserving holds for same-day, invalid-date and unrelated-date statements. Also corrected detection of the single-L spelling in Canceled meeting. Incremented the classifier to proceeding-metadata-5 so old reviewed plans cannot apply under changed semantics.

The focused suite passed 62 tests. The read-only 6,459-record plan now proposes 3,482 ready and 2,977 review-required records, with the same 226 supersessions and 502 recent-ready records. All source fingerprints matched the preceding version-4 plan. The detailed plan and semantic difference are output/metadata-v5-review-plan-20260904.json and output/metadata-v5-plan-diff-20260904.json. No real repair, cross-database transfer, publication or model call occurred. Version-4 repair plans are superseded and require regeneration/review; the isolated bulk-copy approval remains pending.


### Repair plans now bind and retain prior review annotations

Found a repair precondition gap: load_inputs omitted metadata_quality, so an operator could alter an older review annotation after plan preparation without changing the plan comparison. The annotation could then be replaced without retaining it in the new audit entry. Plans now include prior_metadata_quality for each affected record; the existing locked full-plan equality check rejects a changed annotation. New audit entries preserve the prior annotation under original_metadata.metadata_quality. Source identity/content fingerprints retain their existing contract.

Fresh verification: 62 metadata tests passed, followed by 8 explicitly selected database integration tests on isolated port 5435. The initial combined invocation deselected the integration cases due to repository defaults; the separate -m integration run executed all eight. The new regression checks annotation-only plan invalidation and audit preservation through a real PostgreSQL transaction. Prior full pipeline verification after metadata version 5 passed 1,151 non-integration tests.

Regenerated the read-only plan at output/metadata-v5-annotation-review-plan-20260904.json. All 6,459 decisions and fingerprints are identical to the earlier version-5 plan after excluding the added prior annotation field: 3,482 ready, 2,977 held, 226 supersessions and 502 recent-ready records. Earlier plans lacking the new precondition field are stale. No real repair or bulk transfer was applied; the isolated database is stopped after verification.


### Brief serving now verifies the accepted output itself

Found that the API verified an accepted Pass 3 identity and current dependencies without checking whether mutable cached claims still matched that record. A changed brief_text or structured explanation could retain the same active_inference_id and be served. The common serving guard now matches narrative text and customer-facing structured claim/citation fields to the immutable accepted payload. Parcel output uses payload.brief; owner output uses payload.brief_text, matching both normal publication and resolution code. Operational fields such as timestamps, trial metadata and context-derived counts are not model-output claims and are not compared here.

Updated synthetic inference fixtures to carry realistic payloads rather than empty objects. Four regressions alter parcel/owner text or explanation fields while retaining current dependencies, verify withholding, and restore the original projection to verify serving resumes. Focused provenance suite: 40 passed. Full API database and unit suite: 228 passed, including the real restore regression. Missing or mismatched historical payloads remain stored but are not certified for serving; no historical payload is fabricated in production. No model call or real database mutation occurred. The previously packaged API image predates this guard and needs rebuilding before release acceptance.


### Live Cloudflare plan prepared for guarded app-host rollout

Ran OpenTofu plan against the actual encrypted remote-state configuration without applying resources. The saved plan creates cloudflare_dns_record.product and cloudflare_zero_trust_access_application.product, updates the existing Tunnel ingress, and records the existing apex Access resource address move without changing that gate. publish_marketing_site remains false. No deletion, storage change or additional resource class is proposed. Both Access gates have one active email allowlist rule; provider-populated null alternatives are not active policy entries. App DNS/Tunnel dependencies retain the configured Access-before-routing order.

Saved plan: infra/cloudflare/review-app-host-20260904.tfplan, mode 0600, SHA-256 11615bbde1b9ec967becab3fa9bc7a0ebe88c672f90079616e06e51d4d2fc6a4. Sanitized review and source configuration hashes: output/cloudflare-app-host-plan-summary-20260904.json. Raw plan output is restricted to output/cloudflare-app-host-plan-20260904.log; the binary plan is ignored by Git. Approval was requested for this concrete live DNS/Access/Tunnel change. It is not applied and does not establish a running origin, customer sign-in or host recovery. If approval arrives, check plan/configuration freshness before execution and retain the apex gate until the documented customer journey checks pass.
