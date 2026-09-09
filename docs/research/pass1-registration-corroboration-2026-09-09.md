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

The model review found the same gap in non-deterministic outputs: a registration
identifier printed only in corporate rows was being used to attach other parcels
with unconnected addresses. The prompt now explicitly requires an independently
supported connection for those records. Its version changes, while ordinary
source snapshots remain unchanged. Existing results must receive actual source
review. Changed identity decisions go through the normal same-source
contradiction process; old inference rows and model receipts remain immutable.

Voting now counts whether each candidate is assigned to an entity, in addition
to cross-name merge decisions. Two trials that agree not to merge names can
still disagree about a singleton's identity. That disagreement requires a third
trial, and a failed third call cannot create majority support for the singleton.
The execution hash includes the voting version. Archived responses retain their
actual prompts and can be reused only for identical requests.

Both ordinary publication and contradiction resolution project relationships
only when their target belongs to an accepted entity in the same partition.
Member aliases resolve to that entity's canonical name; internal edges are
omitted. Qualified observations about unresolved candidates remain in the
immutable inference without becoming owner links in downstream context. The
Pass 1 quality identity now includes the contradiction projector's source file.

Ordinary truncated portfolio prompts are now deferred before reuse or model
execution. A name-level owner projection can include records outside the prompt's
50-parcel or 30-tax-row detail limit. Those cases need the bounded dossier path,
which fingerprints the complete inventory and exposes every parcel's mailing
address and identifier. A sample of records cannot silently verify the rest.

The first production audit found 69 active deterministic partitions, of which
62 require model review under this intentionally narrow rule. That is a review
queue, not a count of proven identity errors: source review may establish
ordinary address abbreviations or other explicit connections. The backfill is
paused at batch boundaries before Pass 2 consumes the refreshed identities.

Validation: 1,977 non-integration pipeline tests passed; 137 integration tests
were deselected. Changed Python files passed Ruff formatting and lint checks.
Regression coverage includes unconnected addresses, street-number separation,
different five-digit ZIPs, claims without a connected parcel, truncated
portfolios, license/applicant records, disabled model execution, singleton vote
disagreement, failed deciding calls, and relationship projection through both
publication paths without mutating the inference payload.
