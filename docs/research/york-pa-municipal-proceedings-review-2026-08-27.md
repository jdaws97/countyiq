# York County Municipal Proceedings Review

**Review date:** 2026-08-27
**Scope:** all 72 York County municipalities and every governing, planning,
zoning, and county proceedings source configured for CountyIQ

## Recorded coverage

- 110 configured municipal/body source entries across 65 municipalities.
- 107 distinct listing URLs.
- 63 of 72 municipalities have an active main governing-body source.
- 65 of 72 have at least one configured proceedings source.
- 122 policy records cover all 72 municipalities: 110 conditional sources and
  12 paused body policies.

The explicit gaps are:

| Municipality | Main-body result | Disposition |
|---|---|---|
| Cross Roads Borough | No official web proceedings source located | Council paused; do not infer no activity |
| Railroad Borough | No official web proceedings source located | Council paused; do not infer no activity |
| Shrewsbury Township | Main minutes are delivered through eCode360 | BOS paused; separately configured ZHB source remains conditional |
| Dover Township | Combined BOS/ZHB archive delegates delivery to Rep'd, whose terms limit site/content use to personal, non-commercial use | BOS and ZHB paused; separately configured planning source remains conditional |
| West York Borough | Documents delivered through an unreviewed Google Drive origin | Council paused pending written permission or borough-hosted originals |
| West Manheim Township | Official robots policy explicitly disallows the three reviewed paths | BOS, PC, and ZHB paused |
| Franklintown Borough | Useful documents are GoDaddy-CDN-only | Council paused under current vendor crawler/resale terms |
| Newberry Township | Useful documents are GoDaddy-CDN-only | BOS paused under current vendor crawler/resale terms |
| Washington Township | Useful documents are GoDaddy-CDN-only | BOS paused under current vendor crawler/resale terms |

## Reachability snapshot

The retained policy-authorized audit covers every policy row. Among active
sources it recorded 96 healthy body listings, five robots-uncertain blocks,
four access errors, and five successful pages with no supported documents.
Those five pages received the production Playwright fallback and still exposed
no collectable documents. The other 12 rows are explicitly paused.

Across policy rows, 7,154 document links were discovered and 7,152 were
collectable under the exact origin policy. One unrelated Pennsylvania
open-records link and one misspelled insecure external host were rejected. The
counts intentionally include separately governed bodies that share a listing;
they are health evidence, not a unique-document inventory. The complete
row-level result is retained in
`york-pa-municipal-source-static-audit-2026-08-27.json`; no page HTML or
document bodies are retained by the audit.

## Use decision

Official publication makes the proceedings available for public observation,
but does not create one uniform commercial license across municipal and vendor
sites. Each usable entry is therefore conditional, with private evidence
retention only where expressly permitted, factual extraction and short evidence
references instead of packet republication, no source-equivalent export, and a
review due date of 2026-11-27. Reachability, a missing terms page, or `robots.txt`
permission cannot independently elevate a source to green.

## Runtime enforcement

Migration 032 seeds the body-level registry. Migrations 033 and 034 add exact
origin allowlists, pause restricted vendor/robots paths, and approve only
observed same-organization HTTPS aliases. Before network access, the proceedings
assets verify the exact county, municipality, body, listing URL, proceeding
type, acquisition method, rights status, terms review, review date, and allowed
origin. Every redirect destination is authorized before access. Browser
document/XHR/fetch calls cannot cross to an unreviewed origin. Listing and
document requests share a cached, fail-closed robots policy; legacy HTTP links
upgrade only to a reviewed HTTPS origin; content is checked by file signature;
one document cannot be silently attributed to multiple bodies; raw retention
requires a separate permission; and every allow/deny decision is written to an
append-only ledger. Current listing/document health is stored separately and
exposed in the operations API.

A mixed-origin listing is not treated as all-or-nothing. Approved first-party
documents continue through the robots, content, and retention checks, while
unreviewed document links are excluded before download and counted in Dagster
metadata and source-health detail. This preserves lawful municipal signal
without allowing one unrelated or vendor-hosted link to become an origin
bypass—or to fail the approved part of the archive.

This architecture preserves the development signal from authorized sources
while ensuring missing, blocked, changed, or unreviewed municipal sources are
visible as gaps rather than silently scraped or counted as no activity.
