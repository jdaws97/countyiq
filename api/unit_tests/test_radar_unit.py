"""Unit coverage for Development Radar source-policy dependencies."""

from api.routes import radar


def test_radar_requires_only_sources_that_feed_its_scores(monkeypatch):
    checked = []

    monkeypatch.setattr(
        radar,
        "require_source_use",
        lambda _cur, source_key, use, *, conceal: checked.append(
            (source_key, use, conceal)
        ),
    )

    radar._require_radar_sources(object())

    assert checked == [
        ("york_open_data", "derived_product", False),
        ("penndot_open_data", "derived_product", False),
        ("fema_nfhl", "derived_product", False),
        ("tax_claims", "derived_product", False),
    ]


def test_site_readiness_does_not_depend_on_conditional_tax_claims(monkeypatch):
    checked = []
    monkeypatch.setattr(
        radar,
        "require_source_use",
        lambda _cur, source_key, use, *, conceal: checked.append(
            (source_key, use, conceal)
        ),
    )

    radar._require_radar_sources(object(), include_tax_claims=False)

    assert checked == [
        ("york_open_data", "derived_product", False),
        ("penndot_open_data", "derived_product", False),
        ("fema_nfhl", "derived_product", False),
    ]
