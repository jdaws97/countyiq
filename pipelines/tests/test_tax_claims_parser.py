from datetime import date
from pathlib import Path

from countyiq.lib.parsers.tax_claims import (
    tax_claim_id_to_pidn,
    parse_tax_claims_text,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# PIDN conversion
# ---------------------------------------------------------------------------

def test_pidn_standard():
    pidn, unit = tax_claim_id_to_pidn("01-001-01-0002.00-00000")
    assert pidn == "0100101000200"
    assert unit == "00000"


def test_pidn_condo_unit():
    pidn, unit = tax_claim_id_to_pidn("01-001-01-0023.00-C0001")
    assert pidn == "0100101002300"
    assert unit == "C0001"


def test_pidn_alpha_map():
    pidn, unit = tax_claim_id_to_pidn("20-000-NC-0073.A0-00000")
    assert pidn == "20000NC0073A0"
    assert unit == "00000"


def test_pidn_mobile_home():
    pidn, unit = tax_claim_id_to_pidn("27-000-RE-0021.00-M0018")
    assert pidn == "27000RE002100"
    assert unit == "M0018"


def test_pidn_invalid():
    pidn, unit = tax_claim_id_to_pidn("INVALID")
    assert pidn == ""
    assert unit == ""


# ---------------------------------------------------------------------------
# Text parser
# ---------------------------------------------------------------------------

def _fixture_text():
    return (FIXTURES_DIR / "tax_claims_sample.txt").read_text()


def test_parse_extracts_report_date():
    records = parse_tax_claims_text(_fixture_text())
    assert len(records) > 0
    dates = {r["report_date"] for r in records}
    assert len(dates) == 1
    assert dates.pop() == date(2026, 3, 27)


def test_parse_extracts_district():
    records = parse_tax_claims_text(_fixture_text())
    district_01 = [r for r in records if r["tax_district_code"] == "01"]
    assert len(district_01) > 0
    assert district_01[0]["tax_district_name"] == "YORK CITY 1ST WARD"


def test_parse_standard_property():
    records = parse_tax_claims_text(_fixture_text())
    hits = [r for r in records if r["parcel_id_raw"] == "01-001-01-0006.00-00000"]
    assert len(hits) == 3  # COUNTY, SCHOOL, MUNICIPAL
    county = next(r for r in hits if r["authority_name"] == "COUNTY")
    assert county["pidn"] == "0100101000600"
    assert county["tax_year"] == 2025
    assert county["tax_owed"] == 0.0
    assert county["fees_owed"] == 55.0


def test_parse_multi_year_property():
    records = parse_tax_claims_text(_fixture_text())
    hits = [r for r in records if r["parcel_id_raw"] == "01-001-01-0021.00-00000"]
    assert len(hits) == 6  # 2 years x 3 authorities
    years = sorted({r["tax_year"] for r in hits})
    assert years == [2024, 2025]


def test_parse_condo_unit():
    records = parse_tax_claims_text(_fixture_text())
    hits = [r for r in records if r["parcel_id_raw"] == "01-001-01-0023.00-C0001"]
    assert len(hits) > 0
    assert hits[0]["unit_suffix"] == "C0001"
    assert hits[0]["pidn"] == "0100101002300"


def test_parse_negative_payments():
    records = parse_tax_claims_text(_fixture_text())
    hits = [r for r in records if r["parcel_id_raw"] == "01-001-01-0002.00-00000"
            and r["authority_name"] == "COUNTY"]
    assert len(hits) >= 1
    assert hits[0]["fees_paid"] == -55.0


def test_parse_owner_and_address():
    records = parse_tax_claims_text(_fixture_text())
    hits = [r for r in records if r["parcel_id_raw"] == "01-001-01-0006.00-00000"]
    assert hits[0]["owner_name"] == "BRATIC DUSAN & KATHLEEN M"
    assert hits[0]["property_address"] == "21 -25 S GEORGE ST"


def test_parse_alpha_map_code():
    records = parse_tax_claims_text(_fixture_text())
    hits = [r for r in records if r["parcel_id_raw"] == "20-000-NC-0073.A0-00000"]
    assert len(hits) > 0
    assert hits[0]["pidn"] == "20000NC0073A0"
    assert hits[0]["tax_district_code"] == "20"


def test_parse_skips_totals():
    records = parse_tax_claims_text(_fixture_text())
    for r in records:
        assert "TOTAL" not in r["authority_name"]


def test_parse_record_count():
    records = parse_tax_claims_text(_fixture_text())
    # Fixture has 2 pages with 19 parcel IDs, each with 3+ auth rows
    assert len(records) > 20
