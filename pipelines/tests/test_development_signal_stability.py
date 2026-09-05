"""Regression coverage for stable deterministic signal evidence."""

from countyiq.assets.enrichment.development_signals import _SIGNALS


def test_signal_evidence_does_not_include_rebuild_timestamp():
    sql = "\n".join(query for _key, query in _SIGNALS)

    assert "evidence_captured_at" not in sql


def test_municipal_action_links_alphanumeric_pidns_through_shared_normalizer():
    """41% of York PIDNs carry letters; a digit-only strip can never link them."""
    sql = dict(_SIGNALS)["municipal_action"]

    assert "public.proceeding_parcel_matches(" in sql
    assert "'[^0-9]'" not in sql


def test_municipal_action_address_match_is_scoped_to_municipality():
    sql = dict(_SIGNALS)["municipal_action"]
    assert "public.proceeding_parcel_matches(" in sql
    assert "pp.body_name) matched" in sql
