"""PA registered-business lookup via data.pa.gov SODA -> staging.corporate_entities.

Strategy:
  - Extract unique LLC/Corp/LP/etc. owner names from staging.parcels
  - Process a finite alphabetical batch; persisted outcomes resume the next run
  - Refresh found entities more often than negative-cache misses
  - Full-text ($q) search the statewide registered-business dataset
    (xvd7-5r2c, one row per officer/party) and match on a compacted name
  - Record found AND not-found outcomes (negative cache) via SCD2 upsert
  - Archive raw match results to R2

Replaced the Playwright scrape of file.dos.pa.gov on 2026-08-05 (scrape-free
source policy): the official dataset is API-accessible, statewide (so
out-of-county registrants that own York parcels still match), and carries
officer names. It has no operating-status field — records are labeled
`present_in_current_dos_dataset`, never "confirmed active".

Optional: set SODA_APP_TOKEN to raise data.pa.gov rate limits.
"""

import os
import re
import time
from datetime import datetime, timezone

import requests
from dagster import (
    AssetCheckSeverity,
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
    asset,
)

from countyiq.lib.checks import make_row_count_check
from countyiq.lib.county_config import get_county_config
from countyiq.lib.parsers.pa_dos_entities import (
    STATUS_NOT_FOUND,
    make_not_found_record,
    parse_soda_business_rows,
)
from countyiq.lib.scd import scd2_upsert
from countyiq.lib.source_rights import authorize_source, require_source_use
from countyiq.resources.database import DatabaseResource
from countyiq.resources.storage import S3StorageResource


SOURCE_NAME = "pa_dos_entities"

# SCD2 key / value column split
KEY_COLUMNS = ["entity_name"]
VALUE_COLUMNS = [
    "matched_name",
    "entity_number",
    "entity_type",
    "status",
    "formation_date",
    "registered_agent_name",
    "registered_agent_address",
    "office_address",
    "officers",
    "source_url",
]
# Refreshed in place on every lookup so an unchanged record still advances its
# TTL clock. Without it, unchanged rows kept their original valid_from, aged
# past the TTL, and the same alphabetical prefix was re-queried every run while
# newer owner names were never reached.
CARRY_COLUMNS = ["last_checked_at"]

# Cap on consecutive errors before aborting the run
_MAX_ERRORS = 25

# Progress log interval
_LOG_INTERVAL = 100

# Throttle between SODA queries (seconds)
_THROTTLE_SECONDS = 0.25

_REQUEST_TIMEOUT = 30
_MAX_RETRIES = 3
_RETRY_BACKOFF = 5  # seconds, multiplied by attempt number
_QUERY_LIMIT = 500  # candidate officer rows per name; patterns can be broad
_DEFAULT_MAX_NAMES_PER_RUN = 500
_DEFAULT_FOUND_TTL_DAYS = 30
_DEFAULT_NOT_FOUND_TTL_DAYS = 180


def _positive_int_env(name: str, default: int) -> int:
    """Read a positive integer without allowing an unbounded zero value."""
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


@asset(
    group_name="scrapers",
    description="PA DOS registered-business lookup for parcel owners -> staging.corporate_entities",
    kinds={"postgres", "api"},
)
def pa_dos_entities(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    county = get_county_config()
    authorization = authorize_source(
        database,
        source_key="data_pa_businesses",
        acquisition_method="soda_api",
        asset_key="pa_dos_entities",
        dagster_run_id=context.run_id,
    )
    require_source_use(authorization, "derived_product")
    require_source_use(authorization, "raw_retention")
    log = context.log

    # --- 1. Fetch one bounded batch of entity names that need lookup ---
    max_names = _positive_int_env(
        "COUNTYIQ_PA_DOS_MAX_NAMES_PER_RUN", _DEFAULT_MAX_NAMES_PER_RUN
    )
    found_ttl_days = _positive_int_env(
        "COUNTYIQ_PA_DOS_FOUND_TTL_DAYS", _DEFAULT_FOUND_TTL_DAYS
    )
    not_found_ttl_days = _positive_int_env(
        "COUNTYIQ_PA_DOS_NOT_FOUND_TTL_DAYS", _DEFAULT_NOT_FOUND_TTL_DAYS
    )
    name_checkpoint = _get_name_checkpoint(database)
    entity_names = _get_pending_entity_names(
        database,
        limit=max_names,
        found_ttl_days=found_ttl_days,
        not_found_ttl_days=not_found_ttl_days,
        after_name=name_checkpoint,
    )
    if not entity_names:
        log.info("No new business entity names to look up")
        return MaterializeResult(
            metadata={
                "status": MetadataValue.text("no_work"),
                "entities_queued": MetadataValue.int(0),
                "run_limit": MetadataValue.int(max_names),
                "found_ttl_days": MetadataValue.int(found_ttl_days),
                "not_found_ttl_days": MetadataValue.int(not_found_ttl_days),
                "current_records": MetadataValue.int(_get_current_count(database)),
            }
        )

    log.info(
        "Queued %d entity names (run cap=%d, found TTL=%dd, miss TTL=%dd)",
        len(entity_names),
        max_names,
        found_ttl_days,
        not_found_ttl_days,
    )

    dataset_url = f"{county.soda_base_url}/{county.pa_dos_soda_dataset}.json"
    session = requests.Session()
    app_token = os.environ.get("SODA_APP_TOKEN")
    if app_token:
        session.headers["X-App-Token"] = app_token

    # --- 2. SODA lookup loop ---
    records: list[dict] = []
    raw_archive: list[dict] = []
    processed = 0
    found = 0
    not_found = 0
    error_count = 0
    last_attempted_name: str | None = None

    for entity_name in entity_names:
        if error_count >= _MAX_ERRORS:
            log.error("Reached max error cap (%d) — stopping run", _MAX_ERRORS)
            break

        if processed > 0 and processed % _LOG_INTERVAL == 0:
            log.info(
                "Progress: %d/%d processed, %d found, %d not found, %d errors",
                processed,
                len(entity_names),
                found,
                not_found,
                error_count,
            )

        last_attempted_name = entity_name
        try:
            record = _lookup_entity(session, dataset_url, entity_name)
        except requests.exceptions.RequestException as err:
            log.warning("SODA query failed for '%s': %s", entity_name, err)
            error_count += 1
            processed += 1
            continue

        processed += 1
        if record is None:
            record = make_not_found_record(entity_name)
            not_found += 1
        else:
            found += 1
            raw_archive.append({"entity_name": entity_name, "result": record})

        record["source_url"] = (
            f"{dataset_url}?filing_number={record['entity_number']}"
            if record["entity_number"]
            else dataset_url
        )
        record["last_checked_at"] = datetime.now(timezone.utc)
        records.append(record)
        time.sleep(_THROTTLE_SECONDS)

    # --- 3. SCD2 upsert (found + negative-cache rows) ---
    upsert_stats = {"inserted": 0, "expired": 0, "unchanged": 0}
    if records:
        cur = database.cursor()
        try:
            upsert_stats = scd2_upsert(
                cursor=cur,
                schema="staging",
                table="corporate_entities",
                records=records,
                key_columns=KEY_COLUMNS,
                value_columns=VALUE_COLUMNS,
                expire_missing=False,
                carry_columns=CARRY_COLUMNS,
            )
        finally:
            cur.close()
    if last_attempted_name:
        _save_name_checkpoint(database, last_attempted_name)

    # --- 4. Archive raw match results to R2 ---
    if raw_archive:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
        s3.archive(
            f"{county.s3_prefix}/scrapers/pa_dos_entities",
            {"run_at": datetime.now(timezone.utc).isoformat(), "results": raw_archive},
            filename=f"{date_str}.json",
        )

    return MaterializeResult(
        metadata={
            "status": MetadataValue.text("complete"),
            "entities_queued": MetadataValue.int(len(entity_names)),
            "run_limit": MetadataValue.int(max_names),
            "found_ttl_days": MetadataValue.int(found_ttl_days),
            "not_found_ttl_days": MetadataValue.int(not_found_ttl_days),
            "entities_processed": MetadataValue.int(processed),
            "entities_found": MetadataValue.int(found),
            "entities_not_found": MetadataValue.int(not_found),
            "errors": MetadataValue.int(error_count),
            "scd2_inserted": MetadataValue.int(upsert_stats.get("inserted", 0)),
            "scd2_expired": MetadataValue.int(upsert_stats.get("expired", 0)),
            "current_records": MetadataValue.int(_get_current_count(database)),
        }
    )


# ---------------------------------------------------------------------------
# SODA query helpers
# ---------------------------------------------------------------------------

# Tokens that end the distinctive part of an owner name. Everything from the
# first suffix token on is dropped from the LIKE pattern — the DOS side may
# spell it out ("Limited Partnership" for the county's "LP"), so it can't be
# matched literally; parse_soda_business_rows normalizes suffixes when it
# compact-compares candidates.
_SUFFIX_TOKENS = {
    "LLC",
    "LLP",
    "LLLP",
    "LP",
    "INC",
    "CORP",
    "LTD",
    "CO",
    "LC",
    "PC",
    "LIMITED",
    "PARTNERSHIP",
    "COMPANY",
    "CORPORATION",
    "INCORPORATED",
}


def _core_tokens(entity_name: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9]+", entity_name.upper())
    core = []
    for token in tokens:
        if token in _SUFFIX_TOKENS:
            break
        core.append(token)
    return core or tokens[:1]


def _name_like_pattern(entity_name: str) -> str:
    """Build a LIKE pattern from an owner string's distinctive tokens.

    "S&A PROPERTIES CORP" → "S%A%PROPERTIES%" — the % between tokens absorbs
    punctuation/spacing drift ("S & a Properties Corp."), and false hits are
    rejected by the parser's compact-name comparison. ($q full-text was tried
    first and silently missed exact registered names — do not go back to it.)
    """
    return "%".join(_core_tokens(entity_name)) + "%"


def _loose_like_pattern(entity_name: str) -> str:
    """Fallback pattern tolerating punctuation INSIDE tokens.

    The county strips punctuation the DOS name keeps: "RUTTERS" vs
    "Rutter's", "DANGELO" vs "D'angelo". Tokens of 4+ chars get wildcards
    after the first and before the last character ("RUTTERS" → "R%UTTER%S"),
    which the compact-name comparison then disambiguates.
    """
    parts = []
    for token in _core_tokens(entity_name):
        if len(token) >= 4:
            parts.append(f"{token[0]}%{token[1:-1]}%{token[-1]}")
        else:
            parts.append(token)
    return "%".join(parts) + "%"


def _query_pattern(
    session: requests.Session, dataset_url: str, pattern: str, attempt: int = 1
) -> list[dict]:
    """Fetch candidate officer rows for one LIKE pattern, with 5xx retry."""
    try:
        resp = session.get(
            dataset_url,
            params={
                "$where": f"upper(business_name) like '{pattern}'",
                "$limit": _QUERY_LIMIT,
            },
            timeout=_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError as e:
        if (
            attempt < _MAX_RETRIES
            and e.response is not None
            and e.response.status_code >= 500
        ):
            time.sleep(_RETRY_BACKOFF * attempt)
            return _query_pattern(session, dataset_url, pattern, attempt + 1)
        raise


def _lookup_entity(
    session: requests.Session, dataset_url: str, entity_name: str
) -> dict | None:
    """Look one owner name up: strict pattern first, loose fallback on miss."""
    rows = _query_pattern(session, dataset_url, _name_like_pattern(entity_name))
    record = parse_soda_business_rows(rows, entity_name)
    if record is not None:
        return record

    loose = _loose_like_pattern(entity_name)
    if loose != _name_like_pattern(entity_name):
        rows = _query_pattern(session, dataset_url, loose)
        record = parse_soda_business_rows(rows, entity_name)
    return record


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def _get_pending_entity_names(
    database: DatabaseResource,
    *,
    limit: int,
    found_ttl_days: int,
    not_found_ttl_days: int,
    after_name: str | None = None,
) -> list[str]:
    """Return a resumable batch, wrapping after the last attempted name.

    Advancing on attempted names prevents a permanently failing alphabetical
    prefix from starving every later owner when the run-level error cap trips.
    """
    rows = database.execute(
        r"""
        WITH pending AS (
            SELECT DISTINCT p.owner_full
            FROM staging.parcels p
            WHERE p.valid_to IS NULL
              AND p.owner_full ~* %s
              AND NOT EXISTS (
                  SELECT 1
                  FROM staging.corporate_entities ce
                  WHERE ce.entity_name = p.owner_full
                    AND ce.valid_to IS NULL
                    AND COALESCE(ce.last_checked_at, ce.valid_from) > NOW() - (
                        CASE WHEN ce.status = %s THEN %s ELSE %s END
                    ) * INTERVAL '1 day'
              )
        )
        SELECT owner_full
        FROM pending
        ORDER BY
            CASE WHEN %s IS NULL OR owner_full > %s THEN 0 ELSE 1 END,
            owner_full
        LIMIT %s
        """,
        (
            r"(LLC|L\.L\.C|INC|CORP|LP|L\.P|LTD|TRUST|PARTNERS|ASSOCIATES|"
            r"HOLDINGS|ENTERPRISES|PROPERTIES|GROUP|VENTURES|CAPITAL|INVESTMENTS)",
            STATUS_NOT_FOUND,
            not_found_ttl_days,
            found_ttl_days,
            after_name,
            after_name,
            limit,
        ),
    )
    return [row[0] for row in rows if row and row[0]]


def _get_name_checkpoint(database: DatabaseResource) -> str | None:
    rows = database.execute(
        """
        SELECT checkpoint ->> 'last_entity_name'
        FROM meta.scrape_checkpoints
        WHERE source_name = %s
        """,
        (SOURCE_NAME,),
    )
    if not rows or not rows[0]:
        return None
    value = rows[0][0]
    return str(value) if value else None


def _save_name_checkpoint(database: DatabaseResource, entity_name: str) -> None:
    database.execute(
        """
        INSERT INTO meta.scrape_checkpoints (source_name, checkpoint, updated_at)
        VALUES (%s, jsonb_build_object('last_entity_name', %s), NOW())
        ON CONFLICT (source_name) DO UPDATE
        SET checkpoint = EXCLUDED.checkpoint,
            updated_at = EXCLUDED.updated_at
        """,
        (SOURCE_NAME, entity_name),
    )


def _get_current_count(database: DatabaseResource) -> int:
    rows = database.execute(
        "SELECT COUNT(*) FROM staging.corporate_entities WHERE valid_to IS NULL"
    )
    return rows[0][0] if rows else 0


# ---------------------------------------------------------------------------
# Asset check
# ---------------------------------------------------------------------------

pa_dos_entities_record_count = make_row_count_check(
    pa_dos_entities,
    table="corporate_entities",
    threshold_fn=lambda: get_county_config().pa_dos_min_records,
    severity=AssetCheckSeverity.WARN,
    metadata_key="current_records",
    name="pa_dos_entities_record_count",
)
