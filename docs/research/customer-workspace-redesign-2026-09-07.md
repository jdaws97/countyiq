# Customer workspace redesign — September 7, 2026

This iteration changes the product's composition and reading flow. It follows the
user's feedback that the preceding cleanup retained too much of the old layout.
The result is implemented in the local application and checked against real local
property and municipal records. It has not been deployed.

## What changed

The application now starts with a featured investigation, actual parcel geometry,
stated upcoming dates, further activity and recent work. The shared desktop
sidebar groups exploration, research and saved work; phones use a drawer. The map
uses that same shell.

Activity is a record queue beside a focused reading pane. The account has complete
prose, stated dates, a next check when supplied, conditions and milestones, and
connected property context. Source documents have a separate reading view and
inline citations still open the shared source viewer. On phones, selecting a
record opens its account and returning restores the previous list position.
Search results open this same investigation surface.

Properties now have an address/owner header beside a real parcel map, followed by
Activity, Site & ownership, Property records and Sources views. A single activity
record does not get a redundant one-item navigation column. Detailed property
records and additional synthesis remain available without competing with the
initial investigation.

The map's large screening button strip became one labeled selector. Its initial
property fit now accounts for the open details panel, including the phone's bottom
sheet. Both the selected boundary and its adjoining ownership can be seen in the
verified Chapel Church example.

## Durable design direction

[Customer experience](../frontend/customer-experience.md) documents the intended
journeys, the composition of each surface, source and status rules, mobile
behavior and a browser acceptance checklist. `AGENTS.md` now directs future UI
work to that document. [Frontend architecture](../frontend/architecture.md) has
been updated to describe the actual components and replace the obsolete stacked
feed and metadata-heavy evidence presentation.

The contract allows deliberate user-requested changes. It asks future work to
preserve the customer rationale and verify affected journeys, rather than treating
the old layout as a convenient default. This is an implemented design judgment;
customer interviews and commercial validation have not been conducted here.

## Browser evidence

Screenshots were captured from the real local app with Playwright, at 1440px,
1280px and 390px viewport widths. Intermediate screenshots remain in the output
folder; the following illustrate the resulting design and meaningful checks.

| Check                      | Result and evidence                                                                                                                                                                                                                                                                             |
| -------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Overview and real activity | [Desktop overview](../../output/playwright/ux-iteration-2/24-final-overview-desktop.png) and [final phone overview](../../output/playwright/ux-iteration-2/27-final-overview-mobile.png). Actual records, dates and geometry; no mock data.                                                     |
| Focused activity           | [Desktop reading pane](../../output/playwright/ux-iteration-2/25-final-activity-desktop.png) and [1280px layout](../../output/playwright/ux-iteration-2/11-activity-1280.png).                                                                                                                  |
| Property composition       | [Final desktop property](../../output/playwright/ux-iteration-2/26-final-property-desktop.png), [phone header](../../output/playwright/ux-iteration-2/05-property-mobile.png), and [site view](../../output/playwright/ux-iteration-2/04-site-desktop.png). All four views exercised.           |
| Full phone account         | [Phone account](../../output/playwright/ux-iteration-2/06-property-account-mobile.png). The activity summary measured 269px client/scroll height, with no line clamp.                                                                                                                           |
| Source reading             | [Source-document view](../../output/playwright/ux-iteration-2/07-source-mobile.png). Inline citation opened the agenda source; Escape returned focus to the citation. Tested source text contained no hash, event key, inference ID, explanation version or score weight.                       |
| Phone list return          | Selected the fifth record after scrolling. **Back to activity** restored the same 964px scroll position and showed the queue.                                                                                                                                                                   |
| Selected map fit           | [Phone map](../../output/playwright/ux-iteration-2/20-map-fit-mobile.png). The Chapel Church boundary fits above the sheet, with adjoining ownership in gold. Desktop map height was 832px beneath a 68px utility bar in a 900px viewport. Map screening selector exercised.                    |
| Public-reference search    | Searching `LD2025-5-1` returned the Thornton source record, and [opened that exact investigation](../../output/playwright/ux-iteration-2/19-search-investigation.png).                                                                                                                          |
| Following                  | Restaurant follow survived reload and appeared in [Following](../../output/playwright/ux-iteration-2/21-following-mobile.png). The temporary watch was removed afterward.                                                                                                                       |
| Shareable comparison       | [Fresh-context phone comparison](../../output/playwright/ux-iteration-2/22-comparison-fresh-mobile.png) loaded both properties from the URL without prior browser storage. Document width was 390px.                                                                                            |
| Navigation and theme       | [Phone drawer](../../output/playwright/ux-iteration-2/09-mobile-navigation.png) and [dark theme](../../output/playwright/ux-iteration-2/10-overview-dark-mobile.png). Escape returned focus to Menu; page scrolling was restored after close. Theme state is shared between desktop and drawer. |
| Print retention            | With the Sources property view selected, print media still displayed activity, property records, the full account and source appendix; sidebar was hidden and its offset was zero. [Print-layout capture](../../output/playwright/ux-iteration-2/23-print-layout.png).                          |

The final phone overview differs from the earlier intermediate capture: its
featured title and action now appear before the map. Later refinements also
increased small activity metadata type and reduced the mobile save-search action.

## Automated checks

- **43 frontend tests passed.** New regressions cover explanation/proceeding
  coexistence, preserved condition/milestone source positions, unavailable facts,
  and fitting a property around desktop and phone panels.
- **TypeScript, lint and production build passed.** MapLibre and deck.gl remain
  in the map route's large chunks, outside the initial application bundle.
- **Prettier and `git diff --check` passed.** The source changes were compared
  with the snapshot taken before this iteration to preserve unrelated work.

Logs: [tests](../../output/ux-iteration-2/checks/tests.txt),
[lint](../../output/ux-iteration-2/checks/lint.txt),
[build](../../output/ux-iteration-2/checks/build.txt), and
[formatting](../../output/ux-iteration-2/checks/format.txt).

The production build retains its existing large-map-chunk advisory. Native PDF
pagination was not separately tested. Account sign-in and cross-device delivery
cannot be verified in this local guest preview. No API or pipeline behavior was
changed in this iteration; no backfill, paid model run or deployment was performed.
