"""Unit tests for the parcel version-diff event classifier."""

from datetime import date

from countyiq.lib.parcel_events import TRACKED_FIELDS, classify_parcel_change


def _base(**overrides) -> dict:
    row = {
        "deed_bk": "2456",
        "deed_pg": "0812",
        "saledt": "15-MAR-2020",
        "price": "250000",
        "owner_full": "SMITH JOHN",
        "prev_owner": "DOE JANE",
        "mail_addr_full": "10 MAIN ST YORK PA 17401",
        "aprland": "40000",
        "aprbldg": "160000",
        "aprtotal": "200000",
        "yrblt": "1988",
        "res_living_area": "1800",
        "num_stories": "2",
        "comm_struc": None,
        "comm_year_built": None,
        "comm_building_sq_ft": None,
    }
    row.update(overrides)
    return row


def test_no_change_yields_no_events():
    assert classify_parcel_change(_base(), _base()) == []


def test_deed_and_owner_change_is_confirmed_transfer():
    old = _base()
    new = _base(
        deed_bk="2701",
        deed_pg="0033",
        saledt="02-JUN-2026",
        price="410000",
        owner_full="YORK HOLDINGS LLC",
        prev_owner="SMITH JOHN",
    )
    events = classify_parcel_change(old, new)
    transfers = [e for e in events if e["event_type"] == "transfer"]
    assert len(transfers) == 1
    t = transfers[0]
    assert t["confidence"] == "confirmed"
    assert t["event_date"] == date(2026, 6, 2)
    assert "deed_bk" in t["evidence"]["changed"]
    assert t["evidence"]["changed"]["owner_full"]["new"] == "YORK HOLDINGS LLC"


def test_lone_saledt_drift_is_likely_only():
    events = classify_parcel_change(_base(), _base(saledt="16-MAR-2020"))
    assert [e["event_type"] for e in events] == ["transfer"]
    assert events[0]["confidence"] == "likely"


def test_malformed_saledt_gives_no_event_date():
    events = classify_parcel_change(
        _base(), _base(deed_bk="9999", owner_full="NEW OWNER", saledt="03/15/2020")
    )
    assert events[0]["event_type"] == "transfer"
    assert events[0]["confidence"] == "confirmed"
    assert events[0]["event_date"] is None


def test_value_change_is_confirmed_fact():
    events = classify_parcel_change(_base(), _base(aprtotal="215000", aprbldg="175000"))
    assert [e["event_type"] for e in events] == ["value_change"]
    assert events[0]["confidence"] == "confirmed"
    assert events[0]["evidence"]["pattern"] == "renovation_like"


def test_renovation_pattern_requires_no_transfer():
    old = _base()
    new = _base(
        aprbldg="175000",
        aprtotal="215000",
        deed_bk="2701",
        owner_full="FLIP LLC",
    )
    events = classify_parcel_change(old, new)
    value = next(e for e in events if e["event_type"] == "value_change")
    assert value["evidence"]["pattern"] == "general"


def test_demolition_pattern():
    events = classify_parcel_change(
        _base(), _base(aprbldg="0", aprtotal="40000", res_living_area=None)
    )
    value = next(e for e in events if e["event_type"] == "value_change")
    assert value["evidence"]["pattern"] == "demolition_like"
    structure = next(e for e in events if e["event_type"] == "structure_change")
    assert structure["confidence"] == "likely"


def test_land_revaluation_is_general_pattern():
    events = classify_parcel_change(_base(), _base(aprland="55000", aprtotal="215000"))
    assert events[0]["evidence"]["pattern"] == "general"


def test_structure_change_alone():
    events = classify_parcel_change(
        _base(), _base(comm_struc="WH1", comm_building_sq_ft="52000")
    )
    assert [e["event_type"] for e in events] == ["structure_change"]
    assert set(events[0]["evidence"]["changed"]) == {
        "comm_struc",
        "comm_building_sq_ft",
    }


def test_whitespace_and_none_equivalence_is_not_a_change():
    assert classify_parcel_change(_base(comm_struc=""), _base(comm_struc=None)) == []
    assert classify_parcel_change(_base(price="250000 "), _base(price="250000")) == []


def test_tracked_fields_has_no_duplicates():
    assert len(TRACKED_FIELDS) == len(set(TRACKED_FIELDS))
