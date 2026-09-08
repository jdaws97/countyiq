"""Present current accepted record explanations with their original receipts."""

from api.lib.evidence import NFHL_FLOOD_HAZARD_LAYER, evidence_item, with_arcgis_layer
from api.lib.settings import open_data_source_key
from api.lib.source_locations import municipal_source_details


def _record_query(item: dict) -> tuple[str, list] | None:
    identifier = item["id"]
    facts = item.get("facts") or {}
    if identifier == "parcel" or identifier.startswith("adjacent_"):
        return "PIDN", [facts.get("pidn")]
    if identifier == "zoning":
        return "ZRECID", [facts.get("zrecid")]
    if identifier == "future_landuse":
        return "GlobalID", [facts.get("globalid")]
    if identifier.startswith("plan_"):
        return "SEQU_NUM", [facts.get("sequence_number")]
    if identifier == "soils":
        return "OBJECTID_1", [
            key
            for unit in facts.get("units", [])
            for key in unit.get("source_record_ids", [])
        ]
    if identifier == "flood":
        return "FLD_AR_ID", facts.get("source_record_ids", [])
    if identifier.startswith("easement_"):
        return "EASE_ID", [facts.get("ease_id")]
    if identifier.startswith("ag_security_"):
        return "RESOLUTION", [facts.get("resolution")]
    return None


def explanation_payload(
    row: dict, municipal_records: list[dict] | None = None
) -> dict | None:
    explanation = row.get("explanation")
    source = row.get("explanation_source")
    if not explanation or not source:
        return None
    generated_at = row.get("explanation_generated_at")
    if hasattr(generated_at, "isoformat"):
        generated_at = generated_at.isoformat()
    receipts = [
        evidence_item(
            scope=f"explanation-{row['explanation_inference_id']}",
            citation_key=f"evidence:source:{item['id']}",
            label=item["label"],
            source_kind="municipal_evidence" if "text" in item else "public_record",
            source_record_id=item["id"],
            url=(
                with_arcgis_layer(item.get("url"), NFHL_FLOOD_HAZARD_LAYER)
                if item["id"] == "flood"
                else item.get("url")
            ),
            document_url=item.get("url") if "text" in item else None,
            excerpt=item.get("text"),
            details=item.get("facts"),
            effective_at=item.get("meeting_date", source.get("meeting_date")),
            method="Explanation of the cited public records",
            record_query=_record_query(item),
        )
        for item in source["sources"]
    ]
    records = municipal_records or (
        [row] if row.get("card") and row.get("payload") else []
    )
    context_pidn = (
        source["subject_key"].removeprefix("parcel:")
        if source.get("kind") == "property"
        else None
    )
    for item, receipt in zip(source["sources"], receipts, strict=True):
        matches = [
            details
            for record in records
            if (details := municipal_source_details(item, record))
        ]
        if len(matches) == 1:
            receipt["details"].update(matches[0])
        if context_pidn:
            related_pidn = (item.get("facts") or {}).get("pidn") or context_pidn
            receipt["internal_url"] = f"/property/{related_pidn}"
    return {
        "headline": explanation["headline"],
        "summary": explanation["summary"],
        "next_step": explanation["next_step"],
        "record": explanation["record"],
        "citation_evidence": receipts,
        "generated_at": generated_at,
        "model": row.get("explanation_model"),
    }


def fetch_property_explanation(cur, pidn: str) -> dict | None:
    # Recompute only for a property with an accepted explanation. Comparing the
    # full bundle retracts prose when source facts, links or rights change.
    cur.execute(
        """
        SELECT history.inference_id AS explanation_inference_id,
            history.payload->'source' AS explanation_source,
            history.payload->'explanation' AS explanation,
            history.created_at AS explanation_generated_at,
            history.requested_model AS explanation_model
        FROM (
            SELECT * FROM meta.intelligence_inference_history
            WHERE subject_key = 'parcel:' || %(pidn)s
              AND output_kind = 'record_explanation' AND disposition = 'accepted'
            ORDER BY inference_id DESC LIMIT 1
        ) history
        WHERE history.payload->'source' = public.property_explanation_source(
            %(pidn)s, %(source_key)s,
            (history.payload->'source'->>'planning_radius_m')::integer,
            (history.payload->'source'->>'environmental_radius_m')::integer)
        """,
        {"pidn": pidn, "source_key": open_data_source_key()},
    )
    row = cur.fetchone()
    if not row:
        return None
    municipal_records = []
    if any("text" in item for item in row["explanation_source"]["sources"]):
        cur.execute(
            """SELECT document_url, body_name, meeting_date, card, payload
               FROM public.current_municipal_intelligence
               WHERE %(pidn)s = ANY(related_pidns)
               ORDER BY meeting_date DESC, proceeding_id DESC, card_position LIMIT 6""",
            {"pidn": pidn},
        )
        municipal_records = [dict(record) for record in cur.fetchall()]
    return explanation_payload(dict(row), municipal_records)
