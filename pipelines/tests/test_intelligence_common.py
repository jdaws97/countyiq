"""Tests for the shared intelligence context module.

Covers formatter functions and hash computation. No database required.
"""

import datetime
import hashlib
import json


from countyiq.lib.intelligence_common import (
    PROCEEDINGS_FOR_PARCEL_QUERY,
    compute_input_hash,
    format_corporate_context,
    format_entity_context,
    format_neighbors_context,
    format_parcel_context,
    format_portfolio_context,
    format_proceedings_context,
    format_tax_claims_context,
)


def test_parcel_proceeding_address_match_is_normalized_and_municipality_scoped():
    # The shared SQL function is behavior-tested against synthetic parcels.
    sql = PROCEEDINGS_FOR_PARCEL_QUERY
    assert "public.proceeding_parcel_matches(" in sql
    assert "pp.body_name) matched" in sql


# ---------------------------------------------------------------------------
# format_parcel_context
# ---------------------------------------------------------------------------


class TestFormatParcelContext:
    """Tests for format_parcel_context(row: dict) -> dict."""

    def _full_row(self, **overrides) -> dict:
        """Return a staging.parcels-shaped dict with sensible defaults."""
        row = {
            "pidn": "67012345678901",
            "owner_full": "SMITH JOHN A",
            "propadr": "123 MAIN ST",
            "aprtotal": 250000.0,
            "acres": 1.5,
            "class": "R",
            "saledt": "01-JAN-2023",
            "price": 275000.0,
            "prev_owner": "JONES MARY B",
            "municipality": "Spring Garden Township",
            "school_dis": "YOSD",
            "source_url": "https://example.com/parcel/67012345678901",
        }
        row.update(overrides)
        return row

    def test_returns_expected_keys(self):
        result = format_parcel_context(self._full_row())
        expected_keys = {
            "pidn",
            "owner",
            "address",
            "assessed_value",
            "acres",
            "property_class",
            "sale_date",
            "sale_price",
            "previous_owner",
            "municipality",
            "school_district",
            "source_url",
        }
        assert set(result.keys()) == expected_keys

    def test_maps_fields_correctly(self):
        result = format_parcel_context(self._full_row())
        assert result["pidn"] == "67012345678901"
        assert result["owner"] == "SMITH JOHN A"
        assert result["address"] == "123 MAIN ST"
        assert result["assessed_value"] == 250000.0
        assert result["acres"] == 1.5
        assert result["property_class"] == "R"
        assert result["sale_date"] == "01-JAN-2023"
        assert result["sale_price"] == 275000.0
        assert result["previous_owner"] == "JONES MARY B"
        assert result["municipality"] == "Spring Garden Township"
        assert result["school_district"] == "YOSD"
        assert result["source_url"] == "https://example.com/parcel/67012345678901"

    def test_none_string_fields_become_empty_string(self):
        result = format_parcel_context(
            self._full_row(
                owner_full=None,
                propadr=None,
                prev_owner=None,
                municipality=None,
                school_dis=None,
                saledt=None,
                source_url=None,
            )
        )
        assert result["owner"] == ""
        assert result["address"] == ""
        assert result["previous_owner"] == ""
        assert result["municipality"] == ""
        assert result["school_district"] == ""
        assert result["sale_date"] == ""
        assert result["source_url"] == ""

    def test_none_numeric_fields_become_zero(self):
        result = format_parcel_context(
            self._full_row(
                aprtotal=None,
                acres=None,
                price=None,
            )
        )
        assert result["assessed_value"] == 0
        assert result["acres"] == 0
        assert result["sale_price"] == 0

    def test_missing_source_url_key(self):
        """Row without source_url key should not raise."""
        row = self._full_row()
        row.pop("source_url", None)
        result = format_parcel_context(row)
        assert result["source_url"] == ""


# ---------------------------------------------------------------------------
# format_tax_claims_context
# ---------------------------------------------------------------------------


class TestFormatTaxClaimsContext:
    """Tests for format_tax_claims_context(rows: list[dict]) -> list[dict]."""

    def _row(self, **overrides) -> dict:
        row = {
            "tax_year": 2022,
            "authority_name": "YORK COUNTY",
            "total": 1234.56,
            "owner_name": "SMITH JOHN A",
        }
        row.update(overrides)
        return row

    def test_empty_list(self):
        assert format_tax_claims_context([]) == []

    def test_returns_list_of_dicts(self):
        result = format_tax_claims_context([self._row()])
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], dict)

    def test_expected_keys(self):
        result = format_tax_claims_context([self._row()])
        assert set(result[0].keys()) == {"year", "authority", "amount", "owner"}

    def test_maps_fields_correctly(self):
        result = format_tax_claims_context([self._row()])
        assert result[0]["year"] == 2022
        assert result[0]["authority"] == "YORK COUNTY"
        assert result[0]["amount"] == 1234.56
        assert result[0]["owner"] == "SMITH JOHN A"

    def test_multiple_rows_preserved(self):
        rows = [self._row(tax_year=2021), self._row(tax_year=2022)]
        result = format_tax_claims_context(rows)
        assert len(result) == 2
        years = {r["year"] for r in result}
        assert years == {2021, 2022}

    def test_none_total_becomes_zero(self):
        result = format_tax_claims_context([self._row(total=None)])
        assert result[0]["amount"] == 0

    def test_none_owner_becomes_empty_string(self):
        result = format_tax_claims_context([self._row(owner_name=None)])
        assert result[0]["owner"] == ""


# ---------------------------------------------------------------------------
# format_entity_context
# ---------------------------------------------------------------------------


class TestFormatEntityContext:
    """Tests for format_entity_context(row: dict | None) -> dict."""

    def _row(self, **overrides) -> dict:
        row = {
            "entity_id": 42,
            "canonical_name": "SMITH JOHN A LLC",
            "entity_type": "LLC",
            "linked_names": ["SMITH J LLC", "JOHN SMITH LLC"],
            "relationships": {"parcels": ["67000000000001"]},
            "verification_status": "verified",
        }
        row.update(overrides)
        return row

    def test_none_input_returns_not_found(self):
        result = format_entity_context(None)
        assert result == {"found": False}

    def test_found_true_when_row_provided(self):
        result = format_entity_context(self._row())
        assert result["found"] is True

    def test_expected_keys_when_found(self):
        result = format_entity_context(self._row())
        expected_keys = {
            "found",
            "entity_id",
            "canonical_name",
            "entity_type",
            "linked_names",
            "relationships",
            "verification_status",
        }
        assert set(result.keys()) == expected_keys

    def test_maps_fields_correctly(self):
        result = format_entity_context(self._row())
        assert result["entity_id"] == 42
        assert result["canonical_name"] == "SMITH JOHN A LLC"
        assert result["entity_type"] == "LLC"
        assert result["linked_names"] == ["SMITH J LLC", "JOHN SMITH LLC"]
        assert result["relationships"] == {"parcels": ["67000000000001"]}
        assert result["verification_status"] == "verified"

    def test_none_linked_names_becomes_empty_list(self):
        result = format_entity_context(self._row(linked_names=None))
        assert result["linked_names"] == []

    def test_none_relationships_becomes_empty_dict(self):
        result = format_entity_context(self._row(relationships=None))
        assert result["relationships"] == {}

    def test_none_entity_type_becomes_empty_string(self):
        result = format_entity_context(self._row(entity_type=None))
        assert result["entity_type"] == ""

    def test_none_verification_status_becomes_empty_string(self):
        result = format_entity_context(self._row(verification_status=None))
        assert result["verification_status"] == ""


# ---------------------------------------------------------------------------
# format_portfolio_context
# ---------------------------------------------------------------------------


class TestFormatPortfolioContext:
    """Tests for format_portfolio_context(rows: list[dict]) -> list[dict]."""

    def _row(self, **overrides) -> dict:
        row = {
            "pidn": "67000000000001",
            "propadr": "456 ELM ST",
            "aprtotal": 180000.0,
            "saledt": "15-MAR-2021",
            "price": 195000.0,
        }
        row.update(overrides)
        return row

    def test_empty_list(self):
        assert format_portfolio_context([]) == []

    def test_expected_keys(self):
        result = format_portfolio_context([self._row()])
        assert set(result[0].keys()) == {
            "pidn",
            "address",
            "assessed_value",
            "sale_date",
            "sale_price",
        }

    def test_maps_fields_correctly(self):
        result = format_portfolio_context([self._row()])
        assert result[0]["pidn"] == "67000000000001"
        assert result[0]["address"] == "456 ELM ST"
        assert result[0]["assessed_value"] == 180000.0
        assert result[0]["sale_date"] == "15-MAR-2021"
        assert result[0]["sale_price"] == 195000.0

    def test_none_values_handled(self):
        result = format_portfolio_context(
            [self._row(propadr=None, aprtotal=None, saledt=None, price=None)]
        )
        assert result[0]["address"] == ""
        assert result[0]["assessed_value"] == 0
        assert result[0]["sale_date"] == ""
        assert result[0]["sale_price"] == 0


# ---------------------------------------------------------------------------
# format_proceedings_context
# ---------------------------------------------------------------------------


class TestFormatProceedingsContext:
    """Tests for format_proceedings_context(rows: list[dict]) -> list[dict]."""

    def _row(self, **overrides) -> dict:
        row = {
            "extraction_type": "variance_request",
            "applicant_name": "Jane Doe",
            "parcel_reference": "67000000000001",
            "decision": "approved",
            "meeting_date": datetime.date(2024, 6, 15),
            "body_name": "York City Zoning Board",
            "source_url": "https://example.com/proceeding/1",
            "supporting_text": "The variance was approved subject to conditions.",
        }
        row.update(overrides)
        return row

    def test_empty_list(self):
        assert format_proceedings_context([]) == []

    def test_expected_keys(self):
        result = format_proceedings_context([self._row()])
        assert set(result[0].keys()) == {
            "type",
            "applicant",
            "parcel",
            "decision",
            "meeting_date",
            "body",
            "source_url",
            "supporting_text",
            "proceeding_id",
            "extraction_id",
            "active_inference_id",
        }

    def test_maps_fields_correctly(self):
        result = format_proceedings_context([self._row()])
        assert result[0]["type"] == "variance_request"
        assert result[0]["applicant"] == "Jane Doe"
        assert result[0]["parcel"] == "67000000000001"
        assert result[0]["decision"] == "approved"
        assert result[0]["meeting_date"] == "2024-06-15"
        assert result[0]["body"] == "York City Zoning Board"
        assert result[0]["source_url"] == "https://example.com/proceeding/1"
        assert (
            result[0]["supporting_text"]
            == "The variance was approved subject to conditions."
        )

    def test_none_meeting_date_becomes_empty_string(self):
        result = format_proceedings_context([self._row(meeting_date=None)])
        assert result[0]["meeting_date"] == ""

    def test_string_meeting_date_passed_through(self):
        result = format_proceedings_context([self._row(meeting_date="2024-06-15")])
        assert result[0]["meeting_date"] == "2024-06-15"

    def test_none_string_fields_become_empty(self):
        result = format_proceedings_context(
            [
                self._row(
                    applicant_name=None,
                    parcel_reference=None,
                    decision=None,
                    body_name=None,
                    source_url=None,
                    supporting_text=None,
                )
            ]
        )
        assert result[0]["applicant"] == ""
        assert result[0]["parcel"] == ""
        assert result[0]["decision"] == ""
        assert result[0]["body"] == ""
        assert result[0]["source_url"] == ""
        assert result[0]["supporting_text"] == ""


# ---------------------------------------------------------------------------
# format_neighbors_context
# ---------------------------------------------------------------------------


class TestFormatNeighborsContext:
    """Tests for format_neighbors_context(rows: list[dict]) -> list[dict]."""

    def _row(self, **overrides) -> dict:
        row = {
            "pidn": "67000000000002",
            "owner_full": "JONES MARY B",
            "aprtotal": 320000.0,
            "acres": 2.3,
            "class": "R",
            "total_owed": 1800.00,
            "years_delinquent": 2,
        }
        row.update(overrides)
        return row

    def test_empty_list(self):
        assert format_neighbors_context([]) == []

    def test_expected_keys(self):
        result = format_neighbors_context([self._row()])
        assert set(result[0].keys()) == {
            "pidn",
            "owner",
            "assessed_value",
            "acres",
            "property_class",
            "total_owed",
            "years_delinquent",
        }

    def test_maps_fields_correctly(self):
        result = format_neighbors_context([self._row()])
        assert result[0]["pidn"] == "67000000000002"
        assert result[0]["owner"] == "JONES MARY B"
        assert result[0]["assessed_value"] == 320000.0
        assert result[0]["acres"] == 2.3
        assert result[0]["property_class"] == "R"
        assert result[0]["total_owed"] == 1800.00
        assert result[0]["years_delinquent"] == 2

    def test_none_values_handled(self):
        result = format_neighbors_context(
            [
                self._row(
                    owner_full=None,
                    aprtotal=None,
                    acres=None,
                    class_=None,
                    total_owed=None,
                    years_delinquent=None,
                )
            ]
        )
        assert result[0]["owner"] == ""
        assert result[0]["assessed_value"] == 0
        assert result[0]["acres"] == 0
        assert result[0]["total_owed"] == 0
        assert result[0]["years_delinquent"] == 0

    def test_null_class_column(self):
        """The 'class' column is a reserved keyword — test None handling."""
        row = self._row()
        row["class"] = None
        result = format_neighbors_context([row])
        assert result[0]["property_class"] == ""


# ---------------------------------------------------------------------------
# format_corporate_context
# ---------------------------------------------------------------------------


class TestFormatCorporateContext:
    """Tests for format_corporate_context(rows: list[dict]) -> list[dict]."""

    def _row(self, **overrides) -> dict:
        row = {
            "entity_name": "ACME PROPERTIES LLC",
            "entity_number": "4567890",
            "status": "ACTIVE",
            "formation_date": datetime.date(2015, 3, 22),
            "office_address": "100 Commerce Dr, York PA 17401",
            "source_url": "https://dos.pa.gov/entity/4567890",
        }
        row.update(overrides)
        return row

    def test_empty_list(self):
        assert format_corporate_context([]) == []

    def test_expected_keys(self):
        result = format_corporate_context([self._row()])
        assert set(result[0].keys()) == {
            "entity_name",
            "entity_number",
            "status",
            "formation_date",
            "office_address",
            "source_url",
        }

    def test_maps_fields_correctly(self):
        result = format_corporate_context([self._row()])
        assert result[0]["entity_name"] == "ACME PROPERTIES LLC"
        assert result[0]["entity_number"] == "4567890"
        assert result[0]["status"] == "ACTIVE"
        assert result[0]["formation_date"] == "2015-03-22"
        assert result[0]["office_address"] == "100 Commerce Dr, York PA 17401"
        assert result[0]["source_url"] == "https://dos.pa.gov/entity/4567890"

    def test_none_formation_date_becomes_empty_string(self):
        result = format_corporate_context([self._row(formation_date=None)])
        assert result[0]["formation_date"] == ""

    def test_none_string_fields_become_empty(self):
        result = format_corporate_context(
            [
                self._row(
                    entity_number=None,
                    status=None,
                    office_address=None,
                    source_url=None,
                )
            ]
        )
        assert result[0]["entity_number"] == ""
        assert result[0]["status"] == ""
        assert result[0]["office_address"] == ""
        assert result[0]["source_url"] == ""


# ---------------------------------------------------------------------------
# compute_input_hash
# ---------------------------------------------------------------------------


class TestComputeInputHash:
    """Tests for compute_input_hash(data: dict) -> str."""

    def test_returns_64_char_hex_string(self):
        result = compute_input_hash({"pidn": "67012345678901"})
        assert isinstance(result, str)
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_same_input_same_hash(self):
        data = {"pidn": "67012345678901", "owner": "SMITH JOHN A"}
        h1 = compute_input_hash(data)
        h2 = compute_input_hash(data)
        assert h1 == h2

    def test_different_input_different_hash(self):
        h1 = compute_input_hash({"pidn": "67000000000001"})
        h2 = compute_input_hash({"pidn": "67000000000002"})
        assert h1 != h2

    def test_key_order_does_not_matter(self):
        """Sorted keys ensures key order does not change the hash."""
        h1 = compute_input_hash({"a": 1, "b": 2})
        h2 = compute_input_hash({"b": 2, "a": 1})
        assert h1 == h2

    def test_empty_dict_is_valid(self):
        result = compute_input_hash({})
        assert len(result) == 64

    def test_nested_data_serialized(self):
        """Non-string values (dates, etc.) should not raise."""
        data = {
            "pidn": "67000000000001",
            "date": datetime.date(2024, 1, 1),
            "value": 123456,
        }
        result = compute_input_hash(data)
        assert len(result) == 64

    def test_matches_manual_sha256(self):
        """Hash must be reproducible via standard sha256(json)."""
        data = {"pidn": "67000000000001", "x": 42}
        expected = hashlib.sha256(
            json.dumps(data, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        assert compute_input_hash(data) == expected
