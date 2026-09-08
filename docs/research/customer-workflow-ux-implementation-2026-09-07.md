# Customer workflow redesign — implementation and acceptance

Implemented locally on September 7, 2026, against the real CountyIQ preview at
`app.localhost:5180`. This follows the
[customer workflow audit](customer-workflow-ux-audit-2026-09-07.md).

The main reading path is now activity → complete explanation → supporting source
→ related property or owner → watch. Property screening remains available as a
separate way to investigate sites.

## Delivered behavior

- **Evidence:** inline citations and “View source” open a shared source viewer.
  It shows the original passage, public record facts, dates, known page numbers,
  related record links and the original document. Closing returns to the same
  reading position. Mobile uses the full screen. Explicit public-field presenters
  replace arbitrary object rendering, so hashes, inference IDs, weights, model
  details and unknown future processing fields stay out of customer presentation.
  Deed book/page, parcel numbers, ownership changes and other useful public
  references remain available. Unknown citations are visibly unavailable.
- **Activity cards:** complete summaries no longer have a permanent two-line
  clamp. “Read more” exposes the next check, stated conditions/milestones and
  related organizations. Source verification is a separate direct action.
  Dates retain their proposed, scheduled or historical meaning. Repeated category
  labels and self-links on the current property are removed.
- **Property reports:** recorded activity comes first, followed by site facts and
  ownership connections. Zoning, flood/soil limitations and remaining diligence
  questions have readable summaries. Adjoining ownership records have address
  links, sale dates and source actions. Additional context, detailed screening
  records and the full municipal source library have distinct disclosures.
  Share/export controls occupy a small secondary menu.
- **Discovery:** the workspace presents real recent activity and routes into
  investigation. The activity page has four primary filters, secondary controls,
  text search, coverage detail and explicitly qualified upcoming dates. Municipal
  profiles lead with activity and coverage. Directories support investigation
  instead of presenting debt totals as the main reason to choose a municipality.
- **Search:** organization, project, municipality and source-passage results are
  searched alongside property results. Public references can match despite spaces
  or punctuation differences. Explicit record search can find contextual records
  excluded from the default discovery feed; source availability and rights checks
  continue to apply. Search values remain parameterized and are not SQL patterns.
- **Ownership:** the recorded portfolio and linked activity lead the owner page.
  Property rows put addresses, sale dates and assessed values before identifiers,
  and remain readable on a phone. Name-linking context is available separately.
  Model/confidence footer fields and defensive empty-state boilerplate are removed.
- **Map:** arriving through a property's map link opens its detail panel without
  a second polygon click. Adjoining parcels with the same recorded owner are
  marked in gold, with address/date/source context in the panel. Nearby planning
  information explicitly remains a nearby record rather than a project on the
  selected property.
- **Following:** watches retain their latest linked activity and distinguish
  parcel-record changes from municipal activity. Important watch-row content no
  longer disappears on mobile or truncates to an ellipsis. Local persistence and
  account persistence remain visibly different.
- **Comparison:** shared URLs carry two to four validated parcel identifiers.
  Opening a shared link uses its selection without overwriting browser selections.
  Removing properties preserves the remaining URL selection, including a separate
  zero/one-property editing state. Invalid links are distinct from empty local
  selections. Mobile displays each field with its corresponding property address.
  Zoning, constraints and relevant municipal records replace generic evidence
  counts as investigation aids. Print styling retains comparison fields and
  suppresses screen controls.

## Browser acceptance

These checks used actual local records and isolated browser workspaces, without
mocking responses or generating new explanations. Evidence is in
`output/playwright/ux-redesign/`.

| Journey                                     | Result and evidence                                                                                                                                                                                                                                                                                                                                           |
| ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Restaurant property at 2861 E Prospect Road | Recorded hearing activity is near the top of the report instead of below the site inventory. [Desktop](../../output/playwright/ux-redesign/03-property-desktop.png), [mobile](../../output/playwright/ux-redesign/04-property-mobile.png).                                                                                                                    |
| Complete mobile explanation                 | At 390 px, summary client height and scroll height both measured 183 px; computed line clamp was `none`. “Read more” showed the next check and owner link. The audit had observed a 45 px box hiding substantially more text.                                                                                                                                 |
| Source verification                         | One source action opened the exact liquor-license passage, followed by the original York Township agenda link. The source pane measured 389 px both for client width and scroll width. No technical metadata appeared. [Mobile source](../../output/playwright/ux-redesign/05-source-mobile.png).                                                             |
| Public plan reference search                | `LD 2025-5-1` found the Thornton passage containing `LD2025-5-1`. [Search result](../../output/playwright/ux-redesign/10-reference-search-fixed.png).                                                                                                                                                                                                         |
| Municipality and upcoming hearing           | York Township showed reviewed-record coverage and the September 8 date as **proposed**. [Activity](../../output/playwright/ux-redesign/15-feed-desktop.png), [municipal profile](../../output/playwright/ux-redesign/17-municipality-desktop.png).                                                                                                            |
| Municipality directory on mobile            | Typing “York Township” matched `YORK TWP`; activity/profile links remained visible. [Directory](../../output/playwright/ux-redesign/18-directory-mobile.png).                                                                                                                                                                                                 |
| Map investigation                           | The 495 Chapel Church Road panel opened automatically. The adjoining 2934 Cape Horn Road parcel was gold, with its December 1, 2025 sale date. Thornton's nearby planning point remained explicitly nearby. [Desktop](../../output/playwright/ux-redesign/14-map-linked-desktop.png), [mobile](../../output/playwright/ux-redesign/12-map-linked-mobile.png). |
| Owner investigation                         | 334 Hospitality showed its recorded portfolio and linked hearing. All five property rows retained readable addresses/sale dates at 390 px, without body overflow. [Owner](../../output/playwright/ux-redesign/16-owner-desktop.png).                                                                                                                          |
| Shared comparison recipient                 | A fresh browser with no stored comparison opened both intended properties. [Recipient](../../output/playwright/ux-redesign/08-comparison-recipient-desktop.png).                                                                                                                                                                                              |
| Shared comparison editing                   | Actual UI clicks verified three → two → one properties. The remaining property stayed selected, the URL stayed on `/compare`, and the one-property state had no Share button.                                                                                                                                                                                 |
| Mobile comparison                           | Every field labels its property; the next property is below it rather than off-screen in a concealed column. [Mobile](../../output/playwright/ux-redesign/07-compare-mobile.png).                                                                                                                                                                             |
| Watch and return                            | A temporary restaurant watch survived reload and showed the linked hearing. Its parcel-change status remained distinct and visible on mobile. The temporary watch was removed after verification. [Watch](../../output/playwright/ux-redesign/21-watch-mobile.png).                                                                                           |
| Print presentation                          | Print media retained both comparison columns and included the property activity's next check and original source passage while its screen details were collapsed. Print-only source numbering was verified. [Property print styling](../../output/playwright/ux-redesign/23-property-print.png). Native print-dialog pagination was not separately tested.    |
| Workspace and screening                     | Real activity appeared in the workspace; screening retained qualified site-investigation controls. [Workspace](../../output/playwright/ux-redesign/13-workspace-desktop.png), [screening](../../output/playwright/ux-redesign/24-screening.png).                                                                                                              |

The walkthrough caught and corrected additional issues beyond compiler checks:
comparison router navigation with absolute URLs, three-to-two selection removal,
mobile navigation overlap, hidden watch-row details, ambiguous comparison record
headlines, and public-reference spacing. Some earlier screenshots show the state
before the final small print-control and label adjustments.

## Automated verification

- Frontend tests: **39 passed**. Includes public evidence allowlisting, old/new
  ownership facts, exact PDF-page links, proposed versus historical/invalid dates,
  comparison URL states and the existing workspace/watch regressions.
- API tests: **38 passed** across feed text search, entity identity, scoped-event
  visibility, source policy and API contracts, against the dedicated
  `postgres-test` database. Explicit searches still retract unavailable records;
  punctuation and SQL-looking inputs are treated as literal search values.
- `npx tsc -b`, `npm run lint`, and `npm run build`: **passed**. The build retains
  its map-bundle size advisory; this work did not optimize mapping dependencies.
- Changed application files were formatted with the project's Prettier/Ruff
  versions. Diff whitespace checks passed.
- Delegated comparison/directory work received full primary review and browser
  integration checks. The existing orchestration ledger has an unrelated earlier
  schema error; new records were validated independently, with no trust shortcut.

## Scope and remaining validation

The UI implementation goal is complete locally. Existing source records,
explanation acceptance rules and source-use restrictions remain authoritative.
No broad LLM backfill or deployment was performed. Existing unrelated worktree
changes were preserved; a starting snapshot is in `output/ux-redesign/baseline/`.

The current data still has partial municipal coverage, records without accepted
explanations, and separate appearances that are not yet a complete project
history. The redesign makes these limitations more legible; it does not fill the
data gaps or establish development outcomes from agendas. Adjoining map context
uses available accepted explanation evidence and therefore depends on that
evidence being current.

Local sign-in is not configured. Browser persistence was verified here, and the
existing account/watch regression suite passed, but this is not a deployed
cross-device delivery acceptance test. Production follow-up and the customer
usability research proposed in the audit still need their own validation. The
recommended generation canary and backfill cost review also remain separate from
this interface implementation.
