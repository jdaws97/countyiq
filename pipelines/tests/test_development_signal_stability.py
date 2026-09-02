"""Regression coverage for stable deterministic signal evidence."""

from countyiq.assets.enrichment.development_signals import _SIGNALS


def test_signal_evidence_does_not_include_rebuild_timestamp():
    sql = "\n".join(query for _key, query in _SIGNALS)

    assert "evidence_captured_at" not in sql


def test_municipal_action_address_match_is_scoped_to_municipality():
    sql = dict(_SIGNALS)["municipal_action"]

    assert "FROM meta.municipality_source_rights msr" in sql
    assert "msr.body_name = pp.body_name" in sql
    assert "msr.municipality_name = p.municipality" in sql
