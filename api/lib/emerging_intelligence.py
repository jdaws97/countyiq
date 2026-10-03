"""Present reviewed interpretations using the shared customer evidence viewer."""

import re
from hashlib import sha256
from urllib.parse import urlencode

from api.lib.english_presentation import present_receipt
from api.lib.evidence import evidence_item
from api.lib.source_explanations import _record_query
from api.lib.source_locations import municipal_source_details

MARKER = re.compile(r"\[Evidence:source:([A-Za-z0-9_-]+)\]")


def present_case(row: dict, records: dict | None = None) -> dict:
    packet = row["packet"]
    hypothesis = row["hypothesis"]
    case_key = row["case_key"]
    used = set(MARKER.findall(str(hypothesis)))
    for claim in hypothesis["supporting_facts"] + hypothesis["contrary_evidence"]:
        used.add(claim["source_id"])
    for possibility in hypothesis["opportunities"]:
        for claim in (possibility.get("commercial_basis") or {}).values():
            used.add(claim["source_id"])
    sources = [source for source in packet["sources"] if source["id"] in used]
    receipts = []
    presentation = {"presentation_language": "en", **row["analysis"]}
    for source in sources:
        receipt = evidence_item(
            scope=case_key,
            citation_key=f"evidence:source:{source['id']}",
            label=source["label"],
            source_kind="municipal_evidence" if "text" in source else "public_record",
            source_record_id=source["record_key"],
            url=source.get("url"),
            document_url=source.get("url") if "text" in source else None,
            excerpt=source.get("text"),
            details={
                **source.get("facts", {}),
                "body_name": source.get("body_name"),
                "meeting_date": source.get("meeting_date"),
            },
            effective_at=source.get("meeting_date"),
            observed_at=source.get("available_at"),
            method="Source evidence for a reviewed hypothesis",
            record_query=_record_query({**source, "id": source["original_id"]}),
        )
        if records and source["record_key"] in records:
            receipt["details"].update(
                municipal_source_details(source, records[source["record_key"]])
            )
        present_receipt(receipt, source, presentation)
        receipts.append(receipt)
    dates = [item["meeting_date"] for item in sources if item.get("meeting_date")]
    return {
        **hypothesis,
        "case_key": case_key,
        "supporting_facts": [
            _claim_text(claim) for claim in hypothesis["supporting_facts"]
        ],
        "contrary_evidence": [
            _claim_text(claim) for claim in hypothesis["contrary_evidence"]
        ],
        "opportunities": [
            present_opportunity(case_key, item)
            for item in hypothesis["opportunities"]
            if qualifies_as_opportunity(item)
        ],
        "implications": [
            present_opportunity(case_key, item)
            for item in hypothesis["opportunities"]
            if not qualifies_as_opportunity(item)
        ],
        "project_types": hypothesis.get("project_types", []),
        "municipalities": packet["municipalities"],
        "properties": packet["properties"],
        "source_document_count": len(
            {item["document_identity"] for item in sources if "text" in item}
        ),
        "latest_record_date": max(dates) if dates else None,
        "assessed_at": row["created_at"].isoformat(),
        "as_of": packet["as_of"],
        "scope_note": packet["scope_note"],
        "change_summary": None,
        "revision": str(row["inference_id"]),
        "citation_evidence": receipts,
        "activity_links": [
            {
                "label": "Activity for this property",
                "path": "/feed?" + urlencode({"pidn": item["pidn"]}),
            }
            for item in packet["properties"]
            if item["relationship"] == "subject"
        ],
    }


def qualifies_as_opportunity(item: dict) -> bool:
    """Legacy research and unqualified drafts stay in the case, never the work queue."""
    basis = item.get("commercial_basis")
    return (
        item.get("readiness") in {"qualify", "act"}
        and isinstance(basis, dict)
        and all(
            isinstance(basis.get(key), dict)
            and basis[key].get("source_id")
            and basis[key].get("statement")
            for key in ("need", "timing", "qualification_route")
        )
    )


def present_opportunity(case_key: str, item: dict) -> dict:
    identity = item["audience"] + "|" + item["title"].casefold()
    return {
        **item,
        "opportunity_key": case_key + ":" + sha256(identity.encode()).hexdigest()[:16],
        "commercial_basis": {
            key: _claim_text(claim)
            for key, claim in (item.get("commercial_basis") or {}).items()
        }
        or None,
    }


def _claim_text(claim: dict) -> str:
    marker = f"[Evidence:source:{claim['source_id']}]"
    return (
        claim["statement"]
        if marker in claim["statement"]
        else claim["statement"] + " " + marker
    )


def present_cases(cur, rows: list[dict]) -> list[dict]:
    keys = sorted(
        {
            source["record_key"]
            for row in rows
            for source in row["packet"]["sources"]
            if "text" in source
        }
    )
    records = {}
    if keys:
        cur.execute(
            """
            SELECT event_key, document_url, body_name, meeting_date, card, payload
            FROM public.current_municipal_evidence evidence
            WHERE evidence.inference_id IN (
                SELECT indexed.inference_id FROM public.municipal_card_index indexed
                WHERE indexed.event_key=ANY(%s)
            ) AND evidence.event_key=ANY(%s)
            """,
            (keys, keys),
        )
        records = {row["event_key"]: dict(row) for row in cur.fetchall()}
    return [present_case(row, records) for row in rows]
