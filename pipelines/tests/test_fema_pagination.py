"""FEMA pagination termination tests."""

from unittest.mock import Mock

from countyiq.assets.bulk import fema_flood


def test_empty_page_terminates_even_when_server_retains_transfer_flag(monkeypatch):
    fetch_page = Mock(
        side_effect=[
            {"features": [{"attributes": {"FLD_AR_ID": "one"}}],
             "exceededTransferLimit": True},
            {"features": [], "exceededTransferLimit": True},
        ]
    )
    monkeypatch.setattr(fema_flood, "_fetch_page", fetch_page)
    context = Mock()

    result = fema_flood._fetch_all_pages("https://example.test", 28, "42133C", context)

    assert len(result["features"]) == 1
    assert fetch_page.call_count == 2


def test_final_nonempty_page_terminates_when_transfer_flag_clears(monkeypatch):
    fetch_page = Mock(
        return_value={
            "features": [{"attributes": {"FLD_AR_ID": "one"}}],
            "exceededTransferLimit": False,
        }
    )
    monkeypatch.setattr(fema_flood, "_fetch_page", fetch_page)

    result = fema_flood._fetch_all_pages(
        "https://example.test", 28, "42133C", Mock()
    )

    assert len(result["features"]) == 1
    assert fetch_page.call_count == 1
