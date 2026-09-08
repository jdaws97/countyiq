"""Present case accounts using their current, individually located source spans."""

from api.lib.english_presentation import present_receipt, present_record
from api.lib.source_locations import page_passages


def locate_matter_sources(cur, rows: list[dict]) -> None:
    matter_rows = [row for row in rows if row.get("source_kind") == "municipal_matter"]
    inference_ids = {
        row["source_evidence"][0]["details"]["explanation_inference_id"]
        for row in matter_rows
    }
    if not inference_ids:
        return
    # The feed's live view already checked these exact inference versions against
    # current sources. Read their immutable presentation receipts by primary key;
    # rebuilding every county candidate bundle here repeated that expensive check.
    cur.execute(
        "SELECT inference_id, payload FROM meta.intelligence_inference_history WHERE inference_id = ANY(%s::bigint[])",
        (list(inference_ids),),
    )
    snapshots = {row["inference_id"]: row["payload"] for row in cur.fetchall()}
    for row in matter_rows:
        inference_id = row["source_evidence"][0]["details"]["explanation_inference_id"]
        snapshot = snapshots[inference_id]
        explanation = next(
            item["account"]
            for item in snapshot["matters"]
            if item["key"] == row["event_key"]
        )
        originals = {item["id"]: item for item in snapshot["source"]["sources"]}
        displayed = present_record(
            explanation["record"], list(originals.values()), explanation
        )
        for receipt in row.get("source_evidence") or []:
            original = originals.get(receipt.get("explanation_source_id"))
            if original is None:
                continue
            pages = receipt.get("details", {}).pop("_source_pages", [])
            receipt["details"] = {
                **(receipt.get("details") or {}),
                "body_name": original["body_name"],
                "meeting_date": original["meeting_date"],
                "document_kind": original["document_kind"],
                "passages": page_passages([original], pages),
            }
            if "record_dates" in receipt["details"]:
                receipt["details"]["record_dates"] = displayed["dates"]
            present_receipt(receipt, original, explanation)


def matter_payload(row: dict) -> dict | None:
    if row.get("source_kind") != "municipal_matter":
        return None
    sources = row.get("source_evidence") or []
    account = (
        (sources[0].get("details") or {}).get("matter_account") if sources else None
    )
    if not isinstance(account, dict):
        return None
    return {
        key: account[key]
        for key in (
            "request",
            "outcome",
            "outcome_summary",
            "readiness",
            "conditions",
            "history",
        )
    }
