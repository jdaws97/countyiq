"""Asset checks for the enrichment group's output tables.

The 2026-08 review found zero checks on the tables the product actually
serves — a green enrichment run proved nothing about whether evidence,
briefs, or signals exist. These are deliberately coarse (row-count > 0):
they catch "the pass silently produced nothing" without flaking on
legitimate low-volume weeks.

Severity split:
- ERROR on deterministic rebuilds (development_signals, development_momentum,
  owner_resolution): rebuilt from source data every run, empty = broken.
- WARN on LLM-produced tables: legitimately empty on a fresh environment
  until the first backfill completes.
"""

from dagster import AssetCheckSeverity

from countyiq.assets.enrichment.brief_generation import brief_generation
from countyiq.assets.enrichment.county_narratives import county_narratives
from countyiq.assets.enrichment.development_momentum import development_momentum
from countyiq.assets.enrichment.development_signals import development_signals
from countyiq.assets.enrichment.entity_verification import entity_verification
from countyiq.assets.enrichment.owner_briefs import owner_briefs
from countyiq.assets.enrichment.owners import owner_resolution
from countyiq.assets.enrichment.signal_validation_batched import signal_validation_batched
from countyiq.lib.checks import make_row_count_check

development_signals_nonempty = make_row_count_check(
    development_signals,
    table="development_signals",
    schema="public",
    where=None,
    name="development_signals_nonempty",
)

development_momentum_nonempty = make_row_count_check(
    development_momentum,
    table="development_momentum",
    schema="public",
    where=None,
    name="development_momentum_nonempty",
)

owners_nonempty = make_row_count_check(
    owner_resolution,
    table="owners",
    schema="public",
    where=None,
    name="owners_nonempty",
)

evidence_nonempty = make_row_count_check(
    signal_validation_batched,
    table="evidence",
    schema="public",
    where=None,
    severity=AssetCheckSeverity.WARN,
    name="evidence_nonempty",
)

parcel_briefs_nonempty = make_row_count_check(
    brief_generation,
    table="parcel_briefs",
    schema="public",
    where=None,
    severity=AssetCheckSeverity.WARN,
    name="parcel_briefs_nonempty",
)

owner_briefs_nonempty = make_row_count_check(
    owner_briefs,
    table="owner_briefs",
    schema="public",
    where=None,
    severity=AssetCheckSeverity.WARN,
    name="owner_briefs_nonempty",
)

entity_graph_nonempty = make_row_count_check(
    entity_verification,
    table="entity_graph",
    schema="public",
    where=None,
    severity=AssetCheckSeverity.WARN,
    name="entity_graph_nonempty",
)

county_narratives_nonempty = make_row_count_check(
    county_narratives,
    table="county_narratives",
    schema="public",
    where=None,
    severity=AssetCheckSeverity.WARN,
    name="county_narratives_nonempty",
)
