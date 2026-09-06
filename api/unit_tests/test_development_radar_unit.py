"""Unit coverage for buyer-facing development signal labels."""

from api.lib.development_radar import format_signal_label, sanitize_signals_for_public


def test_ownership_change_omits_unknown_date_placeholder():
    signal = {"evidence": {"price": 210000, "buyer_is_llc": False}}

    assert (
        format_signal_label("ownership_change", signal) == "Recorded sale for $210,000"
    )


def test_signal_payload_keeps_owner_facts_and_reasoning():
    signals = {
        "ownership_change": {
            "weight": 0.1,
            "claim": "Jane Citizen sold the parcel",
            "validation_reasoning": "Jane Citizen appears in county records",
            "cross_references": [{"owner_name": "Jane Citizen"}],
            "evidence": {
                "price": 210000,
                "prev_owner": "Jane Citizen",
                "buyer_is_llc": True,
            },
        },
        "economic_development_park": {"evidence": {"park_names": ["Commerce Park"]}},
    }

    public = sanitize_signals_for_public(signals)

    # Owner identity is public record; nothing is redacted from non-tax signals.
    assert public["ownership_change"] == signals["ownership_change"]
    assert public["economic_development_park"]["evidence"]["park_names"] == [
        "Commerce Park"
    ]
