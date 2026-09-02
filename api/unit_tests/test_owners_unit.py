"""Database-independent tests for stable entity relationship links."""

from api.routes.owners import (
    _fetch_entity_verification_evidence,
    _fetch_owner_brief_evidence,
    _linked_relationships,
)


class _Cursor:
    def __init__(self, owners: list[dict]):
        self.owners = owners
        self.sql = ""
        self.params: dict[str, object] = {}

    def execute(self, sql: str, params: dict[str, object]) -> None:
        self.sql = sql
        self.params = params

    def fetchall(self) -> list[dict]:
        return self.owners


def test_relationship_alias_resolves_to_stable_entity_id():
    cursor = _Cursor(
        [
            {
                "owner_id": 11,
                "canonical_name": "Beta Development LLC",
                "aliases": ["Beta Dev"],
                "entity_type": "llc",
                "verification_status": "verified",
            }
        ]
    )

    relationships = _linked_relationships(
        cursor,
        [{"related_entity": "Beta Dev", "relationship_type": "manager"}],
    )

    assert cursor.params == {"names": ["beta dev"]}
    assert relationships == [
        {
            "related_entity": "Beta Dev",
            "relationship_type": "manager",
            "related_owner_id": 11,
            "related_canonical_name": "Beta Development LLC",
            "related_verification_status": "verified",
            "related_entity_type": "llc",
        }
    ]


def test_relationship_mapping_is_normalized_without_forced_resolution():
    cursor = _Cursor([])

    relationships = _linked_relationships(
        cursor,
        {"affiliate": ["Unresolved Holdings", "Related Partner"]},
        allow_people=True,
    )

    assert relationships == [
        {
            "related_entity": "Unresolved Holdings",
            "relationship_type": "affiliate",
        },
        {
            "related_entity": "Related Partner",
            "relationship_type": "affiliate",
        },
    ]


class _EvidenceCursor:
    def __init__(self, responses: list[list[dict]]):
        self.responses = responses
        self.queries: list[str] = []

    def execute(self, sql: str, params: dict[str, object]) -> None:
        self.queries.append(sql)

    def fetchall(self) -> list[dict]:
        return self.responses.pop(0)


def test_owner_brief_citations_resolve_to_signal_and_parcel_receipts():
    cursor = _EvidenceCursor(
        [
            [
                {
                    "pidn": "123",
                    "signal_key": "growth_area",
                    "claim": "Inside the growth area.",
                    "evidence_data": {"ga_type": "PGA"},
                    "source_url": "https://example.com/growth",
                    "internal_url": "/property/123",
                    "validation_status": "confirmed",
                    "adjusted_significance": "high",
                    "validation_reasoning": "Confirmed by source geometry.",
                    "validated_at": "2026-08-31T12:00:00Z",
                    "confidence": 0.94,
                }
            ],
            [
                {
                    "pidn": "123",
                    "propadr": "1 Main St",
                    "municipality": "Test Township",
                    "aprtotal": 200000,
                    "saledt": "01-JAN-2024",
                    "price": 210000,
                    "source_url": "https://example.com/parcels/123",
                    "valid_from": "2026-08-30T08:00:00Z",
                }
            ],
        ]
    )

    items = _fetch_owner_brief_evidence(
        cursor,
        {"citations": ["growth_area"], "parcel_citations": ["123"]},
        allow_people=True,
    )

    assert [item["citation_key"] for item in items] == [
        "signal:growth_area",
        "parcel:123",
    ]
    assert items[0]["url"] == "https://example.com/growth"
    assert items[1]["internal_url"] == "/property/123"


class _EntityEvidenceCursor:
    def __init__(self):
        self.queries: list[str] = []

    def execute(self, sql: str, params: dict[str, object]) -> None:
        self.queries.append(sql)

    def fetchone(self) -> dict:
        return {
            "linked_sources": {
                "parcels": ["123"],
                "corporate_entities": ["Alpha Holdings LLC"],
            },
            "verified_at": "2026-08-31T12:00:00Z",
        }

    def fetchall(self) -> list[dict]:
        return [
            {
                "pidn": "123",
                "propadr": "1 Main St",
                "municipality": "Test Township",
                "source_url": "https://example.com/parcels/123",
                "valid_from": "2026-08-30T08:00:00Z",
            }
        ]


def test_entity_evidence_omits_business_records_when_source_policy_disallows_use():
    cursor = _EntityEvidenceCursor()

    items = _fetch_entity_verification_evidence(
        cursor,
        "Alpha Holdings LLC",
        allow_corporate_evidence=False,
    )

    assert [item["citation_key"] for item in items] == ["evidence:parcels:123"]
    assert not any("staging.corporate_entities" in query for query in cursor.queries)
