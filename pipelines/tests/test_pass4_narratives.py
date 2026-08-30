"""Tests for Pass 4 county narratives.

Tests cover only pure-Python parts (templates, prompt builders, output parser).
No actual LLM calls are made and no database is required.
"""

import pytest

from countyiq.lib.pass4_county_narratives import (
    CORRIDOR_SCAN_QUERY,
    CORRIDOR_SYSTEM_PROMPT,
    CORRIDOR_USER_TEMPLATE,
    DISTRESS_SYSTEM_PROMPT,
    DISTRESS_USER_TEMPLATE,
    MUNICIPAL_SYSTEM_PROMPT,
    MUNICIPAL_USER_TEMPLATE,
    PORTFOLIO_SYSTEM_PROMPT,
    PORTFOLIO_USER_TEMPLATE,
    VALID_NARRATIVE_TYPES,
    VALID_TRAJECTORIES,
    build_corridor_prompt,
    build_portfolio_prompt,
    build_municipal_prompt,
    build_distress_prompt,
    parse_narrative_output,
)

CORRIDOR_PROMPT_TEXT = CORRIDOR_SYSTEM_PROMPT + "\n\n" + CORRIDOR_USER_TEMPLATE
PORTFOLIO_PROMPT_TEXT = PORTFOLIO_SYSTEM_PROMPT + "\n\n" + PORTFOLIO_USER_TEMPLATE
MUNICIPAL_PROMPT_TEXT = MUNICIPAL_SYSTEM_PROMPT + "\n\n" + MUNICIPAL_USER_TEMPLATE
DISTRESS_PROMPT_TEXT = DISTRESS_SYSTEM_PROMPT + "\n\n" + DISTRESS_USER_TEMPLATE


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_cluster():
    """A corridor cluster with 3 parcels sharing a signal."""
    return {
        "signal_key": "active_subdivision",
        "cluster_size": 3,
        "cluster_pidns": ["6700100000001", "6700100000002", "6700100000003"],
        "parcels": [
            {
                "pidn": "6700100000001",
                "address": "100 OAK ST",
                "assessment": "emerging",
                "brief_excerpt": "Active subdivision plan approved...",
            },
            {
                "pidn": "6700100000002",
                "address": "102 OAK ST",
                "assessment": "speculative",
                "brief_excerpt": "Adjacent to approved subdivision...",
            },
            {
                "pidn": "6700100000003",
                "address": "104 OAK ST",
                "assessment": "emerging",
                "brief_excerpt": "Zoning mismatch with future land use...",
            },
        ],
        "proceedings": [
            {
                "type": "subdivision",
                "applicant": "KEYSTONE DEV GROUP LLC",
                "decision": "approved",
                "meeting_date": "2025-07-15",
                "body": "Manchester Township Planning Commission",
            },
        ],
    }


@pytest.fixture
def sample_portfolio():
    """An entity portfolio with multiple parcels."""
    return {
        "entity_id": 42,
        "canonical_name": "KEYSTONE DEVELOPMENT GROUP LLC",
        "entity_type": "llc",
        "briefed_parcels": 5,
        "municipalities": ["Manchester Township", "York Township"],
        "total_acres": 22.5,
        "pidns": [
            "6700100000001", "6700100000002", "6700100000003",
            "6700100000004", "6700100000005",
        ],
        "briefs": [
            {
                "pidn": "6700100000001",
                "address": "100 OAK ST",
                "assessment": "emerging",
                "brief_excerpt": "Active subdivision plan...",
            },
            {
                "pidn": "6700100000004",
                "address": "200 ELM AVE",
                "assessment": "strong_opportunity",
                "brief_excerpt": "Rezoning approved for mixed use...",
            },
        ],
        "deeds": [
            {
                "pidn": "6700100000005",
                "grantor": "SMITH JOHN",
                "grantee": "KEYSTONE DEVELOPMENT GROUP LLC",
                "date": "2025-06-01",
                "price": 150000,
            },
        ],
    }


@pytest.fixture
def sample_municipal_data():
    """Municipal trend data for a single municipality."""
    return {
        "municipality": "Manchester Township",
        "assessment_distribution": {
            "strong_opportunity": 3,
            "emerging": 12,
            "speculative": 8,
            "constrained": 5,
            "not_actionable": 20,
        },
        "signal_distribution": {
            "active_subdivision": 5,
            "zoning_mismatch": 8,
            "flood_zone": 3,
            "vacancy": 12,
        },
        "zhb_decisions": {
            "approved": 15,
            "denied": 3,
            "tabled": 2,
        },
        "distress_summary": {
            "delinquent_parcels": 45,
            "total_owed": 285000,
            "sheriff_sale_count": 3,
        },
    }


@pytest.fixture
def sample_distress_data():
    """Distress migration data comparing current vs 90-day-prior."""
    return {
        "municipality": "York City",
        "school_dis": "York City School District",
        "current_count": 120,
        "prior_count": 108,
        "current_total_owed": 1250000,
        "prior_total_owed": 1100000,
        "count_delta": 12,
        "total_delta": 150000,
    }


@pytest.fixture
def valid_narrative_output():
    """A well-formed narrative LLM output."""
    return {
        "title": "Oak Street Corridor: Coordinated Subdivision Activity",
        "narrative": (
            "Three adjacent parcels along Oak Street in Manchester Township "
            "share active subdivision signals. The cluster appears to be "
            "driven by Keystone Development Group LLC..."
        ),
        "narrative_type": "corridor",
        "trajectory": "accelerating",
        "affected_pidns": ["6700100000001", "6700100000002", "6700100000003"],
        "key_entities": ["KEYSTONE DEVELOPMENT GROUP LLC"],
        "citations": ["active_subdivision", "zoning_mismatch"],
    }


# ---------------------------------------------------------------------------
# TestCorridorTemplate
# ---------------------------------------------------------------------------

class TestCorridorTemplate:
    """Tests for the corridor system/user prompt and builder."""

    def test_corridor_query_uses_dbscan_clusters(self):
        assert "ST_ClusterDBSCAN" in CORRIDOR_SCAN_QUERY
        assert "cluster_id" in CORRIDOR_SCAN_QUERY

    def test_has_cluster_section(self):
        assert "CLUSTER" in CORRIDOR_PROMPT_TEXT

    def test_has_parcels_section(self):
        assert "PARCELS" in CORRIDOR_PROMPT_TEXT

    def test_has_proceedings_section(self):
        assert "PROCEEDINGS" in CORRIDOR_PROMPT_TEXT

    def test_has_tasks_section(self):
        assert "TASKS" in CORRIDOR_PROMPT_TEXT

    def test_has_output_format(self):
        assert "OUTPUT FORMAT" in CORRIDOR_PROMPT_TEXT
        assert "title" in CORRIDOR_PROMPT_TEXT
        assert "narrative" in CORRIDOR_PROMPT_TEXT
        assert "corridor" in CORRIDOR_PROMPT_TEXT

    def test_build_corridor_prompt_returns_string(self, sample_cluster):
        result = build_corridor_prompt(sample_cluster)
        assert isinstance(result, str)
        assert len(result) > 100

    def test_build_corridor_prompt_includes_cluster_data(self, sample_cluster):
        result = build_corridor_prompt(sample_cluster)
        assert "active_subdivision" in result
        assert "3" in result  # cluster_size
        assert "6700100000001" in result

    def test_build_corridor_prompt_includes_parcels(self, sample_cluster):
        result = build_corridor_prompt(sample_cluster)
        assert "100 OAK ST" in result
        assert "102 OAK ST" in result
        assert "104 OAK ST" in result

    def test_build_corridor_prompt_includes_proceedings(self, sample_cluster):
        result = build_corridor_prompt(sample_cluster)
        assert "KEYSTONE DEV GROUP LLC" in result
        assert "approved" in result


# ---------------------------------------------------------------------------
# TestPortfolioTemplate
# ---------------------------------------------------------------------------

class TestPortfolioTemplate:
    """Tests for the portfolio system/user prompt and builder."""

    def test_has_entity_section(self):
        assert "ENTITY" in PORTFOLIO_PROMPT_TEXT

    def test_has_briefs_section(self):
        assert "BRIEFS" in PORTFOLIO_PROMPT_TEXT or "PARCEL" in PORTFOLIO_PROMPT_TEXT

    def test_has_deed_section(self):
        assert "DEED" in PORTFOLIO_PROMPT_TEXT

    def test_has_tasks_section(self):
        assert "TASKS" in PORTFOLIO_PROMPT_TEXT

    def test_has_output_format(self):
        assert "OUTPUT FORMAT" in PORTFOLIO_PROMPT_TEXT
        assert "title" in PORTFOLIO_PROMPT_TEXT
        assert "narrative" in PORTFOLIO_PROMPT_TEXT
        assert "owner_portfolio" in PORTFOLIO_PROMPT_TEXT

    def test_build_portfolio_prompt_returns_string(self, sample_portfolio):
        result = build_portfolio_prompt(sample_portfolio)
        assert isinstance(result, str)
        assert len(result) > 100

    def test_build_portfolio_prompt_includes_entity_data(self, sample_portfolio):
        result = build_portfolio_prompt(sample_portfolio)
        assert "KEYSTONE DEVELOPMENT GROUP LLC" in result
        assert "llc" in result
        assert "5" in result  # briefed_parcels

    def test_build_portfolio_prompt_includes_parcels(self, sample_portfolio):
        result = build_portfolio_prompt(sample_portfolio)
        assert "100 OAK ST" in result
        assert "200 ELM AVE" in result

    def test_build_portfolio_prompt_includes_deeds(self, sample_portfolio):
        result = build_portfolio_prompt(sample_portfolio)
        assert "SMITH JOHN" in result
        assert "150,000" in result or "150000" in result


# ---------------------------------------------------------------------------
# TestMunicipalTemplate
# ---------------------------------------------------------------------------

class TestMunicipalTemplate:
    """Tests for the municipal system/user prompt and builder."""

    def test_has_municipality_section(self):
        upper = MUNICIPAL_PROMPT_TEXT.upper()
        assert "MUNICIPALITY" in upper or "MUNICIPAL" in upper

    def test_has_assessment_section(self):
        assert "assessment" in MUNICIPAL_PROMPT_TEXT.lower()

    def test_has_signal_section(self):
        assert "signal" in MUNICIPAL_PROMPT_TEXT.lower()

    def test_has_tasks_section(self):
        assert "TASKS" in MUNICIPAL_PROMPT_TEXT

    def test_has_output_format(self):
        assert "OUTPUT FORMAT" in MUNICIPAL_PROMPT_TEXT
        assert "title" in MUNICIPAL_PROMPT_TEXT
        assert "narrative" in MUNICIPAL_PROMPT_TEXT
        assert "municipality" in MUNICIPAL_PROMPT_TEXT

    def test_build_municipal_prompt_returns_string(self, sample_municipal_data):
        result = build_municipal_prompt(sample_municipal_data)
        assert isinstance(result, str)
        assert len(result) > 100

    def test_build_municipal_prompt_includes_municipality(self, sample_municipal_data):
        result = build_municipal_prompt(sample_municipal_data)
        assert "Manchester Township" in result

    def test_build_municipal_prompt_includes_assessments(self, sample_municipal_data):
        result = build_municipal_prompt(sample_municipal_data)
        assert "strong_opportunity" in result or "3" in result

    def test_build_municipal_prompt_includes_distress(self, sample_municipal_data):
        result = build_municipal_prompt(sample_municipal_data)
        assert "45" in result or "285,000" in result or "285000" in result


# ---------------------------------------------------------------------------
# TestDistressTemplate
# ---------------------------------------------------------------------------

class TestDistressTemplate:
    """Tests for the distress system/user prompt and builder."""

    def test_has_distress_section(self):
        upper = DISTRESS_PROMPT_TEXT.upper()
        assert "DISTRESS" in upper

    def test_has_change_section(self):
        lower = DISTRESS_PROMPT_TEXT.lower()
        assert "change" in lower or "delta" in lower or "migration" in lower

    def test_has_tasks_section(self):
        assert "TASKS" in DISTRESS_PROMPT_TEXT

    def test_has_output_format(self):
        assert "OUTPUT FORMAT" in DISTRESS_PROMPT_TEXT
        assert "title" in DISTRESS_PROMPT_TEXT
        assert "narrative" in DISTRESS_PROMPT_TEXT
        assert "market_segment" in DISTRESS_PROMPT_TEXT

    def test_build_distress_prompt_returns_string(self, sample_distress_data):
        result = build_distress_prompt(sample_distress_data)
        assert isinstance(result, str)
        assert len(result) > 100

    def test_build_distress_prompt_includes_municipality(self, sample_distress_data):
        result = build_distress_prompt(sample_distress_data)
        assert "York City" in result

    def test_build_distress_prompt_includes_change_data(self, sample_distress_data):
        result = build_distress_prompt(sample_distress_data)
        assert "120" in result or "108" in result
        assert "12" in result  # count_delta


# ---------------------------------------------------------------------------
# TestParseNarrativeOutput
# ---------------------------------------------------------------------------

class TestParseNarrativeOutput:
    """Tests for parse_narrative_output(output) -> dict."""

    def test_valid_output_parsed(self, valid_narrative_output):
        result = parse_narrative_output(valid_narrative_output)
        assert result["title"] == valid_narrative_output["title"]
        assert result["narrative"] == valid_narrative_output["narrative"]
        assert result["narrative_type"] == "corridor"
        assert result["trajectory"] == "accelerating"
        assert len(result["affected_pidns"]) == 3
        assert "error" not in result

    def test_missing_title_returns_error(self):
        output = {
            "narrative": "Some narrative text.",
            "narrative_type": "corridor",
            "trajectory": "stable",
        }
        result = parse_narrative_output(output)
        assert "error" in result

    def test_missing_narrative_returns_error(self):
        output = {
            "title": "Some title",
            "narrative_type": "corridor",
            "trajectory": "stable",
        }
        result = parse_narrative_output(output)
        assert "error" in result

    def test_empty_title_returns_error(self):
        output = {
            "title": "",
            "narrative": "Some narrative text.",
            "narrative_type": "corridor",
            "trajectory": "stable",
        }
        result = parse_narrative_output(output)
        assert "error" in result

    def test_empty_narrative_returns_error(self):
        output = {
            "title": "Some title",
            "narrative": "",
            "narrative_type": "corridor",
            "trajectory": "stable",
        }
        result = parse_narrative_output(output)
        assert "error" in result

    def test_invalid_narrative_type_defaults_to_corridor(self):
        output = {
            "title": "Test Title",
            "narrative": "Test narrative.",
            "narrative_type": "bogus_type",
            "trajectory": "stable",
        }
        result = parse_narrative_output(output)
        assert result["narrative_type"] == "corridor"

    def test_missing_narrative_type_defaults_to_corridor(self):
        output = {
            "title": "Test Title",
            "narrative": "Test narrative.",
            "trajectory": "stable",
        }
        result = parse_narrative_output(output)
        assert result["narrative_type"] == "corridor"

    def test_invalid_trajectory_defaults_to_stable(self):
        output = {
            "title": "Test Title",
            "narrative": "Test narrative.",
            "narrative_type": "corridor",
            "trajectory": "super_fast",
        }
        result = parse_narrative_output(output)
        assert result["trajectory"] == "stable"

    def test_missing_trajectory_defaults_to_stable(self):
        output = {
            "title": "Test Title",
            "narrative": "Test narrative.",
            "narrative_type": "corridor",
        }
        result = parse_narrative_output(output)
        assert result["trajectory"] == "stable"

    def test_all_valid_narrative_types_accepted(self):
        for ntype in VALID_NARRATIVE_TYPES:
            output = {
                "title": "Test Title",
                "narrative": "Test narrative.",
                "narrative_type": ntype,
                "trajectory": "stable",
            }
            result = parse_narrative_output(output)
            assert result["narrative_type"] == ntype

    def test_all_valid_trajectories_accepted(self):
        for trajectory in VALID_TRAJECTORIES:
            output = {
                "title": "Test Title",
                "narrative": "Test narrative.",
                "narrative_type": "corridor",
                "trajectory": trajectory,
            }
            result = parse_narrative_output(output)
            assert result["trajectory"] == trajectory

    def test_non_dict_returns_error(self):
        result = parse_narrative_output("not a dict")
        assert "error" in result

    def test_affected_pidns_default_to_empty_list(self):
        output = {
            "title": "Test Title",
            "narrative": "Test narrative.",
            "narrative_type": "corridor",
            "trajectory": "stable",
        }
        result = parse_narrative_output(output)
        assert result["affected_pidns"] == []

    def test_key_entities_default_to_empty_list(self):
        output = {
            "title": "Test Title",
            "narrative": "Test narrative.",
            "narrative_type": "corridor",
            "trajectory": "stable",
        }
        result = parse_narrative_output(output)
        assert result["key_entities"] == []

    def test_citations_default_to_empty_list(self):
        output = {
            "title": "Test Title",
            "narrative": "Test narrative.",
            "narrative_type": "corridor",
            "trajectory": "stable",
        }
        result = parse_narrative_output(output)
        assert result["citations"] == []
