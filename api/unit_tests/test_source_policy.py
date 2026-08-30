"""Unit coverage for response-layer source policy helpers."""

from api.lib.source_policy import is_public_organization


def test_public_organization_types_exclude_natural_people():
    assert is_public_organization("LLC") is True
    assert is_public_organization("corporation") is True
    assert is_public_organization("individual") is False
    assert is_public_organization(None) is False
