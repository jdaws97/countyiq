# Site inquiries and local source worker — October 3, 2026

This iteration implements the authorized local-PC acquisition path and refines
the site-intake product. It does not establish customer demand, municipal approval,
complete municipal coverage or verified site suitability.

## Production source recovery

The PC acquired nine approved public feeds under a current VPS policy permit.
The VPS imported the immutable bundle through the normal Dagster parsers, source
checks, raw archive and SCD2 loaders. No production database credential was copied
to the PC and no database port was exposed.

Run `caba69ec-84d6-462c-9bc8-2193216bfd71` succeeded on October 3. Its bundle ID was
`c31a818f579e462a8d1969326730d618`, acquired at 20:35:38 UTC. The manifest SHA-256
was `a248211905f9bc8438c6c0f75c1b46f90dfe325de4de4a589f43013434e59620`.
All five assets materialized and all seven registered asset checks passed.

| Source | Imported records |
| --- | ---: |
| PennDOT roads | 2,272 |
| PennDOT transportation projects | 137 |
| PennDOT traffic | 1,819 |
| DEP regulated tank facilities | 382 |
| DEP cleanup locations within the configured query extent | 1,314 |
| County tax claims, report dated October 2 | 37,017 authority rows |

Each source's refresh status became successful. Six dataset watermarks were
committed with their staging changes; the two DEP layers have separate
transactions. Production raw evidence archives remain the retention record.
The workflow is manual while the PC is online. A small PC/VPS clock offset found
during the first acquisition now causes a bounded wait before requests; a larger
offset fails before acquisition.

## Browser verification

Playwright exercised the local application against the actual production intake
response for parcel `29000MB000500`, 467 Capitol Hill Road, Franklin Township,
plus its actual public parcel-boundary and municipal-evidence responses. These
responses were supplied to local browser requests; this was not an authenticated
production-browser session. All entered client proposals and notes were explicitly
labeled verification examples and stayed in the browser workspace.

Verified behavior:

- Save and continue from the unsaved-navigation dialog retains the inquiry.
- A documented question response survives saving and appears in the handoff;
  unanswered questions remain visible.
- Changing a ready inquiry's proposed use removes its ready status and review.
- Deleting the saved inquiry from another browser tab leaves the active draft
  intact and blocks accidental recreation by a stale save.
- Successful print preparation verifies evidence first. A simulated 403 during
  the next print check removes the preview and does not invoke printing.
- At 390px, the editor has no horizontal overflow. The phone menu closes with
  Escape, and the handoff remains readable.
- A native four-page Letter PDF retains the user brief, evidence, questions,
  municipal source qualifications, source links and scope. The first and final
  pages were rendered and inspected after adjusting question-response grouping.
  Navigation and screen controls are excluded from print.

Local artifacts are under `output/playwright/`: desktop and phone screenshots,
`site-handoff-mobile.png` and `site-inquiry-handoff.pdf`. Generated examples are
not committed as customer records.

## Validation

The final implementation passed the complete pipeline unit suite (2,084 tests),
fresh isolated pipeline database integration suite (150 tests), API database
suite (245 tests), Dagster definitions validation, CI and API Contract workflows.
The clock-offset follow-up passed 26 focused snapshot tests. Inquiry/workspace
API tests passed (11), including account isolation, version conflicts and
question-response validation. Frontend validation includes its 73 tests,
applied Prettier formatting, TypeScript build,
ESLint and the production Vite build. Ruff formatting was applied to Python code.
The map remains a separate lazy-loaded bundle; its existing bundle-size advisory
still appears during builds.

Repository Security workflows cannot complete their CodeQL and dependency-review
jobs while those GitHub repository features are disabled. Ordinary CI checks and
application tests remain separate from that configuration limitation.
