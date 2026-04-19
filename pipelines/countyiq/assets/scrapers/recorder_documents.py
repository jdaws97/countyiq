"""Recorder of Deeds metadata from York County Tyler portal -> staging recorder tables.

Strategy:
  - walk current parcels in PIDN order
  - derive recorder UPI from PIDN
  - search Tyler parcel search
  - fetch document detail pages for discovered documents
  - store metadata only (no PDFs/images)
"""

from datetime import datetime, timezone
import json

from dagster import (
    asset,
    asset_check,
    AssetCheckResult,
    AssetCheckSeverity,
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
)

from countyiq.lib.county_config import get_county_config
from countyiq.lib.parsers.tyler_recorder import pidn_to_recorder_upi
from countyiq.lib.scd import scd2_upsert
from countyiq.lib.tyler_recorder import TylerRecorderClient
from countyiq.resources.database import DatabaseResource
from countyiq.resources.storage import S3StorageResource


SOURCE_NAME = "recorder_documents"
DOCUMENT_KEY_COLUMNS = ["document_id"]
DOCUMENT_VALUE_COLUMNS = [
    "document_number",
    "document_type",
    "recording_at",
    "book",
    "page",
    "num_pages",
    "consideration",
    "grantors",
    "grantees",
    "legal_text",
    "source_url",
    "detail_fetched_at",
]
LINK_KEY_COLUMNS = ["pidn", "document_id"]
LINK_VALUE_COLUMNS = ["recorder_upi", "legal_text"]


@asset(
    group_name="scrapers",
    description=f"{get_county_config().name} recorder metadata from Tyler -> staging.recorded_documents",
    kinds={"postgres", "requests"},
)
def recorder_documents_scrape(
    context: AssetExecutionContext,
    database: DatabaseResource,
    s3: S3StorageResource,
) -> MaterializeResult:
    county = get_county_config()
    checkpoint = _load_checkpoint(database, SOURCE_NAME)

    if checkpoint.get("status") == "complete":
        return MaterializeResult(
            metadata={
                "status": MetadataValue.text("complete"),
                "current_documents": MetadataValue.int(_get_current_document_count(database)),
                "current_parcel_links": MetadataValue.int(_get_current_link_count(database)),
            }
        )

    parcels = _load_parcel_batch(
        database,
        after_pidn=checkpoint.get("last_completed_pidn"),
        limit=county.recorder_max_parcels_per_run,
    )
    if not parcels:
        checkpoint["status"] = "complete"
        _save_checkpoint(database, SOURCE_NAME, checkpoint)
        return MaterializeResult(
            metadata={
                "status": MetadataValue.text("complete"),
                "current_documents": MetadataValue.int(_get_current_document_count(database)),
                "current_parcel_links": MetadataValue.int(_get_current_link_count(database)),
            }
        )

    documents_by_id: dict[str, dict] = {}
    parcel_links_by_key: dict[tuple[str, str], dict] = {}
    processed_parcels = 0
    discovered_documents = 0

    with TylerRecorderClient(
        base_url=county.recorder_base_url,
        parcel_search_id=county.recorder_parcel_search_id,
        document_search_id=county.recorder_document_search_id,
        throttle_seconds=county.recorder_throttle_seconds,
        session_refresh=county.recorder_session_refresh,
    ) as client:
        for pidn in parcels:
            recorder_upi = pidn_to_recorder_upi(pidn)
            if not recorder_upi:
                context.log.warning("Skipping PIDN with no recorder UPI conversion: %s", pidn)
                continue

            context.log.info("Recorder lookup for PIDN %s (UPI %s)", pidn, recorder_upi)
            search_records = client.search_parcel_documents(recorder_upi)
            processed_parcels += 1
            discovered_documents += len(search_records)

            for search_record in search_records:
                document_id = search_record.get("document_id")
                if not document_id:
                    continue

                document = documents_by_id.setdefault("{}".format(document_id), {"document_id": document_id})
                _merge_document_record(document, search_record, county.recorder_base_url)

                if not document.get("detail_fetched_at"):
                    detail = client.fetch_document_detail(document_id)
                    detail["detail_fetched_at"] = datetime.now(timezone.utc)
                    _merge_document_record(document, detail, county.recorder_base_url)

                linked_pidns = set(document.get("legal_pidns") or [])
                linked_pidns.update(search_record.get("legal_pidns") or [])
                linked_pidns.add(pidn)

                legal_text = document.get("legal_text") or search_record.get("legal_text", "")
                for linked_pidn in linked_pidns:
                    if not linked_pidn:
                        continue
                    parcel_links_by_key[(linked_pidn, document_id)] = {
                        "pidn": linked_pidn,
                        "document_id": document_id,
                        "recorder_upi": recorder_upi,
                        "legal_text": legal_text,
                    }

    document_records = [_to_document_row(record) for record in documents_by_id.values()]
    link_records = list(parcel_links_by_key.values())

    document_stats = {"inserted": 0, "expired": 0}
    if document_records:
        cur = database.cursor()
        try:
            document_stats = scd2_upsert(
                cursor=cur,
                schema="staging",
                table="recorded_documents",
                records=document_records,
                key_columns=DOCUMENT_KEY_COLUMNS,
                value_columns=DOCUMENT_VALUE_COLUMNS,
                expire_missing=False,
            )
        finally:
            cur.close()

    link_stats = {"inserted": 0, "expired": 0}
    if link_records:
        cur = database.cursor()
        try:
            link_stats = scd2_upsert(
                cursor=cur,
                schema="staging",
                table="recorded_document_parcels",
                records=link_records,
                key_columns=LINK_KEY_COLUMNS,
                value_columns=LINK_VALUE_COLUMNS,
                expire_missing=False,
            )
        finally:
            cur.close()

    next_checkpoint = {
        "status": "in_progress",
        "last_completed_pidn": parcels[-1],
        "processed_parcels": checkpoint.get("processed_parcels", 0) + processed_parcels,
        "documents_seen": checkpoint.get("documents_seen", 0) + discovered_documents,
    }
    _save_checkpoint(database, SOURCE_NAME, next_checkpoint)

    s3.archive(
        f"{county.s3_prefix}/scrapers/recorder_documents",
        {
            "batch_start_pidn": parcels[0],
            "batch_end_pidn": parcels[-1],
            "processed_parcels": processed_parcels,
            "documents": document_records,
            "parcel_links": link_records,
        },
        filename=f"{parcels[0]}_{parcels[-1]}.json",
    )

    return MaterializeResult(
        metadata={
            "status": MetadataValue.text(next_checkpoint["status"]),
            "batch_start_pidn": MetadataValue.text(parcels[0]),
            "batch_end_pidn": MetadataValue.text(parcels[-1]),
            "processed_parcels": MetadataValue.int(processed_parcels),
            "documents_in_batch": MetadataValue.int(len(document_records)),
            "parcel_links_in_batch": MetadataValue.int(len(link_records)),
            "document_inserts": MetadataValue.int(document_stats.get("inserted", 0)),
            "link_inserts": MetadataValue.int(link_stats.get("inserted", 0)),
            "current_documents": MetadataValue.int(_get_current_document_count(database)),
            "current_parcel_links": MetadataValue.int(_get_current_link_count(database)),
        }
    )


def _merge_document_record(target: dict, incoming: dict, recorder_base_url: str) -> None:
    for key, value in incoming.items():
        if value in (None, "", []):
            continue
        if key == "source_url":
            value = _absolute_url(recorder_base_url, value)
        if key in {"grantors", "grantees", "legal_pidns"}:
            existing = target.get(key) or []
            merged = []
            seen = set()
            for item in list(existing) + list(value):
                if not item or item in seen:
                    continue
                seen.add(item)
                merged.append(item)
            target[key] = merged
            continue
        if key in {"document_type", "legal_text"}:
            existing = target.get(key)
            if isinstance(existing, str) and existing and isinstance(value, str) and len(existing) > len(value):
                continue
        target[key] = value


def _to_document_row(record: dict) -> dict:
    return {
        "document_id": record.get("document_id"),
        "document_number": record.get("document_number"),
        "document_type": record.get("document_type"),
        "recording_at": record.get("recording_at"),
        "book": record.get("book"),
        "page": record.get("page"),
        "num_pages": record.get("num_pages"),
        "consideration": record.get("consideration"),
        "grantors": record.get("grantors", []),
        "grantees": record.get("grantees", []),
        "legal_text": record.get("legal_text"),
        "source_url": record.get("source_url"),
        "detail_fetched_at": record.get("detail_fetched_at"),
    }


def _absolute_url(base_url: str, value: str) -> str:
    if not value:
        return ""
    if value.startswith("http://") or value.startswith("https://"):
        return value
    trimmed_base = base_url.rstrip("/")
    origin = trimmed_base[:-4] if trimmed_base.endswith("/web") else trimmed_base
    if value.startswith("/web/"):
        return f"{origin}{value}"
    if value.startswith("/"):
        return f"{trimmed_base}{value}"
    return f"{trimmed_base}/{value}"


def _load_parcel_batch(database: DatabaseResource, after_pidn: str | None, limit: int) -> list[str]:
    if after_pidn:
        rows = database.execute(
            """
            SELECT pidn
            FROM staging.parcels
            WHERE valid_to IS NULL AND pidn > %s
            ORDER BY pidn
            LIMIT %s
            """,
            (after_pidn, limit),
        )
    else:
        rows = database.execute(
            """
            SELECT pidn
            FROM staging.parcels
            WHERE valid_to IS NULL
            ORDER BY pidn
            LIMIT %s
            """,
            (limit,),
        )
    return [row[0] for row in rows if row and row[0]]


def _load_checkpoint(database: DatabaseResource, source_name: str) -> dict:
    rows = database.execute(
        "SELECT checkpoint FROM meta.scrape_checkpoints WHERE source_name = %s",
        (source_name,),
    )
    if rows:
        return rows[0][0] or {}
    return {}


def _save_checkpoint(database: DatabaseResource, source_name: str, data: dict) -> None:
    cur = database.cursor()
    try:
        cur.execute(
            """
            INSERT INTO meta.scrape_checkpoints (source_name, checkpoint, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (source_name) DO UPDATE
            SET checkpoint = EXCLUDED.checkpoint, updated_at = NOW()
            """,
            (source_name, json.dumps(data, default=str)),
        )
        cur.connection.commit()
    finally:
        cur.close()


def _get_current_document_count(database: DatabaseResource) -> int:
    rows = database.execute(
        "SELECT COUNT(*) FROM staging.recorded_documents WHERE valid_to IS NULL"
    )
    return rows[0][0] if rows else 0


def _get_current_link_count(database: DatabaseResource) -> int:
    rows = database.execute(
        "SELECT COUNT(*) FROM staging.recorded_document_parcels WHERE valid_to IS NULL"
    )
    return rows[0][0] if rows else 0


@asset_check(asset=recorder_documents_scrape)
def recorder_documents_record_count(database: DatabaseResource) -> AssetCheckResult:
    count = _get_current_document_count(database)
    return AssetCheckResult(
        passed=count > 0,
        severity=AssetCheckSeverity.ERROR,
        metadata={"current_documents": MetadataValue.int(count)},
    )


@asset_check(asset=recorder_documents_scrape)
def recorder_document_links_record_count(database: DatabaseResource) -> AssetCheckResult:
    count = _get_current_link_count(database)
    return AssetCheckResult(
        passed=count > 0,
        severity=AssetCheckSeverity.ERROR,
        metadata={"current_links": MetadataValue.int(count)},
    )
