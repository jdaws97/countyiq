# CountyIQ customer experience

Status: implemented design direction, September 7, 2026.

This is the product and interaction contract for the customer application. Read
it before changing navigation, page composition, investigation content, or source
presentation. The user explicitly requested a substantial redesign around the
customer journey and durable documentation so subsequent agents would not restore
the previous layout. This records that direction; it is not evidence of customer
interviews or commercial validation.

## Customer and outcome

CountyIQ helps a small developer or acquisition team investigate a place: notice
an interesting public record, understand what it establishes, locate the property
and connections, verify the original, and retain the investigation for later.

The main journey is:

**Overview → Activity investigation → Source document → Property / organization /
municipality → Follow → Return through Following or recent work.**

Customers can also enter through search or the map. Those paths must converge on
the same property, organization and investigation surfaces. A ranking is an entry
point for research, not the central explanation of why a property matters.

## Page and interaction contracts

| Surface        | Customer question                                 | Required composition                                                                                                                                                                                                  |
| -------------- | ------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Overview       | What is worth looking into, and where was I?      | A real featured record with a parcel preview when linked; dates with matter names and their stated status; a short list of further activity; recent work and saved searches.                                          |
| Activity       | What does this record mean for my investigation?  | Desktop record queue beside one focused reading pane. Complete account, dates, next check when available, conditions and milestones, source documents, connected property and organizations.                          |
| Property       | What is this place, and what do we know about it? | Address and owner beside an actual parcel map; follow/compare actions; separate Activity, Site & ownership, Property records and Sources views.                                                                       |
| Map            | Where is it in relation to other places?          | The shared workspace shell around a full-height map. Property entry selects and opens that property. Accepted adjoining ownership is distinct from the selected parcel; nearby planning context is explicitly nearby. |
| Following      | What should I return to?                          | Saved subjects and their linked activity. Scope parcel-record change labels accurately. Preserve guest export/import and account synchronization.                                                                     |
| Comparison     | How do these specific properties differ?          | A small property set, comparable diligence facts, links to relevant records, and mobile values labeled by property. A copied URL must carry the selection.                                                            |
| Organizations  | What does this recorded owner hold?               | Address-led portfolio, sale dates and source-backed activity. Identity details are secondary; an ownership name match is not a proven corporate relationship.                                                         |
| Municipalities | What is happening here, and what is covered?      | Searchable local-government directory leading to activity, stated dates and source coverage. Tax aggregates are secondary research context.                                                                           |

### Workspace shell

`WorkspaceShell` owns grouped persistent navigation, global search, account state
and theme. Desktop uses a restrained deep-teal sidebar and a small utility bar.
Phones use a keyboard-accessible drawer. Use `PageShell` for normal pages and the
shared map mode for the map. Do not reintroduce an independent top navigation or a
second navigation scheme for individual customer pages.

The visual direction uses serif titles, readable sans-serif accounts, a quiet
neutral background, teal actions and limited olive accents. Whitespace separates
the main decision from supporting context. Maps contain real geometry rather
than decorative graphics implying a location. Data labels, dates and body text
must remain legible; long titles wrap naturally.

### Overview

A first visit should show actual available intelligence, not a wall of empty
workspace widgets. Featured and additional records come from the available feed;
no synthetic sample activity or invented urgency. The date panel describes only
dates in the loaded results and preserves proposed/expected status. It is not a
complete municipal calendar. The customer must be able to identify the matter
behind a date without opening it.

On phones, the featured title and investigation action precede the map. Recent
work supports recognition. Account-specific watch and synchronization behavior
continues to belong to the existing workspace implementation.

Overview defaults to **Following** when the workspace has followed subjects;
otherwise it starts with **Explore county**. Both scopes remain selectable.
Following includes records matching any followed property, project, organization
or municipality, with filtering before pagination. An empty followed result
must stay empty. It must not silently substitute county activity. Activity links
retain this scope, and watch changes refresh the results.

Exact upcoming dates with a source citation offer an all-day calendar reminder.
The reminder retains proposed, expected, scheduled or deadline status, the
supporting quote and original URL. Any stated time is included in its description;
do not invent a timezone or represent a proposal as a confirmed appointment.
Vague and historical dates do not receive this action.

Municipal coverage distinguishes collected records from reviewed records and
shows collection/review dates when known. These counts describe collected
documents, not completeness of all municipal activity.

### Property screening

Radar exposes minimum/maximum acreage and recorded active-plan status. Ordinary
Radar views carry score, municipality, acreage, property class and plan criteria
into the map and back to the list. Both surfaces apply the same eligibility rule.
The map covers its visible extent and may be capped. Movers compares snapshots;
its map link explicitly opens current scores, since the map does not plot deltas.

### Activity investigation

The queue is a selection surface, not thirty expanded reports. Desktop shows the
selected account beside it. On narrow screens the customer selects a record,
reads it, and uses **Back to activity** to return to the list. Selection is carried
in the URL; an unavailable selection must never silently display a different
record as if it were the requested one. Filters clear the previous selection.

The account and source-document views serve different reading tasks. Inline
citations can also open the shared source viewer without leaving the account.
The account always presents complete prose: no persistent two-line clamp after
opening, no unexplained citation tokens, and no nested chain of disclosures to
reach the basic explanation.

An explanation must not replace structured conditions or milestones. Preserve
those facts from the underlying proceeding and their original citation indexes.
A future date or stated milestone does not establish that an action occurred.
Where a next check is unavailable, omit it rather than manufacture advice.

### Property investigation

The header establishes identity and location. The four views replace the former
long vertical stack of repeated summaries, score boxes and receipts. View state
is in the URL; legacy `#property-*` section links remain usable on entry.

- **Activity:** a complete selected account. Multiple records have a selectable
  history; a single record does not need a duplicate one-item navigation column.
  No-activity states distinguish limited coverage from a finding of no change.
- **Site & ownership:** land, assessment, last sale, current zoning, flood/soil
  context, unresolved diligence questions, and accepted ownership connections.
  Additional property synthesis remains available here.
- **Property records:** detailed assessment, legal/public identifiers, sale,
  structures, tax, soil and screening records. Scores are secondary and explain
  their scope; they do not establish sale availability or buildability.
- **Sources:** linked municipal records and property-source access.

A property printout must retain the other property views and the selected
activity's account and supporting source wording. Screen view selection must not
silently strip essential context from printed output.

## Evidence and language rules

Customer-facing prose and excerpts are English, including intelligence derived
from Spanish or mixed-language municipal PDFs. Preserve original documents,
literal source spans, proper names and identifiers. Store translations separately
with the accepted explanation, label them as translations in the source viewer
and copied excerpts, and retain the original PDF's verified starting page. Never
split translated text using offsets in the original language or call a translation
verbatim wording. Withhold excerpts awaiting an English presentation instead of
falling back to raw non-English text. Original document links may open the original
language outside the application.

Keep exact public record titles, dates, relevant quoted wording, page references,
source links and clear relationship descriptions. Use the shared customer field
allowlist in `customerEvidence.ts`. Retain public parcel identifiers and deed
book/page when useful for locating a legal record.

Do not render serialized evidence dictionaries. Hashes, event keys, inference IDs,
model names, prompt/schema versions, scoring weights and internal linkage metadata
belong outside the customer UI, including its advanced disclosures. New source
facts require a deliberate customer presenter, not a broader catch-all renderer.

Keep the distinctions that matter to an investigation:

- Agenda proposal, recommendation, scheduled event and recorded decision are
  different states. Passing a proposed date does not turn it into a completed
  hearing or an approval.
- Approval can be conditional; conditions and completion remain separate.
- Current zoning, proposed rezoning and future land-use policy are different.
- Nearby, adjoining, same recorded owner and project membership are different.
- Missing coverage and an absence of events are different.
- An assessed value is not an asking price; a screen is not a verified condition.

Source absence must be visible and truthful. An original-document button should
open the relevant page when the source provides a reliable page reference. Never
invent a source, resolved property, project boundary, utility connection or
confirmed date to make a page look complete.

Each retained municipal excerpt can be copied with its source attribution and
opened at its physical PDF page when reliable page metadata exists. Preserve
the original selected wording across page boundaries. Do not derive line numbers
from wrapped screen text. Without page metadata, provide the document and exact
excerpt without promising a page jump. GIS evidence leads to the related property
on the map, enabling the relevant available layer, and retains the official data
record as a separate source action.

## Change discipline

Treat the composition above as the default for later work. Do not restore the old
stacked feed, score-first property page, metadata-heavy receipts or detached map
navigation as a convenient implementation shortcut. Reuse the shared components.

This document does not freeze the product or require a separate approval for
routine fixes. An explicit user-requested design change can replace these choices.
When changing a primary journey, document the new customer rationale here and
verify the complete journey in a real browser. Automated tests cannot establish
whether the result is appealing or easy to scan.

## Acceptance checklist

Use current, real local records and inspect screenshots at a desktop width and
390px phone width; include an intermediate width for the activity workspace.

1. A first visit exposes a meaningful record and an obvious investigation action.
2. Open it from the overview. The same record appears in the reading pane. On a
   phone, return to the activity list without losing the available results.
3. Read a long account, a proposed date and a conditional decision. Verify full
   prose, date status and condition/milestone sources rather than only headings.
4. Open an inline citation and the source-document view; read the original wording
   and follow the document link. No internal metadata leaks into the customer UI.
5. Open a linked property; switch all four views; follow it; reload; revisit it
   through Following. Remove only test watches created during verification.
6. Open the map from that property's actual link. Confirm the selected boundary,
   context panel, adjoining ownership and return link; exercise a map filter.
7. Check global search, mobile navigation, keyboard focus and Escape, short-screen
   drawer scrolling, light/dark theme persistence and horizontal overflow.
8. Open a comparison URL in a fresh browser context; inspect labeled phone values.
9. Check print media for account and source retention. Native PDF pagination is a
   separate check and must not be claimed from CSS emulation alone.
10. Run the frontend formatter, typecheck, lint, relevant tests and production
    build. Map libraries must remain outside the initial application bundle.

See [frontend architecture](architecture.md) for implementation boundaries,
[the workflow audit](../research/customer-workflow-ux-audit-2026-09-07.md) for the
original evidence, and [the redesign verification](../research/customer-workspace-redesign-2026-09-07.md)
for this iteration's actual checks and screenshots.
