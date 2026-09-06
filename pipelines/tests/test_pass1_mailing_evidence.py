"""Pass 1 context must carry identity-corroborating mailing evidence."""

from countyiq.lib.pass1_entity_verification import (
    CLUSTER_RECORDS_QUERY_PARCELS,
    CONTEXT_FORMAT_VERSION,
    _format_parcel_records,
)


def test_pass1_parcel_context_includes_mailing_address():
    assert "mail_addr_full" in CLUSTER_RECORDS_QUERY_PARCELS
    text = _format_parcel_records(
        [
            {
                "pidn": "P1",
                "owner_full": "SMITH JOHN A",
                "propadr": "1 MAIN ST",
                "mail_addr_full": "99 OAK ST YORK PA 17401",
            }
        ]
    )
    assert "Mailing address: 99 OAK ST YORK PA 17401" in text
    assert CONTEXT_FORMAT_VERSION == "registry-lookup-provenance-v3"
