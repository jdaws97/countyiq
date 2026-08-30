"""Source authorization is a pre-fetch, fail-closed control."""

from datetime import date, datetime, timedelta, timezone

import pytest

from countyiq.lib.source_rights import (
    authorize_municipality_sources,
    authorize_source,
    authorize_source_use,
    require_source_use,
)


class _Database:
    def __init__(self, policy):
        self.policy = policy
        self.audit = []

    def execute(self, sql, params=None):
        if "FROM meta.source_rights" in sql:
            return [self.policy] if self.policy is not None else []
        if "INSERT INTO meta.source_rights_audit" in sql:
            self.audit.append(params)
            return None
        raise AssertionError(sql)


def _policy(*, status="green", acquisition=True, methods=None, due=None):
    return (
        status,
        acquisition,
        True,
        True,
        False,
        False,
        methods or ["arcgis_rest"],
        date.today(),
        due or date.today() + timedelta(days=30),
        {"basis": "unit test"},
        datetime.now(timezone.utc),
        "Test publisher",
        "https://example.gov/source",
        "https://example.gov/terms",
        "test policy",
        1,
    )


def test_authorized_source_records_receipt():
    database = _Database(_policy())

    authorization = authorize_source(
        database,
        source_key="york_open_data",
        acquisition_method="arcgis_rest",
        asset_key="zoning_overlays_arcgis",
        dagster_run_id="run-1",
    )

    assert authorization.derived_product_allowed is True
    assert database.audit[0][4:6] == (True, "authorized")
    assert database.audit[0][6] == 1
    assert len(database.audit[0][7]) == 64
    assert '"source_key":"york_open_data"' in database.audit[0][8]


def test_downstream_use_is_enforced_separately():
    database = _Database(_policy())
    authorization = authorize_source(
        database,
        source_key="york_open_data",
        acquisition_method="arcgis_rest",
        asset_key="zoning_overlays_arcgis",
    )

    require_source_use(authorization, "raw_retention")
    with pytest.raises(RuntimeError, match="blocks person level display"):
        require_source_use(authorization, "person_level_display")


@pytest.mark.parametrize(
    ("policy", "message"),
    [
        (_policy(status="paused"), "policy is paused"),
        (_policy(acquisition=False), "acquisition is disabled"),
        (_policy(methods=["official_pdf"]), "not allowlisted"),
        (_policy(due=date.today() - timedelta(days=1)), "review expired"),
    ],
)
def test_blocked_source_records_receipt(policy, message):
    database = _Database(policy)

    with pytest.raises(RuntimeError, match=message):
        authorize_source(
            database,
            source_key="source",
            acquisition_method="arcgis_rest",
            asset_key="asset",
        )

    assert database.audit[0][4] is False


def test_unknown_source_fails_closed_without_network_authority():
    database = _Database(None)

    with pytest.raises(RuntimeError, match="no meta.source_rights policy"):
        authorize_source(
            database,
            source_key="unknown",
            acquisition_method="arcgis_rest",
            asset_key="asset",
        )

    assert database.audit == []


class _UseDatabase:
    def __init__(self, policy):
        self.policy = policy
        self.audit = []

    def execute(self, sql, params=None):
        if "FROM meta.source_rights" in sql:
            return [self.policy] if self.policy is not None else []
        if "INSERT INTO meta.source_rights_audit" in sql:
            self.audit.append(params)
            return None
        raise AssertionError(sql)


def _use_policy(*, status="green", allowed=True, due=None):
    row = list(_policy(status=status, due=due))
    row[3] = allowed
    return tuple(row)


def test_downstream_asset_reauthorizes_current_source_use():
    database = _UseDatabase(_use_policy())

    authorize_source_use(
        database,
        source_key="york_open_data",
        use="derived_product",
        asset_key="development_signals",
        dagster_run_id="run-2",
    )

    assert database.audit[0][:6] == (
        "york_open_data",
        "development_signals",
        "run-2",
        "use:derived_product",
        True,
        "authorized",
    )


@pytest.mark.parametrize(
    ("policy", "message"),
    [
        (_use_policy(status="paused"), "policy is paused"),
        (_use_policy(allowed=False), "blocks derived product"),
        (_use_policy(due=date.today() - timedelta(days=1)), "review expired"),
    ],
)
def test_downstream_asset_fails_closed_and_records_receipt(policy, message):
    database = _UseDatabase(policy)

    with pytest.raises(RuntimeError, match=message):
        authorize_source_use(
            database,
            source_key="source",
            use="derived_product",
            asset_key="development_momentum",
        )

    assert database.audit[0][4] is False


class _MunicipalityDatabase:
    def __init__(self, rows):
        self.rows = rows
        self.audit = []

    def execute(self, sql, params=None):
        if "FROM meta.municipality_source_rights" in sql:
            requested = set(params[0])
            return [row for row in self.rows if row[0] in requested]
        if "INSERT INTO meta.municipality_source_audit" in sql:
            self.audit.append(params)
            return None
        raise AssertionError(sql)


def _municipality_policy(
    *,
    source_key="dover_twp_board_of_supervisors",
    body="Dover Twp Board of Supervisors",
    url="https://example.gov/minutes",
    proceeding_type="board_of_supervisors",
    status="conditional",
    due=None,
):
    return (
        source_key,
        body,
        url,
        proceeding_type,
        status,
        status != "paused",
        True,
        True,
        False,
        False,
        ["official_document_direct"],
        ["https://example.gov"],
        "not_found",
        due or date.today() + timedelta(days=30),
        date.today(),
        {"basis": "unit test"},
        datetime.now(timezone.utc),
        "test policy",
        1,
        "https://example.gov/terms",
    )


def test_municipality_policy_must_match_config_exactly():
    database = _MunicipalityDatabase([_municipality_policy()])

    authorizations = authorize_municipality_sources(
        database,
        entries=((
            "Dover Twp Board of Supervisors",
            "https://example.gov/minutes",
            "board_of_supervisors",
        ),),
        acquisition_method="official_document_direct",
        asset_key="public_proceedings_scrape",
    )

    assert "dover_twp_board_of_supervisors" in authorizations
    assert database.audit[0][4:6] == (True, "authorized")
    assert database.audit[0][6] == 1
    assert len(database.audit[0][7]) == 64


def test_changed_municipality_url_fails_closed_and_is_audited():
    database = _MunicipalityDatabase([_municipality_policy()])

    with pytest.raises(RuntimeError, match="does not match reviewed policy"):
        authorize_municipality_sources(
            database,
            entries=((
                "Dover Twp Board of Supervisors",
                "https://example.gov/new-minutes",
                "board_of_supervisors",
            ),),
            acquisition_method="official_document_direct",
            asset_key="public_proceedings_scrape",
        )

    assert database.audit[0][4] is False


def test_unknown_municipality_source_fails_closed():
    database = _MunicipalityDatabase([])

    with pytest.raises(RuntimeError, match="no reviewed policy"):
        authorize_municipality_sources(
            database,
            entries=((
                "New Borough Council",
                "https://example.gov/minutes",
                "borough_council",
            ),),
            acquisition_method="official_document_direct",
            asset_key="public_proceedings_scrape",
        )

    assert database.audit == []
