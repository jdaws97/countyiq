# Proceedings metadata review — September 5, 2026

Version `proceeding-metadata-6` fixes source-selection errors found while
preparing fresh Pass 0 canaries. The final dry run covers 6,459 current rows:
3,511 ready and 2,948 requiring review, with 488 ready documents dated in 2026
through September 5. It proposes 638 preserved-source SCD2 replacements and
5,821 annotation updates. **This cleanup has not been applied.** No proceeding
extractions exist against the affected rows. These are metadata classifications,
not evidence of model quality or permission to run the full backfill.

The final artifact is
`output/production-readiness-2026-09-05/metadata-v6/source-conflict-local-dry-run.json`.
It hashes the source snapshot and both parser/review modules. Earlier draft
plans remain alongside it for diagnosis and must not be applied.

## Source findings and changes

- Codorus source 7679 has board members followed by a line break before
  “present.” The old date boundary missed attendance and mistook an earlier
  plan approval for a second meeting date. Its June 25, 2024 date is now
  recognized; the unconfigured planning-board identity still requires review.
- East Manchester source 8399 starts with an August 21, 2025 budget agenda.
  An October parade date is agenda business. Date extraction now ends at the
  first numbered item after the agenda title. The document is explicitly named
  as an agenda/minutes packet and remains held even after date correction.
  The same packet check catches earlier canary 2217; its prior evaluation
  remains historical diagnostic evidence, not a current eligible source.
- Qualified agenda titles must occur before meeting business. Ordinary consent
  agenda sections and minutes-approval continuations do not establish a second
  document. Explicit combined filenames still require review when the recorded
  meeting has a heading such as “Financial Review.”
- Trailing slashes no longer hide exact dates in document permalinks. Red Lion
  9114 and 9130 had acquired prior-minutes dates; their documented dates are
  February 10, 2025 and February 13, 2023, respectively.
- Full dates with missing spaces or a dot before the year are recognized.
  Yearless month/day wording can contradict a filename without manufacturing a
  header year. Genuine conflicting opening dates stay held.

Root rejected a preliminary assistant review that reported no unresolved dates.
Its own excerpts showed contradictions in 7442, 7443, 7446, 7719, 8000, 8047
and 8906. The corrected parser holds all seven. For example, 7442 says
March 4,2023, then describes a February 5,2024 opening, while its URL says
March 4,2024. Felton 8000 says June 3rd while its URL says June 2nd. Repeating
the parser's result was insufficient source verification.

Pass 0 dispatch now requires the current metadata review version as well as
ready status and a meeting date no later than today. A prior ready annotation
cannot silently authorize a document under changed rules. The quality receipt
also binds the metadata module and shared date parser. The future York City
agenda 6710 remains an offline diagnostic candidate until its September 14
meeting date; it was not included in the fresh paid test.

Validation: 1,435 pipeline unit/regression tests pass, 124 integration tests
deselected in that run. All eight metadata transaction/eligibility integration
tests pass against `countyiq_test`; the Dagster definitions import passes.
The tests preserve source history, reject stale/missing review versions,
exercise real date/packet failures and retain conflicting-date controls.
