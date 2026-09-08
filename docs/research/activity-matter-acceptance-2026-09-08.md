# Activity matter accounts: local acceptance, September 8, 2026

The user reported generic agenda titles, mixed subjects, missing variance details
and outcomes, and slow loading on port 5191. The implementation adds a Pass 3
matter-account stage and uses its complete accounts as activity items. Passes
0–2 retain their source-selection and verified-identity responsibilities.

## Real source canary

The user explicitly authorized the signed-in Codex subscription for four public
candidate bundles. The maintained `subscription_backfill.py matter` command
completed four accepted bundles, zero errors/quarantines and zero API calls.
Artifacts remain under `output/activity-matter-canary-2026-09-08/` outside Git.
These four bundles partitioned into seven accounts: three explained activities
and four sparse research leads. This is a local canary, not countywide coverage.

- **370 Poplar Street:** the July Planning Commission materials explain a
  74-by-18-foot dust collection silo against a 50-foot maximum. August minutes
  report Zoning Hearing Board approval on July 20. The activity labels this
  “Approval reported” and preserves the earlier discussion. A separate sparse
  section-number agenda listing was not assumed to be the same request.
- **750 E. Philadelphia Street:** application 30-2026-Z-V requests appliance-store
  use and parking relief. Planning minutes record applicant absence and no
  recommendation; the board agendas contain unfilled approve/deny motions.
  The account explicitly says a final outcome is not established. Its four
  documents include the English presentation of a Spanish agenda. The older
  withdrawn 3-2026 application stays separate and remains a research lead.
- **110 Yoe Drive:** four rezoning records form one account, with no established
  adoption outcome. Two final-subdivision listings form a separate sparse lead.

Candidate retrieval does not yet join repeated project names without a verified
property, literal case reference or literal address anchor. Case prefixes support
spaced and unspaced forms. Existing matter merge/split conflicts require review.

## Loading

The same local 30-item, 90-day, priority-sorted feed request measured 16.308s
before the change. Materializing live source checks once reduced the existing
path to 0.738s. With the complete matter-account path, source receipt lookup and
presentation guards enabled, the final request measured **1.371s**. These are
local single-request observations, not production percentiles or a load test.
The new route verifies current source scope at query time; it does not serve a
stale response cache to achieve this improvement.

## Verification

- Pipeline non-integration suite: 1,809 passed; the eight remaining local HTTP
  tests required socket access and then passed. After the final matter changes,
  61 focused matter/explanation/definitions tests passed, including 14 matter
  contract tests.
- API: 58 checks passed in the initial source/feed/watch run; five old raw-agenda
  notification expectations were updated to the new research-lead contract,
  preserving explained-notification tests, and all five reruns passed. All nine
  new database-backed matter tests passed, including pagination after a split,
  new-source and edited-source withdrawal, source pages, current rights,
  notifications and spaced case references. The nine focused feed/source/English
  unit tests also passed. An optional full API unit run stalled after 14 tests
  in the restricted environment and was stopped; it is not reported as a pass.
- Frontend: typecheck, lint and production build passed. Ten test files passed
  in the restricted environment; the remaining routing file passed all four
  checks with localhost socket access. The existing large map-bundle warning
  remains unrelated to this change.
- Real browser at 1440px, 900px and 390px: readable case account, no horizontal
  overflow, phone detail navigation, retained source history, citation drawer,
  Escape dismissal and correct official document link. Follow matter survives
  reload; the test follow was removed. The research toggle preserves URL state.

Screenshots are in `output/playwright/activity-matter-750-desktop.png`,
`activity-matter-750-tablet.png`, `activity-matter-750-phone-detail.png`, and
`activity-matter-poplar-final.png`. Source reading confirms the populated record;
no later decision is inferred from a date or an agenda motion template.

## Rollout

Schema migrations 071–075 introduce aliases, complete candidate sources/current
accounts and shared activity/readiness views. All are applied only to the local
and dedicated test databases during this work. The normal intelligence event
producer publishes accepted accounts and keeps notifications on the same
explained-activity boundary. The subscription backfill operator guide documents
the matter invocation. Production deployment and countywide authoring are
coordinated separately; generating four local bundles does not finish that work.
