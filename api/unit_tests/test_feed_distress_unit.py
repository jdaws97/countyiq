"""Public-versus-restricted delinquency feed copy."""

from api.routes import feed


def _delinquency_row() -> dict:
    return {
        "source_kind": "delinquency_event",
        "what_happened": "Affected claims increased from $1,000.00 to $1,500.00.",
        "why_it_matters": "Old copy",
        "what_happens_next": "Old next step",
        "source_evidence": [
            {
                "label": "County tax-claim listing",
                "url": "https://example.test/claims.pdf",
                "document_url": "https://example.test/claims.pdf",
                "excerpt": "$1,500.00",
                "details": {
                    "change_kind": "increased",
                    "old_affected_total": 1000,
                    "new_affected_total": 1500,
                    "affected_claims": 2,
                    "tax_years": [2024, 2025],
                },
            }
        ],
    }


def test_public_delinquency_copy_hides_exact_debt_details():
    row = _delinquency_row()
    public = feed._display_event_copy(row, allow_restricted_distress=False)

    assert "$" not in public["what_happened"]
    assert "balance" not in public["what_happened"].lower()
    assert public["source_evidence"][0]["details"] == {"change_kind": "increased"}
    assert public["source_evidence"][0]["excerpt"] is None
    assert public["source_evidence"][0]["url"] == "https://example.test/claims.pdf"
    assert row["source_evidence"][0]["details"]["new_affected_total"] == 1500


def test_restricted_delinquency_copy_preserves_exact_debt_details():
    row = _delinquency_row()

    assert feed._display_event_copy(
        row,
        allow_restricted_distress=True,
    ) is row
