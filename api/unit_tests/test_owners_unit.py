"""Database-independent tests for stable entity relationship links."""

from api.routes.owners import _linked_relationships


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
