"""Address-like references cannot become shared named-project aliases."""
import pytest
from countyiq.lib.proceeding_contract import distinctive_project_reference, project_aliases


@pytest.mark.parametrize("name", ["123 Market Square Road", " 123 Market Square", "42 Willow Creek Drive"])
def test_address_is_not_a_distinctive_named_project(name):
    assert not distinctive_project_reference(name)
    assert project_aliases({"body_name":"York City Planning Commission",
                            "extraction_details":{"project_reference":name}}) == []


def test_named_development_still_supports_continuity():
    assert distinctive_project_reference("Willow Creek development")
    assert project_aliases({"body_name":"York City Planning Commission",
                            "extraction_details":{"project_reference":"Willow Creek development"}})
