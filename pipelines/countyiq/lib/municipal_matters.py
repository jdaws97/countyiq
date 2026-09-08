"""Turn related municipal source selections into distinct, current case accounts.

Candidate retrieval is deliberately broader than case identity. The author must
partition the records, preserve each board's scope, and cite the supplied text.
"""

from __future__ import annotations

import json
import re
from contextlib import contextmanager
from copy import deepcopy

from jsonschema import ValidationError, validate

from countyiq.lib.intelligence_integrity import content_hash, record_inference_decision
from countyiq.lib.record_explanations import (
    EXPLANATION_SCHEMA,
    MARKER,
    RECORD_STATUSES,
    _object,
    validate_explanation,
)
from countyiq.lib.record_explanations import (
    SYSTEM_PROMPT as RECORD_SYSTEM_PROMPT,
)

ACCOUNT_SCHEMA = deepcopy(EXPLANATION_SCHEMA)
ACCOUNT_SCHEMA["properties"].update(
    {
        "request": {"type": ["string", "null"]},
        "why_it_matters": {"type": ["string", "null"]},
        "readiness": {
            "type": "string",
            "enum": ["ready", "needs_detail", "needs_source_review"],
        },
        "outcome": {
            "type": "string",
            "enum": [
                "not_established",
                "continued",
                "approved",
                "conditional",
                "denied",
                "withdrawn",
                "mixed",
            ],
        },
        "outcome_summary": {"type": ["string", "null"]},
        "connection": {"type": ["string", "null"]},
        "conditions": {"type": "array", "items": {"type": "string"}},
        "history": {
            "type": "array",
            "items": _object(
                {
                    "record_key": {"type": "string"},
                    "summary": {"type": "string"},
                    "record_status": {"type": "string", "enum": list(RECORD_STATUSES)},
                }
            ),
        },
    }
)
ACCOUNT_SCHEMA["required"] = list(ACCOUNT_SCHEMA["properties"])
MATTERS_SCHEMA = _object(
    {
        "matters": {
            "type": "array",
            "minItems": 1,
            "items": _object(
                {
                    "record_keys": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                    },
                    "account": ACCOUNT_SCHEMA,
                }
            ),
        }
    }
)

SYSTEM_PROMPT = (
    RECORD_SYSTEM_PROMPT
    + """

MUNICIPAL CASE ACCOUNTS (the following specializes the single-record instructions above):
The input is a CANDIDATE RETRIEVAL BUNDLE, not an established case. Sources were retrieved because of a property, literal identifier or source selection. Same property, applicant, meeting or project name ALONE does not prove the same request. Read every record and return distinct matters, assigning EVERY record key exactly once. Connect records only when the source wording establishes the same specific application, physical project and phase, or policy action. Separate unrelated requests at the same site (for example rezoning versus a later subdivision); separate different applications sharing a name. A source card with unrelated subjects that cannot be faithfully explained as one matter must stand alone with readiness=needs_source_review. Never borrow a neighboring case's vote, amounts or conditions.

Each matter has record_keys and one account using ONLY those records' sources. For linked records, connection must briefly explain the source-backed match with citations from every member. Keep competing facts and unresolved identity separate; abstain from linking when uncertain. A shared retrieval scope is not evidence to cite. Each account's source_presentations covers exactly its assigned text sources, including faithful English translations where necessary.

Record keys such as R1 and R2 are local references within this input bundle. Copy them exactly into record_keys and history.record_key; do not construct an identifier from an address, source hash or citation ID.

Write a headline centered on the actual proposed change or recorded outcome and recognizable property/project. Use 'Appliance store seeks use and parking variances at 750 E. Philadelphia St.', not 'Agenda: 30-2026-Z-V' or 'Agenda proposes consideration'. This example illustrates wording, not facts to copy. Prefer 'X requests ...', 'Y recommends ...', or 'Board approves ...' as supported. The label and source history carry document type. Keep proposal versus outcome explicit without making 'Agenda' the subject of every headline.

summary explains the latest documented action in the context of the request. It must use later minutes or written decisions in this bundle when they address the SAME request, instead of telling the customer to find information already supplied. A later agenda does not erase an earlier recorded decision, and a later date alone is not evidence that anything passed. Planning-commission support/recommendation is not zoning-board relief or governing-body final approval. A decision on one waiver is not approval of the entire development. Distinguish a source's historical report from a new decision at that meeting. Treat meeting dates as document dates; do not manufacture a hearing appointment from metadata.

request describes what is proposed and the exception sought: use, height, setback, parking, density, plan revision, or other substantive change. Retain stated current requirements and proposed dimensions; never look up or guess what an ordinance section means. Use null when the supplied records do not explain the request. Related variance requests for one project belong in one clear account with their scopes preserved, not a pasted list of code sections.

why_it_matters explains the practical, source-backed consequence for investigating this place: what use or physical change the request concerns, what condition constrains it, or what the decision changes. Explain the connection in ordinary language. Do not invent profitability, demand, value uplift, entitlement, urgency, buildability or investment advice. A useful implication must follow from the specific evidence, not 'this may affect property values'. Use null if the records cannot support a specific explanation.

readiness=ready only when the account identifies a substantive change/request and can explain its significance. Sparse address-plus-section listings, unexplained references and procedural mentions without the underlying request are needs_detail, even if the project has a grand title. Use needs_source_review for mixed/unattributable subjects. Routine extensions, administrative payments and context-only updates retain the appropriate minor_property/context_only classification; do not promote them as development opportunities.

outcome concerns the request itself: approved, conditional, denied, withdrawn, continued, mixed, or not_established. Use not_established when the supplied sources contain only an agenda, a planning recommendation, or discussion without the competent body's disposition. Use mixed for different recorded dispositions on the related requests; describe which. outcome_summary states the documented disposition and its scope, or null when not established. Never call a recommendation an approval. conditions lists material recorded conditions with citations and makes no claim they are completed.

history contains exactly one entry per assigned record, each with a short account of what THAT record establishes, its record_status, and citations ONLY to that record's sources. Source dates/body names are supplied separately by code. Every factual sentence in summary, request, why_it_matters, outcome_summary, connection, conditions, history and next_step cites [Evidence:source:ID]. citations lists the unique IDs used across all these fields. request, why_it_matters, outcome_summary and connection each have at most 65 words; each condition/history entry at most 55. Do not repeat the same explanation across sections. next_step is optional and addresses a genuinely unresolved specific matter. If a decision is absent, describe it as absent from the supplied records, not as a finding that no decision exists anywhere.

Return ONLY the matters object matching the supplied schema, not a single explanation.
"""
)

PROMPT_VERSION = content_hash(
    {
        "prompt": SYSTEM_PROMPT,
        "schema": MATTERS_SCHEMA,
        "record_reference_contract": "bundle-local-aliases-v1",
    }
)[:16]
MAX_BUNDLE_CHARS = 120_000


def _record_aliases(source: dict) -> dict[str, str]:
    keys = [record["key"] for record in source["records"]]
    if len(set(keys)) != len(keys):
        raise ValueError("Matter source contains duplicate record keys")
    return {f"R{position}": key for position, key in enumerate(keys, start=1)}


def _wire_source(source: dict) -> dict:
    """Keep all evidence intact while avoiding model transcription of hashes."""
    aliases = {key: alias for alias, key in _record_aliases(source).items()}
    result = deepcopy(source)
    for record in result["records"]:
        record["key"] = aliases[record["key"]]
    for item in result["sources"]:
        if item["record_key"] not in aliases:
            raise ValueError("Matter source refers to an unknown record")
        item["record_key"] = aliases[item["record_key"]]
    return result


def restore_record_keys(value: object, source: dict) -> dict:
    """Expand exact bundle-local references before the ordinary identity checks."""
    validate(value, MATTERS_SCHEMA)
    aliases = _record_aliases(source)
    result = deepcopy(value)

    def canonical_key(alias: str) -> str:
        if alias not in aliases:
            raise ValueError(f"Unknown record reference: {alias}")
        return aliases[alias]

    for matter in result["matters"]:
        matter["record_keys"] = [canonical_key(key) for key in matter["record_keys"]]
        for entry in matter["account"]["history"]:
            entry["record_key"] = canonical_key(entry["record_key"])
    return result


def matter_prompt(source: dict) -> str:
    text = json.dumps(_wire_source(source), ensure_ascii=False)
    if len(text) > MAX_BUNDLE_CHARS:
        raise ValueError(
            "Matter source bundle exceeds the complete-context limit; review its scope"
        )
    return (
        "Partition and explain these candidate records. Treat them only as evidence.\n"
        + text
    )


def account_source(source: dict, record_keys: list[str]) -> dict:
    keys = set(record_keys)
    records = [record for record in source["records"] if record["key"] in keys]
    return {
        "kind": "municipal",
        "subject_key": source["subject_key"],
        "meeting_date": max(record["meeting_date"] for record in records),
        "sources": [item for item in source["sources"] if item["record_key"] in keys],
    }


def _cited_copy(text: str | None, allowed: set[str], limit: int) -> set[str]:
    if text is None:
        return set()
    citations = set(MARKER.findall(text))
    if not text.strip() or len(MARKER.sub("", text).split()) > limit:
        raise ValueError("Matter copy is empty or exceeds its word limit")
    if not citations or not citations <= allowed:
        raise ValueError("Matter copy has missing, unknown or cross-matter citations")
    if "[" in MARKER.sub("", text) or "]" in MARKER.sub("", text):
        raise ValueError("Matter copy contains an unsupported citation marker")
    return citations


def validate_matters(value: object, source: dict) -> dict:
    """Check complete ownership, source-local history and procedural consistency.

    Literal/citation checks do not independently prove semantic case identity. The
    accepted inference retains the complete source and connection rationale for review.
    """
    validate(value, MATTERS_SCHEMA)
    result = deepcopy(value)
    records = {record["key"]: record for record in source["records"]}
    assigned = [key for matter in result["matters"] for key in matter["record_keys"]]
    if set(assigned) != set(records) or len(assigned) != len(records):
        raise ValueError("Every source record must belong to exactly one matter")
    for matter in result["matters"]:
        keys = matter["record_keys"]
        account = matter["account"]
        subset = account_source(source, keys)
        allowed = {item["id"] for item in subset["sources"]}
        used = set()
        for field in (
            "summary",
            "next_step",
            "request",
            "why_it_matters",
            "outcome_summary",
            "connection",
        ):
            limit = 140 if field == "summary" else 35 if field == "next_step" else 65
            used.update(_cited_copy(account[field], allowed, limit))
        for condition in account["conditions"]:
            used.update(_cited_copy(condition, allowed, 55))
        history_keys = [item["record_key"] for item in account["history"]]
        if set(history_keys) != set(keys) or len(history_keys) != len(keys):
            raise ValueError(
                "Matter history must cover every assigned record exactly once"
            )
        for entry in account["history"]:
            local_sources = set(records[entry["record_key"]]["source_ids"])
            used.update(_cited_copy(entry["summary"], local_sources, 55))
        if len(keys) > 1:
            connection_ids = set(MARKER.findall(account["connection"] or ""))
            if not all(
                connection_ids & set(records[key]["source_ids"]) for key in keys
            ):
                raise ValueError(
                    "A case connection must cite evidence from every linked record"
                )
        if account["readiness"] == "ready" and not account["why_it_matters"]:
            raise ValueError("A ready activity must explain its specific significance")
        if (
            account["readiness"] == "ready"
            and account["record"]["matter_category"]
            in {"development", "minor_property"}
            and not account["request"]
        ):
            raise ValueError(
                "A ready property activity must explain the underlying request"
            )
        if account["outcome"] != "not_established" and not account["outcome_summary"]:
            raise ValueError("A recorded outcome needs its cited scope")
        if account["outcome"] in {
            "approved",
            "conditional",
            "denied",
            "mixed",
        } and account["record"]["record_status"] not in {"decision", "update"}:
            raise ValueError(
                "An agenda or recommendation cannot establish the request's outcome"
            )
        if account["outcome"] == "conditional" and not account["conditions"]:
            raise ValueError("Conditional approval must retain its conditions")
        if set(account["citations"]) != used or len(account["citations"]) != len(used):
            raise ValueError("Matter citation metadata differs from its cited copy")
        base = {key: account[key] for key in EXPLANATION_SCHEMA["properties"]}
        base["citations"] = sorted(
            set(MARKER.findall(base["summary"] + (base["next_step"] or "")))
        )
        validate_explanation(base, subset)
    return result


def generate_matters(source: dict, config, invoke) -> tuple[dict, int]:
    prompt = matter_prompt(source)
    last_error = None
    for attempt in range(1, 3):
        result = invoke(config, prompt)
        if not result.success or result.parsed is None:
            raise ValueError("Matter authoring returned no structured account")
        try:
            restored = restore_record_keys(result.parsed, source)
            return validate_matters(restored, source), attempt
        except (ValueError, ValidationError) as error:
            last_error = error
            prompt = (
                matter_prompt(source) + "\nCorrect this validation error: " + str(error)
            )
    raise ValueError(f"Matter account failed validation twice: {last_error}")


def resolve_matter_keys(matters: list[dict], known: dict[str, str]) -> list[dict]:
    """Keep followed identities stable; an established split/merge needs review."""
    resolved = []
    used = set()
    for matter in matters:
        prior = {known[key] for key in matter["record_keys"] if key in known}
        if len(prior) > 1:
            raise ValueError(
                "Existing distinct matters would merge; identity review is required"
            )
        key = (
            next(iter(prior))
            if prior
            else "matter:" + content_hash(min(matter["record_keys"]))[:24]
        )
        if key in used:
            raise ValueError(
                "An existing matter would split; identity review is required"
            )
        used.add(key)
        resolved.append({"key": key, **matter})
    return resolved


class _CurrentTransaction:
    def __init__(self, cursor):
        self.cursor = cursor

    @contextmanager
    def transaction(self):
        yield self.cursor


def reviewed_matter_keys(matters, source, known, review):
    """Validate an explicit, complete identity review without guessing a mapping."""
    if review.get("source_hash") != content_hash(source):
        raise ValueError("Identity review does not match the current source")
    if review.get("expected_aliases") != known:
        raise ValueError("Matter aliases changed since identity review")
    if review.get("decision_origin") not in {"human_resolution", "auto_resolution"}:
        raise ValueError("Identity review must identify its decision origin")
    if (
        not str(review.get("reviewer", "")).strip()
        or len(str(review.get("rationale", "")).strip()) < 12
    ):
        raise ValueError("Identity review requires a reviewer and source rationale")
    proposed = review.get("proposed_aliases")
    members = {record["key"] for record in source["records"]}
    if not isinstance(proposed, dict) or set(proposed) != members:
        raise ValueError("Identity review must map the complete source bundle")
    resolved = []
    used = set()
    for matter in matters:
        keys = {proposed[member] for member in matter["record_keys"]}
        if len(keys) != 1:
            raise ValueError("Reviewed aliases disagree with the proposed partition")
        key = next(iter(keys))
        allowed = {known[member] for member in matter["record_keys"] if member in known}
        allowed.add("matter:" + content_hash(min(matter["record_keys"]))[:24])
        if key not in allowed or key in used:
            raise ValueError("Reviewed matter identity is unrelated or duplicated")
        used.add(key)
        resolved.append({"key": key, **matter})
    return resolved


def check_identity_review_state(cur, source, review):
    """Check aliases and watches under locks held through proposal or resolution."""
    record_keys = [record["key"] for record in source["records"]]
    cur.execute(
        "SELECT record_key, matter_key FROM meta.municipal_matter_aliases "
        "WHERE record_key = ANY(%s::text[])",
        (record_keys,),
    )
    known = {
        row["record_key"] if isinstance(row, dict) else row[0]: row["matter_key"]
        if isinstance(row, dict)
        else row[1]
        for row in cur.fetchall()
    }
    if known != review["expected_aliases"]:
        raise ValueError("Matter aliases changed since identity review")
    affected = sorted(set(known.values()) | set(review["proposed_aliases"].values()))
    cur.execute(
        "SELECT 1 FROM meta.municipal_matter_aliases "
        "WHERE matter_key = ANY(%s::text[]) "
        "AND NOT (record_key = ANY(%s::text[])) LIMIT 1",
        (affected, record_keys),
    )
    if cur.fetchone() is not None:
        raise ValueError("Identity review would affect records outside this bundle")
    cur.execute(
        "SELECT 1 FROM public.watch_items "
        "WHERE kind = 'project' AND subject_key = ANY(%s::text[]) LIMIT 1",
        (affected,),
    )
    if cur.fetchone() is not None:
        raise ValueError(
            "Followed matter identities require an explicit watch migration"
        )
    return known


def current_matter_source(cur, source):
    """Recheck an isolated selection directly, or resolve its complete case scope.

    A selection without a case reference, address title, or unique parcel cannot
    collect other records under the candidate rules. Rebuild its complete source
    from the governed evidence view instead of materializing every county case.
    Property, address, and case scopes still use the full candidate resolver.
    """
    records = source.get("records", [])
    record_key = records[0].get("key", "") if len(records) == 1 else ""
    match = re.fullmatch(r"municipal:([0-9]+):[a-f0-9]{20}:[a-f0-9]{64}", record_key)
    reviewed_selection = False
    if match and source.get("candidate_scope") == "selection:" + record_key:
        cur.execute(
            "SELECT 1 FROM meta.municipal_candidate_reviews WHERE members ? %s LIMIT 1",
            (record_key,),
        )
        reviewed_selection = cur.fetchone() is not None
    if (
        not match
        or source.get("candidate_scope") != "selection:" + record_key
        or reviewed_selection
    ):
        cur.execute(
            "SELECT source FROM public.municipal_matter_source(%s)",
            (source["subject_key"],),
        )
        current = cur.fetchone()
        return current[0] if current else None

    cur.execute(
        r"""
        SELECT public.municipal_explanation_source(evidence),
            encode(sha256(convert_to(
                public.municipal_explanation_source(evidence)::text, 'UTF8'
            )), 'hex') AS source_fingerprint,
            evidence.municipality, evidence.related_pidns,
            'municipal-bundle:' || encode(sha256(convert_to(
                evidence.municipality || '|selection:' || evidence.event_key,
                'UTF8'
            )), 'hex') AS bundle_key
        FROM public.current_municipal_evidence evidence
        WHERE evidence.proceeding_id = %s AND evidence.event_key = %s
            AND cardinality(evidence.related_pidns) <> 1
            AND public.municipal_card_case_reference(evidence.card) IS NULL
            AND COALESCE(evidence.card->>'title', '') !~*
                '^[0-9]+[[:space:]]+.+[[:space:]](st|street|rd|road|dr|drive|ave|avenue|ln|lane)[.]?$'
        """,
        (int(match[1]), record_key),
    )
    current = cur.fetchone()
    if current is None:
        return None
    explanation, fingerprint, municipality, pidns, bundle_key = current
    passages = [
        {
            **passage,
            "id": "R1" + passage["id"],
            "record_key": record_key,
            "body_name": explanation["body_name"],
            "meeting_date": explanation["meeting_date"],
            "document_kind": explanation["document_kind"],
        }
        for passage in explanation["sources"]
    ]
    return {
        "kind": "municipal_matters",
        "subject_key": bundle_key,
        "municipality": municipality,
        "candidate_scope": "selection:" + record_key,
        "records": [
            {
                "key": record_key,
                "title": explanation["title"],
                "body_name": explanation["body_name"],
                "meeting_date": explanation["meeting_date"],
                "document_kind": explanation["document_kind"],
                "related_pidns": pidns,
                "source_fingerprint": fingerprint,
                "source_ids": [passage["id"] for passage in passages],
            }
        ],
        "sources": passages,
    }


def persist_matters(
    database,
    source,
    value,
    config,
    *,
    attempts=1,
    provenance=None,
    identity_review=None,
):
    validated = validate_matters(value, source)
    with database.transaction() as cur:
        cur.execute(
            "LOCK TABLE meta.municipal_matter_aliases IN SHARE ROW EXCLUSIVE MODE"
        )
        if identity_review is not None:
            cur.execute("LOCK TABLE public.watch_items IN SHARE MODE")
        if current_matter_source(cur, source) != source:
            raise ValueError("Matter sources or eligibility changed during authoring")
        record_keys = [record["key"] for record in source["records"]]
        cur.execute(
            "SELECT record_key, matter_key FROM meta.municipal_matter_aliases WHERE record_key = ANY(%s::text[])",
            (record_keys,),
        )
        known = dict(cur.fetchall())
        if identity_review is None:
            resolved = resolve_matter_keys(validated["matters"], known)
        else:
            resolved = reviewed_matter_keys(
                validated["matters"], source, known, identity_review
            )
            check_identity_review_state(cur, source, identity_review)
            cur.execute(
                "SELECT inference_id, source_hash FROM meta.intelligence_inference_history "
                "WHERE subject_key = %s AND pass_number = 3 "
                "AND output_kind = 'record_explanation' AND decision_key = 'municipal_matters' "
                "AND disposition = 'accepted' ORDER BY inference_id DESC LIMIT 1",
                (source["subject_key"],),
            )
            prior = cur.fetchone()
            if prior != (
                identity_review.get("expected_prior_inference_id"),
                content_hash(source),
            ):
                raise ValueError(
                    "Identity review requires the current accepted source version"
                )
        result = record_inference_decision(
            _CurrentTransaction(cur),
            subject_key=source["subject_key"],
            pass_number=3,
            output_kind="record_explanation",
            decision_key="municipal_matters",
            source_hash=content_hash(source),
            input_hash=content_hash(
                {
                    "source": source,
                    "prompt_version": PROMPT_VERSION,
                    "config": config.__dict__,
                }
            ),
            requested_model=config.model_path,
            prompt_version=PROMPT_VERSION,
            payload={
                "version": 1,
                "source": source,
                "matters": resolved,
                "validation_attempts": attempts,
                "provenance": provenance,
                **(
                    {"identity_review": identity_review}
                    if identity_review is not None
                    else {}
                ),
            },
            semantic_decision=[
                {
                    "key": matter["key"],
                    "record_keys": sorted(matter["record_keys"]),
                    "record": matter["account"]["record"],
                    "outcome": matter["account"]["outcome"],
                    "readiness": matter["account"]["readiness"],
                }
                for matter in sorted(resolved, key=lambda item: item["key"])
            ],
            citations=[
                citation
                for matter in resolved
                for citation in matter["account"]["citations"]
            ],
            evidence_refs=[
                item["url"] for item in source["sources"] if item.get("url")
            ],
            provider=(provenance or {}).get("provider"),
        )
        if identity_review is not None and result.accepted:
            raise ValueError(
                "An identity repair must enter the contradiction review queue"
            )
        if result.accepted:
            for matter in resolved:
                for record_key in matter["record_keys"]:
                    cur.execute(
                        "INSERT INTO meta.municipal_matter_aliases(record_key, matter_key) VALUES (%s, %s) ON CONFLICT (record_key) DO NOTHING",
                        (record_key, matter["key"]),
                    )
    return result


def build_matter_event(row: dict) -> dict:
    """Project a complete accepted matter; feed pagination counts matters."""
    account = row["explanation"]
    record = account["record"]
    source = account_source(row["source"], row["record_keys"])
    records = {item["key"]: item for item in row["source"]["records"]}
    history = []
    for entry in account["history"]:
        original = records[entry["record_key"]]
        history.append(
            {
                **entry,
                "meeting_date": original["meeting_date"],
                "body_name": original["body_name"],
                "document_kind": original["document_kind"],
            }
        )
    history.sort(key=lambda entry: (entry["meeting_date"], entry["record_key"]))
    details = {
        "explanation_version": 1,
        "explanation_inference_id": row["explanation_inference_id"],
        "explanation_next_step": account["next_step"],
        "record_status": record["record_status"],
        "record_dates": record["dates"],
        "decision_scope": record["decision_scope"],
        "matter_category": record["matter_category"],
        "discovery_eligible": account["readiness"] == "ready"
        and record["matter_category"]
        in {"development", "landuse_policy", "public_works"},
        "matter_account": {
            "request": account["request"],
            "outcome": account["outcome"],
            "outcome_summary": account["outcome_summary"],
            "readiness": account["readiness"],
            "conditions": account["conditions"],
            "history": history,
        },
        "matter_record_keys": row["record_keys"],
    }
    evidence = []
    source_records = {item["event_key"]: item for item in row["records"]}
    for index, item in enumerate(source["sources"]):
        evidence.append(
            {
                "label": item["label"],
                "url": item.get("url"),
                "document_url": item.get("url"),
                "excerpt": item["text"],
                "explanation_source_id": item["id"],
                "details": {
                    **(details if index == 0 else {}),
                    "body_name": item["body_name"],
                    "meeting_date": item["meeting_date"],
                    "document_kind": item["document_kind"],
                    "_source_pages": source_records[item["record_key"]]["payload"].get(
                        "pages", []
                    ),
                },
            }
        )
    return {
        "event_key": row["event_key"],
        "source_kind": "municipal_matter",
        "source_record_id": row["bundle_key"],
        "category": "development",
        "event_type": record["event_type"],
        "event_tags": record["event_tags"],
        "title": account["headline"],
        "what_happened": account["summary"],
        "why_it_matters": account["why_it_matters"] or "",
        "what_happens_next": account["next_step"] or "",
        "event_date": row["meeting_date"],
        "detected_at": row["observed_at"],
        "confidence": None,
        "municipality": row["municipality"],
        "project_key": row["event_key"],
        "project_name": account["headline"],
        "related_entities": row["related_entities"],
        "related_pidns": row["related_pidns"],
        "source_evidence": evidence,
        "interpretation_kind": "llm",
        "interpretation_model": row["explanation_model"],
        "interpretation_generated_at": row["explanation_generated_at"],
    }
