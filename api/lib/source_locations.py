"""Recover document page locations from accepted, current source selections.

Locations are presentation metadata. They never change an accepted explanation's
source identity, and only attach when the retained wording and document match.
"""

from __future__ import annotations

from collections.abc import Iterable

from api.lib.english_presentation import (
    english_explanation,
    present_receipt,
    present_record,
)


def page_passages(spans: Iterable[dict], pages: list[dict]) -> list[dict]:
    """Split selected wording at known physical pages, preserving every character."""
    passages = []
    for span in spans:
        text = span.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        start, end = span.get("start"), span.get("end")
        if (
            type(start) is not int
            or type(end) is not int
            or start < 0
            or end - start != len(text)
        ):
            passages.append({"text": text, "page": None})
            continue

        cursor = start
        for page in pages:
            page_start, page_end = page.get("start"), page.get("end")
            if type(page_start) is not int or type(page_end) is not int:
                continue
            first, last = max(cursor, page_start), min(end, page_end)
            if first >= last:
                continue
            if cursor < first:
                passages.append(
                    {"text": text[cursor - start : first - start], "page": None}
                )
            page_number = page.get("page")
            passages.append(
                {
                    "text": text[first - start : last - start],
                    "page": page_number
                    if type(page_number) is int and page_number > 0
                    else None,
                }
            )
            cursor = last
        if cursor < end:
            passages.append({"text": text[cursor - start :], "page": None})
    return passages


def municipal_source_details(source: dict, record: dict) -> dict:
    """Locate an individual cited span or a complete card in its current document."""
    if not record.get("card"):
        return {}
    if (source.get("document_url") or source.get("url")) != record.get("document_url"):
        return {}
    text = source.get("excerpt", source.get("text"))
    if not isinstance(text, str) or not text.strip():
        return {}
    spans = record["card"]["passages"]
    selected = []
    if text == "\n[…]\n".join(span["text"] for span in spans):
        selected = spans
    else:
        # The explanation source id identifies a span even when wording repeats.
        source_id = source.get("explanation_source_id", source.get("id", ""))
        if (
            isinstance(source_id, str)
            and source_id.startswith("P")
            and source_id[1:].isdigit()
        ):
            index = int(source_id[1:]) - 1
            if 0 <= index < len(spans) and spans[index]["text"] == text:
                selected = [spans[index]]
        if not selected:
            matches = [span for span in spans if span["text"] == text]
            if len(matches) == 1:
                selected = matches
    if not selected:
        return {}
    return {
        "body_name": record["body_name"],
        "document_kind": record["payload"].get("document_kind", "record"),
        "meeting_date": str(record["meeting_date"]),
        "passages": page_passages(selected, record["payload"].get("pages", [])),
    }


def locate_feed_sources(cur, rows: list[dict]) -> None:
    """Enrich a bounded feed page using the same governed, current evidence view."""
    event_keys = [
        row["event_key"]
        for row in rows
        if row.get("source_kind") == "municipal_evidence"
    ]
    if not event_keys:
        return
    proceeding_ids = sorted({int(key.split(":")[1]) for key in event_keys})
    cur.execute(
        """SELECT *
           FROM public.current_municipal_intelligence
           WHERE proceeding_id = ANY(%s::integer[])
             AND event_key = ANY(%s::text[])""",
        (proceeding_ids, event_keys),
    )
    records = {row["event_key"]: dict(row) for row in cur.fetchall()}
    for row in rows:
        if row.get("source_kind") != "municipal_evidence":
            continue
        record = records.get(row["event_key"], {})
        explanation = record.get("explanation")
        ready = english_explanation(explanation)
        originals = (record.get("explanation_source") or {}).get("sources", [])
        if ready:
            row["title"] = explanation["headline"]
            row["what_happened"] = explanation["summary"]
            row["what_happens_next"] = explanation["next_step"] or ""
        else:
            row["title"] = "Municipal record"
            row["what_happened"] = "An English account is being prepared."
            row["what_happens_next"] = ""
        for source in row.get("source_evidence") or []:
            if isinstance(source, dict):
                source["details"] = {
                    **(source.get("details") or {}),
                    **municipal_source_details(source, record),
                }
                original = next(
                    (
                        item
                        for item in originals
                        if item["id"] == source.get("explanation_source_id")
                        and item.get("text") == source.get("excerpt")
                    ),
                    {"id": None, "text": source.get("excerpt")},
                )
                present_receipt(source, original, explanation)
                if not ready:
                    source["label"] = "Municipal record"
                    for key in (
                        "record_dates",
                        "decision_scope",
                        "explanation_next_step",
                    ):
                        source["details"].pop(key, None)
                elif "record_dates" in source["details"]:
                    displayed = present_record(
                        explanation["record"], originals, explanation
                    )
                    source["details"]["record_dates"] = displayed["dates"]
