"""Conservative chronology over accepted, source-backed proceeding extractions.

No additional inference: never treat missing updates as completed conditions,
never turn an agenda into a recorded decision, and never choose between same-day
conflicting decisions. Raw source wording and evidence identifiers survive.
"""

import re
from datetime import date, datetime

_DECISIONS = {
    "approved": "Approval recorded",
    "denied": "Denial recorded",
    "tabled": "Tabled",
    "continued": "Continued",
}

_MATTER_OUTCOMES = {
    "approved": "Approval recorded",
    "conditional": "Conditional approval recorded",
    "denied": "Denial recorded",
    "withdrawn": "Withdrawal recorded",
    "continued": "Continuance recorded",
    "mixed": "Multiple recorded outcomes — review their scope",
    "not_established": "Outcome not established by the supplied records",
}
_CITATION = re.compile(r"\[Evidence:source:([^\]]+)\]")


def exact_date(text):
    """Normalize ISO or spelled-out month/day/year; never infer a missing year."""
    if not isinstance(text, str):
        return None
    value = text.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError:
            return None
    if re.fullmatch(r"[A-Za-z]+ \d{1,2},? \d{4}", value):
        for fmt in ("%B %d %Y", "%b %d %Y"):
            try:
                return datetime.strptime(value.replace(",", ""), fmt).date().isoformat()
            except ValueError:
                pass
    return None


def summarize_project(events, *, incomplete=False, today=None):
    today = today or date.today()
    if len(events) == 1 and events[0].get("matter"):
        return _summarize_matter(events[0], incomplete=incomplete, today=today)
    # Compare normalized dates, not source spellings (e.g. "Jan 2 2026").
    events = [
        {**event, "event_date": exact_date(event.get("event_date"))} for event in events
    ]
    dated = [
        e for e in events if e["event_date"] and e["event_date"] <= today.isoformat()
    ]
    dated.sort(key=lambda e: (e["event_date"], e["event_key"]), reverse=True)
    decisions, conditions, milestones = [], [], []
    for event in events:
        for source in event.get("sources", []):
            details = source.get("details") or {}
            receipt = {
                "event_key": event["event_key"],
                "evidence_id": source["evidence_id"],
                "record_date": event.get("event_date"),
            }

            def supported_receipt(marker):
                selected = next(
                    (
                        s
                        for s in event.get("sources", [])
                        if marker in (s.get("details") or {}).get("supports", [])
                    ),
                    source,
                )
                return {**receipt, "evidence_id": selected["evidence_id"]}

            completed = event in dated and details.get("record_status") not in {
                "scheduled",
                "recommendation",
                "withdrawn",
                "removed",
            }
            if event in dated and completed and details.get("decision") in _DECISIONS:
                decisions.append(
                    {
                        **supported_receipt("decision"),
                        "decision": details["decision"],
                        "body": details.get("decision_authority")
                        or source.get("label"),
                        "matter": details.get("extraction_type"),
                        "scope": details.get("decision_scope"),
                    }
                )
            for index, condition in enumerate(details.get("conditions") or []):
                if isinstance(condition, str) and condition.strip():
                    conditions.append(
                        {
                            **supported_receipt(f"condition:{index}"),
                            "text": condition,
                            "status": "Satisfaction not established by this record"
                            if completed
                            else "Adoption not established by this record",
                        }
                    )
            for index, milestone in enumerate(details.get("milestones") or []):
                wording = milestone.get("text")
                if not isinstance(wording, str) or not wording.strip():
                    continue
                normalized = exact_date(milestone.get("date"))
                milestones.append(
                    {
                        **supported_receipt(f"milestone:{index}"),
                        "text": wording,
                        "kind": milestone.get("kind"),
                        "date": normalized,
                        "status": "Date passed; outcome unverified"
                        if normalized and normalized < today.isoformat()
                        else "Stated date"
                        if normalized
                        else "Exact date needs verification",
                    }
                )
            wording = details.get("upcoming_date")
            if isinstance(wording, str) and wording.strip():
                normalized = exact_date(details.get("upcoming_date_iso")) or exact_date(
                    wording
                )
                milestones.append(
                    {
                        **receipt,
                        "text": wording,
                        "date": normalized,
                        "status": "Date passed; outcome unverified"
                        if normalized and normalized < today.isoformat()
                        else "Stated date"
                        if normalized
                        else "Exact date needs verification",
                    }
                )
    decisions.sort(key=lambda d: (d["record_date"], d["event_key"]), reverse=True)
    latest = dated[0] if dated else None
    latest_decisions = [
        d for d in decisions if latest and d["record_date"] == latest["event_date"]
    ]
    groups = {}
    for decision in latest_decisions:
        groups.setdefault(
            (
                decision.get("scope"),
                decision.get("body") if decision.get("scope") else None,
            ),
            set(),
        ).add(decision["decision"])
    conflicting = any(len(outcomes) > 1 for outcomes in groups.values())

    def decision_label(decision):
        scope = decision.get("scope")
        return (
            scope.replace("_", " ").capitalize() + ": " if scope else ""
        ) + _DECISIONS[decision["decision"]]

    status = (
        "Conflicting records — verify scope and authority"
        if conflicting
        else (
            "Multiple scoped decisions recorded — review each action"
            if len(groups) > 1
            else decision_label(latest_decisions[0])
            if latest_decisions
            else "Later activity recorded; verify decision status"
            if latest and decisions
            else "No decision established by the linked records"
        )
    )
    if latest and not conflicting:
        states = set()
        for event in dated:
            if event["event_date"] != latest["event_date"]:
                continue
            event_states = set()
            for source in event.get("sources", []):
                details = source.get("details") or {}
                if details.get("record_status"):
                    event_states.add(details["record_status"])
                elif details.get("decision") in _DECISIONS:
                    event_states.add("decision")
            states.update(event_states or {"activity"})
        # Event-key order cannot establish which same-day action happened last.
        if states & {"withdrawn", "removed"} and len(states) > 1:
            status = "Multiple actions recorded — verify scope and sequence"
        elif "withdrawn" in states:
            status = "Withdrawal recorded"
        elif "removed" in states:
            status = "Removed from agenda; later action unverified"
    # Keep scope visible: different boards/relief types are not interchangeable.
    return {
        "status": status,
        "as_of": latest.get("event_date") if latest else None,
        "latest_event_key": latest.get("event_key") if latest else None,
        "latest_change": latest.get("what_happened") if latest else None,
        "decisions": decisions,
        "conditions": conditions,
        "milestones": milestones,
        "history_incomplete": incomplete
        or any(not exact_date(e.get("event_date")) for e in events),
        "caveat": "Status describes linked records, not construction permission. Conditions remain unverified until a source explicitly resolves them; later silence does not satisfy them.",
    }


def _summarize_matter(event, *, incomplete, today):
    """Use the accepted complete account instead of legacy extraction fields."""
    account = event["matter"]
    sources = {
        source.get("citation_key", "").removeprefix("evidence:source:"): source
        for source in event.get("sources", [])
    }

    def receipt(text):
        supporting_records = []
        for source_id in _CITATION.findall(text or ""):
            source = sources.get(source_id)
            if source:
                supporting_records.append(
                    {
                        "event_key": event["event_key"],
                        "evidence_id": source["evidence_id"],
                        "record_date": exact_date(
                            (source.get("details") or {}).get("meeting_date")
                        ),
                    }
                )
        if not supporting_records:
            return None
        dates = {record["record_date"] for record in supporting_records}
        return {
            **supporting_records[0],
            # A multi-record account can describe a rejection, revised approval
            # and later monitoring. Citation order cannot date the whole outcome.
            "record_date": dates.pop() if len(dates) == 1 else None,
            "supporting_records": supporting_records,
        }

    outcome = account["outcome"]
    outcome_receipt = receipt(account.get("outcome_summary"))
    dated_outcome = outcome_receipt and all(
        record["record_date"] and record["record_date"] <= today.isoformat()
        for record in outcome_receipt["supporting_records"]
    )
    status = _MATTER_OUTCOMES[outcome]
    decisions = []
    if outcome != "not_established":
        if dated_outcome:
            decisions.append(
                {
                    **outcome_receipt,
                    "decision": outcome,
                    "body": None,
                    "matter": _CITATION.sub("", account["outcome_summary"]).strip(),
                    "scope": None,
                }
            )
        else:
            status = "Recorded outcome needs source-date verification"
    conditions = []
    for condition in account.get("conditions", []):
        source_receipt = receipt(condition)
        if source_receipt:
            conditions.append(
                {
                    **source_receipt,
                    "text": _CITATION.sub("", condition).strip(),
                    "status": "Satisfaction not established by this account",
                }
            )
    history_dates = [
        exact_date(entry.get("meeting_date")) for entry in account.get("history", [])
    ]
    past_dates = [
        value for value in history_dates if value and value <= today.isoformat()
    ]
    return {
        "status": status,
        "as_of": max(past_dates, default=None),
        "latest_event_key": event["event_key"],
        "latest_change": event.get("what_happened"),
        "decisions": decisions,
        "conditions": conditions,
        "milestones": [],
        "history_incomplete": incomplete or not history_dates or None in history_dates,
        "caveat": "Status describes the accepted account and its stated scope. Conditions remain unverified until a source explicitly resolves them.",
    }
