# Existing-feature improvements — September 8, 2026

Implemented the highest-value improvements that use CountyIQ's existing records,
workspace and source metadata. This iteration does not require another inference
pass, a data backfill, or a new external service.

## Customer changes

- Municipal sources show exact retained excerpts, physical PDF page links when
  available, and **Copy excerpt & source**. Page locations are recovered from the
  current accepted evidence view and attached only when both document and selected
  wording match. Cross-page selections preserve their original wording and keep
  unlocated portions without an invented page number. Property explanations and
  feed citations use the same presenter.
- GIS sources provide readable, selected public attributes and a map action for
  the related property. Zoning and flood sources enable the corresponding layer;
  their official attribute records remain accessible. Zoning record links use
  the actual ZRECID. Map entry without coordinates resolves the property center,
  retains its selection during startup, and fits its boundary above/beside the
  property panel.
- Overview starts with followed activity when watches exist, with an explicit
  county exploration option. Activity has the same scope selector. Following
  matches any followed parcel, project, resolved organization or municipality
  before ranking and pagination. Empty follows remain empty; local and account
  watch changes refresh the scope. Featured records retain feed ranking.
- Coverage displays collection/review timestamps and the latest collected and
  reviewed meeting dates. Overview shows coverage for the featured municipality.
  Counts describe collected documents and do not imply complete municipal coverage.
- Exact, cited dates today or later offer an all-day ICS reminder from Overview,
  investigations and municipal upcoming-date lists. The export retains stated
  status, matter, municipality, supporting quote and original document URL.
  Any stated time remains in the description. Vague, historical, past or
  uncited dates have no calendar action.
- Radar offers maximum acreage and explicit linked-plan status alongside the
  existing screen. Ordinary list/map navigation carries score, municipality,
  acreage, class and plan status. Both APIs apply parcel eligibility. Readiness
  works on the map. Movers links explicitly open current scores instead of
  implying that the map plots score changes.

## Verification

- Frontend: 50 tests passed, including calendar escaping/folding and status,
  source page/URL/copy behavior, Radar query criteria, workspace synchronization,
  map viewport helpers and site routing. TypeScript, ESLint and the production
  build pass. The build retains its large lazy map-chunk warning.
- API: 36 focused tests passed across followed feed, ambiguous owner identity,
  municipal evidence, accepted source explanations, property explanation
  retraction, Radar and source-location helpers. Tests use the dedicated
  `countyiq_test` database. Radar parity fixtures include active/no-plan and
  ineligible parcels and run after source-workflow rebuilds.
- Ruff and Prettier ran on changed Python and frontend files.
- Chromium against the current local API on 8011 and frontend on 5191:
  verified empty Following; followed Loganville through the UI; confirmed
  Overview defaults to Following and its activity links retain scope; inspected
  municipal coverage and source excerpts; copied an excerpt successfully;
  verified Loganville's physical PDF page 1 link; downloaded and inspected the
  September 22 expected-meeting ICS; opened property zoning evidence and followed
  its map link; verified the selected parcel is visible above the mobile panel;
  and opened a 1–20 acre Radar screen on the map with a matching return link.
- Inspected desktop and 390px phone layouts. Mobile Overview had a 390px
  document width, with no horizontal overflow. Browser downloads and screenshots
  are local verification artifacts, not production data.

Screenshots under `output/playwright/` (ignored local artifacts):

- `customer-value-source-20260908.png`
- `customer-value-overview-mobile-20260908.png`
- `customer-value-zoning-mobile-20260908.png`
- `customer-value-radar-map-20260908.png`

## Limits

Legacy evidence without physical-page metadata still opens the original document
and shows its retained excerpt. This iteration does not generate line coordinates
or highlight text inside a publisher's PDF viewer. Publishers may replace files
at their original URLs. Map results are limited to the viewport and API result
cap. A calendar reminder does not confirm that a proposed or expected event will
occur. No production deployment was performed by this task.
