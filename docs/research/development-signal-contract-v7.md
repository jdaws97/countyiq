# Development signal contract — score version 7

Version 7 makes the customer-facing statement for every Development Momentum signal match its deterministic trigger. Each property row must expose the source fact, spatial or record-match basis, score effects, and a non-claim/caveat. Optional LLM validation remains annotation only and never changes a score.

## Score contract

- **Development Momentum** is the clipped sum of activity points for active/nearby plans, municipal matters, park inventory, ownership changes, same-name contiguous ownership, tax-delinquency presence, plan/zoning divergence, PennDOT projects, development overlays, traffic counts, and growth areas.
- **Opportunity** uses separately calibrated signal weights, is zero without a parcel-level gate signal, and is forced to zero when the parcel has its own recent plan or municipal matter.
- **Site Screening** starts at 50. Its only adjustments are: economic park +25; growth area +10; development overlay +5; traffic +5; non-completed PennDOT project +5; lightly improved screen +5; soil −15; special-purpose zoning overlay −15; SFHA overlap −20; nearby DEP record −10.
- **Eligibility** is removed only by a mapped agricultural conservation easement. Agricultural Security Area enrollment is context only and changes no score.

## Cross-referenced signals

| Signal | Deterministic trigger | Accurate customer statement | Important non-claim | Score effects |
|---|---|---|---|---|
| `active_subdivision` | Believable county planning point received within 3 years intersects or is within 30 m of the parcel | Plan point mapped on the parcel, or exact distance from its boundary | A point is not a surveyed plan boundary, approval, or permit | Momentum +30; Opportunity gate forces parcel to active-plan view |
| `nearby_subdivision` | Same planning filter, 30–250 m from parcel | Nearby plan point with distance and title | It is not this parcel's plan | Momentum +8; Opportunity +10 |
| `economic_development_park` | Exact PIDN in county business/industrial park inventories | Parcel is mapped in named official park inventory | No automatic zoning, incentives, utilities, or entitlement | Momentum +15/+18; Opportunity +22; Site +25 |
| `municipal_action` | Governed proceeding linked by exact PIDN or municipality-scoped normalized address within 24 months | Municipal matter, decision, date, and match method | Address matches can be ambiguous; a matter is not necessarily approved | Momentum +4 to +20; active-plan gate |
| `zoning_mismatch` | Current zoning and adopted future-land-use categories differ at parcel center | Parcel-center plan/zoning divergence | Future land use is policy, not current zoning; center point can miss split parcels | Momentum +10; Opportunity +6 |
| `ownership_change` | Non-nominal parcel sale in past 12 months | Recorded sale; optionally notes an organization-looking buyer name | Name pattern is not a verified investor classification or proof of intent | Momentum +6/+8/+10; Opportunity +4 |
| `vacancy` | No intersecting county building footprint plus low-value filters | No mapped footprint; low-value screen | Does not prove vacancy or buildability; footprint data can lag | Opportunity +12; Site +5 |
| `tax_distress` | PIDN has positive balance in governed current tax-claim listing | Current tax-delinquency indicator | Exact claim rows and balances are suppressed; verify with bureau | Momentum +10; Opportunity +4 |
| `assemblage` | Parcel intersects configured minimum count of differently named owners' parcels | Neighbor ownership/topology pattern | Can mean opportunity or fragmentation; does not prove assemblage | Opportunity +15 |
| `entity_assemblage` | Exact normalized recorded owner name on touching parcels and a recent non-nominal acquisition | Same-name contiguous ownership after recent acquisition | Name matching is not entity resolution and does not prove coordinated intent | Momentum +10/+15; Opportunity +23 |
| `penndot_project` | Closest non-completed PennDOT project point within 800 m | Published status, project name, and distance | A project point does not establish parcel impact, access, funding, or timing | Momentum +3; Opportunity +2; Site +5 |
| `development_overlay` | Parcel center in municipal overlay typed `DEVELOPMENT` | Parcel center mapped in named development overlay | Overlay is context, not automatic permission | Momentum +4; Opportunity 0; Site +5 |
| `local_traffic_activity` | Qualifying county count from last 5 years within 400 m of parcel center | Source-reported volume, year, purpose, and distance | Not assumed to be current AADT | Momentum +1/+2/+4; Opportunity +2; Site +5 |
| `growth_area` | Parcel center in county Primary or Secondary Growth Area | Parcel center lies in named growth-area class | Policy does not override zoning, sewer capacity, constraints, or approvals | Momentum +2; Opportunity +5; Site +10 |
| `soil_constraint` | A mapped soil unit covering at least 5% of parcel has representative slope ≥15%, poor/somewhat-poor drainage, or hydrologic group D | Exact triggering unit, parcel share, slope/drainage/runoff reason, plus all mapped units | Generalized soil mapping is not a site investigation; `Well drained` does not cancel slope or septic limitations | Opportunity −3; Site −15 |
| `zoning_constraint` | Parcel center in airport, historic, steep-slope, underground-mining, or wellhead overlay | Parcel center lies in named special-purpose overlay | Verify boundary and requirements in current municipal ordinance | Opportunity −1; Site −15 |
| `environmental_diligence` | Closest public PA DEP record within 500 m of parcel center | Facility/site, published status, layer, and distance | Proximity is not a contamination finding or regulatory determination | Opportunity 0; Site −10 |
| `flood_zone` | FEMA Special Flood Hazard Area geometry overlaps at least 1% of parcel geometry | Exact parcel-overlap percentage and mapped zones | Not an official determination or statement that a structure lies in the SFHA | Opportunity −2; Site −20 |
| `conservation_easement` | Exact PIDN in county agricultural conservation-easement inventory | Recorded agricultural conservation easement | Confirm the deed and any permitted building area | Eligibility exclusion; scores 0 |
| `ag_security` | Exact PIDN in county Agricultural Security Area inventory | ASA enrollment; explicitly not a development prohibition | Pennsylvania says ASA enrollment does not itself prevent sale, subdivision, or development | Context only; no score effect |

## Authoritative interpretation references

- York County Planning Commission open-data services: <https://arcweb1.ycpc.org/server/rest/services/OPEN_DATA>
- FEMA National Flood Hazard Layer: <https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer>
- PennDOT published project service: <https://gis.penndot.gov/arcgis/rest/services/paprojects/paprojects/MapServer>
- Pennsylvania DEP public GIS data: <https://gis.dep.pa.gov/depgisprd/rest/services>
- Pennsylvania Agricultural Security Areas: <https://www.pa.gov/agencies/pda/plants-land-water/farmland-preservation/agricultural-security-areas>
- York County agricultural conservation easement FAQ: <https://www.yorkcountypa.gov/FAQ.aspx?QID=303>

The property API resolves ArcGIS sources to record-level queries when stable source keys exist. Every signal still carries a caveat because these layers are screening evidence rather than legal, engineering, environmental, or insurance determinations.
