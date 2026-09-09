# Corroborating records before deterministic registration attachment

Status: candidate pending source-reviewed correction and release binding.

The exact-registration shortcut previously attached all records whose printed
owner name normalized to an unambiguous PA DOS legal name. That registration
identified the corporation, but did not independently connect every same-name
parcel to it. The original FF YORK / FFYORK canary, for example, included
Wicklow Drive and Market Street mailing addresses without a supplied bridge.
Its structural acceptance did not establish that cross-record identity.

The revised shortcut requires every parcel mailing address to match a
registration office. It ignores case, commas, periods, repeated spaces and an
optional ZIP+4 extension; street tokens, unit designators, locality, state and
the five-digit ZIP remain significant. A tax claim must use the identifier of
an already connected parcel. Licenses, proceedings, truncated portfolios and
unconnected records go to the existing model review. Uncertainty does not
trigger a paid fallback when model execution is disabled.

The deterministic execution version changes, while the LLM prompt and ordinary
source snapshots remain unchanged. Existing results that lose eligibility must
receive actual source review. Changed identity decisions go through the normal
same-source contradiction process; neither old inference rows nor immutable
model receipts are rewritten.

The first production audit found 69 active deterministic partitions, of which
62 require model review under this intentionally narrow rule. That is a review
queue, not a count of proven identity errors: source review may establish
ordinary address abbreviations or other explicit connections. The backfill is
paused at batch boundaries before Pass 2 consumes the refreshed identities.

Validation: 1,971 non-integration pipeline tests passed; 137 integration tests
were deselected. Changed Python files passed Ruff formatting and lint checks.
Regression coverage includes unconnected addresses, street-number separation,
different five-digit ZIPs, claims without a connected parcel, truncated
portfolios, license/applicant records, and disabled model execution.
