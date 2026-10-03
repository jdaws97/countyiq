"""Large entity portfolios must preserve unknown facts in hashable source data."""

from unittest.mock import Mock

import pytest
from countyiq.lib.intelligence_common import compute_input_hash
from countyiq.lib.pass1_entity_verification import (
    build_entity_cluster_prompt,
    gather_cluster_records,
)


@pytest.mark.parametrize(
    ("field", "summary_key", "known"),
    [
        ("owner_full", "owners", "EXAMPLE LLC"),
        ("class", "classes", "COMMERCIAL"),
        ("municipality", "municipalities", "Example Township"),
    ],
)
def test_large_portfolio_preserves_null_counts_and_has_a_stable_hash(
    field, summary_key, known
):
    parcels = [
        {
            "pidn": f"P{index:03}",
            "owner_full": "EXAMPLE LLC",
            "class": "COMMERCIAL",
            "municipality": "Example Township",
            "aprtotal": 100,
        }
        for index in range(60)
    ]
    # Include known values, a SQL NULL, and an absent field in the full portfolio.
    # Put the missing values beyond the detailed rows retained in the prompt.
    parcels[-2][field] = None
    del parcels[-1][field]
    cursor = Mock()
    cursor.fetchall.side_effect = [parcels, [], [], [], []]

    records = gather_cluster_records(cursor, ["EXAMPLE LLC"])

    summary = records["portfolio_summary"]
    assert summary[summary_key] == {known: 58, "?": 2}
    assert summary["total_parcels"] == 60
    assert summary["total_assessed_value"] == 6000
    assert "'?': 2" in build_entity_cluster_prompt(records)
    fingerprint = compute_input_hash(records)
    assert len(fingerprint) == 64
    summary[summary_key] = dict(reversed(list(summary[summary_key].items())))
    assert compute_input_hash(records) == fingerprint
