"""Unit tests for Tyler recorder parsing helpers."""

import os

from countyiq.lib.parsers.tyler_recorder import (
    extract_pidns_from_legal_text,
    parse_tyler_document_detail,
    parse_tyler_search_results,
    pidn_to_recorder_legal,
    pidn_to_recorder_upi,
)


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def test_pidn_to_recorder_upi():
    assert pidn_to_recorder_upi("0100101002400") == "010010100240000000"


def test_pidn_to_recorder_legal():
    assert pidn_to_recorder_legal("0100101002400") == "01-001-01-0024.00-00000"


def test_extract_pidns_from_legal_text():
    text = "YORK CITY Parcel # 01-001-01-0024.00-00000 and 46-000-01-0001.00-00000"
    assert extract_pidns_from_legal_text(text) == ["0100101002400", "4600001000100"]


def test_parse_tyler_search_results():
    with open(os.path.join(FIXTURES, "tyler_recorder_search_results.html")) as f:
        html = f.read()

    records = parse_tyler_search_results(html)
    assert len(records) == 2

    first = records[0]
    assert first["document_id"] == "DOCCLND2024028005"
    assert first["document_number"] == "2024028005"
    assert first["document_type"] == "EASEMENT"
    assert first["book"] == "2837"
    assert first["page"] == "4717"
    assert first["grantors"] == ["COUNTY OF YORK", "YORK COUNTY"]
    assert first["grantees"] == ["METROPOLITAN EDISON COMPANY"]
    assert first["legal_pidns"] == ["0100101002400"]


def test_parse_tyler_document_detail():
    with open(os.path.join(FIXTURES, "tyler_recorder_document_detail.html")) as f:
        html = f.read()

    record = parse_tyler_document_detail(html)
    assert record["document_type"] == "EASEMENT"
    assert record["document_number"] == "2024028005"
    assert record["book"] == "2837"
    assert record["page"] == "4717"
    assert record["num_pages"] == 3
    assert record["consideration"] == 0.0
    assert record["grantors"] == ["COUNTY OF YORK", "YORK COUNTY"]
    assert record["grantees"] == ["METROPOLITAN EDISON COMPANY"]
    assert record["legal_pidns"] == ["0100101002400"]
