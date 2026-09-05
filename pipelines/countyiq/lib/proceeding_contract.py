"""Versioned proceeding evidence, dates and application identity.

Display prose never supplies identity. Only exact source identifiers and explicit
case relationships do. Ambiguous records stay separate until reviewed.
"""
from __future__ import annotations
from datetime import date, datetime
import hashlib
import re
import unicodedata

CONTRACT_VERSION = 2
DETAIL_FIELDS = ("evidence_spans", "record_status", "event_date", "event_date_text",
                 "upcoming_date_iso", "application_ids", "project_reference",
                 "parcel_references", "matter_category")


def compact(value):
    return "".join(unicodedata.normalize("NFKC", str(value or "")).split())


def exact_date(value):
    """Read one explicit four-digit-year date; preserve uncertain wording outside it."""
    if not isinstance(value, str):
        return None
    text = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", value.strip(), flags=re.I)
    month = r"(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
    pattern = rf"(?<![\w/-])(?:\d{{4}}-\d{{2}}-\d{{2}}|\d{{1,2}}/\d{{1,2}}/\d{{4}}|\d{{1,2}}-\d{{1,2}}-\d{{4}}|{month}\.?\s+\d{{1,2}},?\s+\d{{4}})(?![\w/-])"
    found = list(re.finditer(pattern, text, re.I))
    # Do not pick an advertising date from a multi-date bidding schedule.
    if len(found) != 1:
        return None
    match = found[0]
    # A docket identifier that happens to resemble a date is not a dated event.
    if re.search(r"\b(?:case|docket|application|plan)\s*(?:(?:no\.?|number|#)\s*)?$",
                 text[:match.start()], re.I):
        return None
    outside = text[:match.start()] + " " + text[match.end():]
    if re.search(rf"{month}\.?\s+\d{{1,2}}\b|\b\d{{1,2}}[/-]\d{{1,2}}(?:[/-]\d{{2,4}})?\b",
                 outside, re.I):
        return None
    value = re.sub(r"\bSept\b", "Sep", match[0], flags=re.I).replace(".", "")
    parsed = None
    for fmt in ("%Y-%m-%d", "%B %d, %Y", "%B %d %Y", "%b %d, %Y",
                "%b %d %Y", "%m/%d/%Y", "%m-%d-%Y"):
        try:
            parsed = datetime.strptime(value, fmt).date()
            break
        except ValueError:
            continue
    if parsed is None:
        return None
    weekdays = re.findall(r"\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b", text, re.I)
    if weekdays and any(day.casefold() != parsed.strftime("%A").casefold() for day in weekdays):
        return None
    return parsed.isoformat()


def literal_date_in(value, passages):
    """Reduce a paraphrased milestone to an unambiguous verbatim full date."""
    expected = exact_date(value)
    if expected is None:
        return None
    pattern = (r"(?<![\w/-])(?:\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{4}|"
               r"(?:January|February|March|April|May|June|July|August|September|October|November|December|"
               r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})(?![\w/-])")
    matches = [m[0] for text in passages for m in re.finditer(pattern, text, re.I)
               if exact_date(m[0]) == expected]
    return matches[0] if matches else None


def details_for(extraction):
    if "evidence_spans" not in extraction:
        return {}
    fields = DETAIL_FIELDS + ("decision_scope", "decision_authority", "decision_outcome", "milestones",
        "identity_status", "identity_conflicts", "relevance_scope", "relevance_basis", "discovery_eligible",
        "decision_action_text", "relevance_source_text", "relevance_context_text", "status_projection_reason")
    return {"contract_version": extraction.get("contract_version", CONTRACT_VERSION),
            **{k: extraction.get(k) for k in fields if k in extraction or k in DETAIL_FIELDS}}


def references_sql(alias="pe"):
    return f"COALESCE({alias}.extraction_details->'parcel_references', jsonb_build_array({alias}.parcel_reference))"


def contract_errors(item, source_text, meeting_date=None):
    """Check evidence membership and deterministic procedural counterexamples.

    This does not claim to prove entailment of generated prose. Semantic review
    remains necessary before releasing a new prompt/settings identity.
    """
    errors = []
    spans = item.get("evidence_spans")
    if not isinstance(spans, list) or not spans:
        return ["evidence_spans must contain at least one source passage"]
    quotes, covered = [], set()
    for i, span in enumerate(spans):
        if not isinstance(span, dict) or not isinstance(span.get("quote"), str):
            errors.append(f"evidence span {i} is malformed")
            continue
        quote = span["quote"]
        if not quote.strip() or compact(quote) not in compact(source_text):
            errors.append(f"evidence span {i} is not present in source")
        quotes.append(quote)
        fields = span.get("fields")
        if not isinstance(fields, list) or not all(isinstance(x, str) for x in fields):
            errors.append(f"evidence span {i} fields are malformed")
        else:
            covered.update(fields)
    for field in ("what_happened", "decision", "conditions", "upcoming_date",
                  "event_date_text", "application_ids", "project_reference", "parcel_references",
                  "applicant_name", "current_zoning", "proposed_zoning", "why_it_matters", "what_happens_next"):
        if item.get(field) and field not in covered:
            errors.append(f"{field} has no assigned evidence span")
    # Display summary quote is a real span, never joined source snippets.
    if item.get("supporting_text") not in quotes:
        errors.append("supporting_text must equal one evidence span")
    for field in ("application_ids", "parcel_references"):
        values = item.get(field)
        if not isinstance(values, list):
            errors.append(f"{field} must be an array")
            continue
        for value in values:
            if not isinstance(value, str) or not value.strip() or not any(
                compact(value).casefold() in compact(q).casefold() for q in quotes
            ):
                errors.append(f"{field} contains a reference absent from its evidence")
    project_ref = item.get("project_reference")
    if project_ref and not any(compact(project_ref).casefold() in compact(q).casefold() for q in quotes):
        errors.append("project_reference is not an exact source name")
    status = item.get("record_status")
    if status in ("scheduled", "recommendation") and item.get("decision"):
        errors.append("scheduled/recommended action cannot carry a completed decision")
    if status == "scheduled":
        from countyiq.lib.proceeding_semantics import scheduled_action_errors
        errors.extend(scheduled_action_errors(item.get("what_happened")))
    decision = item.get("decision")
    if decision and "decision" not in covered:
        errors.append("decision lacks evidence")
    for field in ("event_date_text", "upcoming_date"):
        value = item.get(field)
        if value and not any(compact(value).casefold() in compact(q).casefold() for q in quotes):
            errors.append(f"{field} is absent from its source passages")
    if item.get("event_date"):
        normalized = exact_date(item.get("event_date_text"))
        if normalized != item["event_date"]:
            errors.append("event_date requires a complete explicit source date")
        if meeting_date and status != "scheduled" and item["event_date"] > str(meeting_date):
            errors.append("completed event cannot postdate its meeting document")
    if item.get("upcoming_date_iso") and exact_date(item.get("upcoming_date")) != item["upcoming_date_iso"]:
        errors.append("upcoming_date_iso requires a complete explicit source date")
    # These footer case numbers are allocation hints, not filed applications.
    footer_ids = re.findall(r"Next\s+Conditional\s+Use\s+Case\s*#?\s*(CUH\s*\d{4}\s*-\s*\d+)", source_text, re.I)
    matter = " ".join([item.get("project_name") or "", *(item.get("application_ids") or [])])
    for case in footer_ids:
        if compact(case).casefold() in compact(matter).casefold():
            other = re.sub(r"Next\s+Conditional\s+Use\s+Case\s*#?\s*"+re.escape(case), "", source_text, flags=re.I)
            if compact(case).casefold() not in compact(other).casefold():
                errors.append("next case-number boilerplate is not a filed matter")
    if item.get("upcoming_date") and any(re.search(
        r"Conditional\s+Use\s+Hearing\s+Application\s*&\s*Plan\s+Submission", q, re.I
    ) for q in quotes):
        errors.append("generic submission calendar cannot supply a case deadline")
    return errors


def _key_text(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def application_identity(body_name, application_id):
    # IDs explicitly carrying a board/plan prefix may cross board meetings.
    # Bare docket numbers are scoped to the board to avoid PC/ZHB collisions.
    from countyiq.lib.intelligence_events import municipality_from_body_name
    ident = _key_text(application_id)
    jurisdiction = _key_text(municipality_from_body_name(body_name))
    scope = jurisdiction if re.match(r"(zhb|cuh|t|ld|sd|ordinance|resolution)\s*\d", ident) else _key_text(body_name)
    return scope + "|" + ident


def source_project_key(row):
    aliases = project_aliases(row)
    if not aliases:
        return None
    return "project:" + hashlib.sha256(aliases[0].encode()).hexdigest()[:20]


def project_aliases(row):
    details = row.get("extraction_details") or {}
    from countyiq.lib.intelligence_events import municipality_from_body_name
    aliases = []
    if details.get("identity_status") == "needs_review" or details.get("identity_conflicts"):
        return aliases
    identifiers = list(details.get("application_ids") or [])
    reference = details.get("project_reference") or ""
    if re.fullmatch(r"(?:Resolution|Ordinance)\s+(?:No\.?\s*)?\d{4}-\d+", reference, re.I):
        identifiers.append(reference)
    for app in identifiers:
        # Bare case numbers recur between boards. Cross-board identity needs
        # the SAME source case, applicant and specific location; no fuzzy joins.
        addresses = sorted(_key_text(x) for x in details.get("parcel_references") or []
                           if re.match(r"^\d", x))
        if re.match(r"^Case\s+\d", app, re.I) and row.get("applicant_name") and addresses:
            identity = "|".join((_key_text(municipality_from_body_name(row.get("body_name"))),
                                 _key_text(app), _key_text(row["applicant_name"]), ";".join(addresses)))
        else:
            identity = application_identity(row.get("body_name"), app)
        aliases.append("application|" + identity)
    # An applicant/company label alone is not a unique named development.
    if (details.get("matter_category") != "landuse_policy"
            and distinctive_project_reference(details.get("project_reference"))
            and _key_text(details["project_reference"]) != _key_text(row.get("applicant_name"))):
        from countyiq.lib.intelligence_events import municipality_from_body_name
        name = re.sub(r"^(case\s+)?[A-Za-z]*[- ]?\d{2,4}-\d{1,4}\s*", "",
                      details["project_reference"], flags=re.I)
        aliases.append("named|" + _key_text(municipality_from_body_name(row.get("body_name"))) + "|" + _key_text(name))
    return sorted(set(aliases))


def resolve_project_keys(rows, known_aliases=None):
    """Assign stable identities from explicit aliases without merging conflicts.

    Existing aliases win so adding a plan title cannot change an already-watched
    application's key. Two previously independent identities require review,
    never a silent merge. The caller persists additions in one writer transaction.
    """
    aliases = dict(known_aliases or {})
    result, additions = {}, {}
    for row in sorted(rows, key=lambda r: (str(r.get("meeting_date") or ""), str(r["id"]))):
        if (row.get("extraction_details") or {}).get("contract_version") not in {2, 3}:
            continue
        names = project_aliases(row)
        known = {aliases[name] for name in names if name in aliases}
        if len(known) > 1:
            key = None
        elif known:
            key = next(iter(known))
        elif names:
            key = "project:" + hashlib.sha256(names[0].encode()).hexdigest()[:20]
        else:
            key = None
        result[row["id"]] = key
        if len(known) <= 1:
            for name in names:
                if name not in aliases:
                    aliases[name] = key
                    additions[name] = key
    return result, additions


def distinctive_project_reference(value):
    """Generic relief/plan descriptions cannot identify unrelated applications."""
    words = _key_text(value).split()
    if re.fullmatch(
        r"(?:(?:the|a|an|proposed|new|existing) )*"
        r"(?:emergency shelter|community cent(?:er|re)|industrial building|apartment building)"
        r"(?: (?:project|renovation|conversion|expansion))?", " ".join(words)):
        return False
    generic = set("a an the and or of for at to in on proposed potential preliminary final plan plans subdivision development project review request variance relief application case accessory use steep slope dimensional building site lot lots line adjustment ordinance amendment zoning text draft road rd street st lane ln drive dr north south east west phase".split())
    generic.update("grant township borough municipality municipal county city system".split())
    if (re.search(r"\bordinance\b", str(value or ""), re.I)
            or _key_text(value) in {"agricultural security area", "battery energy storage system"}):
        return False
    meaningful = [word for word in words if word not in generic and not word.isdigit()]
    if re.search(r"\b(?:road|rd|street|st|lane|ln|drive|dr|avenue|ave|boulevard|blvd)\.?$", str(value or ""), re.I):
        return False
    return len(set(meaningful)) >= 2 and not re.match(r"^\d", str(value or "").strip())
