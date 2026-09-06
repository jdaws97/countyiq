"""Pass 0 v3: cited claims hydrated from a source-bound passage index.

The caller binds model claims to the source fingerprint captured before the call.
Model output never supplies that fingerprint, ISO dates, field-assignment lists or
display evidence. Membership and conservative counterexamples are checked here;
semantic release evaluation remains mandatory.
"""

from copy import deepcopy
import json
import re
from jsonschema import Draft202012Validator
from countyiq.lib.pass_schemas import PASS0_EXTRACTION_SCHEMA
from countyiq.lib.source_passages import index_source_passages
from countyiq.lib.proceeding_contract import compact, exact_date

VERSION = 3
MAX_SOURCE_CHARS = 140_000
# Provider strict schemas reject uniqueItems; doc.resolve enforces uniqueness locally.
IDS = {"type": "array", "items": {"type": "string"}, "minItems": 1}


def obj(properties):
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def choice(values):
    return {"type": "string", "enum": values.split()}


def array(item):
    return {"type": "array", "items": item}


CLAIM = obj({"text": {"type": "string", "minLength": 1}, "passage_ids": IDS})
NULLABLE_CLAIM = {"anyOf": [CLAIM, {"type": "null"}]}
SCOPES = (
    "plan variance special_exception conditional_use ordinance bond contract "
    "naming procedural unknown"
)
STATUSES = "scheduled recommendation decision update withdrawn removed"
KINDS = (
    "hearing decision_deadline bid_advertisement bid_opening construction_start "
    "completion other"
)
RELEVANCE_SCOPES = (
    "new_construction expansion conversion redevelopment new_lots plan_review "
    "subdivision_only property_relief policy_change capital_project "
    "project_milestone unknown"
)
ITEM = obj(
    {
        "extraction_type": deepcopy(
            PASS0_EXTRACTION_SCHEMA["properties"]["extractions"]["items"]["properties"][
                "extraction_type"
            ]
        ),
        "project_name": {"type": ["string", "null"]},
        "what_happened": CLAIM,
        "applicant_name": NULLABLE_CLAIM,
        "current_zoning": NULLABLE_CLAIM,
        "proposed_zoning": NULLABLE_CLAIM,
        "conditions": array(CLAIM),
        "why_it_matters": NULLABLE_CLAIM,
        "what_happens_next": NULLABLE_CLAIM,
        "record_status": choice(STATUSES),
        "decision": {
            "anyOf": [
                obj(
                    {
                        "outcome": choice("approved denied tabled continued"),
                        "scope": choice(SCOPES),
                        "authority": {"type": "string", "minLength": 1},
                        "passage_ids": IDS,
                    }
                ),
                {"type": "null"},
            ]
        },
        "event_date": NULLABLE_CLAIM,
        "milestones": array(
            obj(
                {
                    "kind": choice(KINDS),
                    "text": {"type": "string", "minLength": 1},
                    "passage_ids": IDS,
                }
            )
        ),
        "application_ids": array(CLAIM),
        "project_reference": NULLABLE_CLAIM,
        "parcel_references": array(CLAIM),
        "related_entities": array(CLAIM),
        "identity_conflicts": array(CLAIM),
        "relevance": obj(
            {
                "category": choice(
                    "development minor_property landuse_policy public_works context_only"
                ),
                "scope": choice(RELEVANCE_SCOPES),
                "basis": CLAIM,
            }
        ),
        "confidence": choice("high medium low"),
    }
)
PASS0_CLAIMS_SCHEMA = obj(
    {
        "source_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "extractions": array(ITEM),
    }
)
# Keep the old wire contract only for explicitly labeled offline replays.
LEGACY_CLAIMS_SCHEMA = deepcopy(PASS0_CLAIMS_SCHEMA)
decision_schema = ITEM["properties"]["decision"]["anyOf"][0]
decision_schema["properties"]["action_text"] = {"type": "string", "minLength": 1}
decision_schema["required"].append("action_text")
relevance_schema = ITEM["properties"]["relevance"]
relevance_schema["properties"]["source_text"] = {"type": "string", "minLength": 1}
relevance_schema["required"].append("source_text")
# Preserve the prior cited wire shape for explicit offline replay. The stored
# projection remains version 3; the current prompt/schema identity changes.
NARRATIVE_REPLAY_SCHEMA = deepcopy(PASS0_CLAIMS_SCHEMA)
for field in ("why_it_matters", "what_happens_next"):
    del ITEM["properties"][field]
    ITEM["required"].remove(field)
# The stored/replay envelope retains its fingerprint. The model only selects
# claims; copying a cryptographic hash cannot establish request provenance.
PASS0_MODEL_SCHEMA = obj(
    {"extractions": deepcopy(PASS0_CLAIMS_SCHEMA["properties"]["extractions"])}
)
_MODEL_ENVELOPE_VALIDATOR = Draft202012Validator(obj({"extractions": array({})}))
_VALIDATOR = Draft202012Validator(PASS0_CLAIMS_SCHEMA)


def passage_document(source_text):
    if not isinstance(source_text, str) or not source_text.strip():
        raise ValueError("Source text is unavailable")
    if len(source_text) > MAX_SOURCE_CHARS:
        raise ValueError(
            "Whole source exceeds the passage contract limit; review before extraction"
        )
    return index_source_passages(source_text)


def source_input(source_text):
    doc = passage_document(source_text)
    return json.dumps(
        {"passages": [{"id": p.passage_id, "text": p.text} for p in doc.passages]},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def bind_model_claims(payload, source_text, *, expected_source_sha256):
    """Bind a response to its caller's pre-call source snapshot without editing it.

    The caller must retain request/response identity; passage IDs are local to
    one document. Never obtain expected_source_sha256 from model output or use
    this function to repair historical responses with an incorrect copied hash.
    Item validation remains in review_claims so bad siblings can be quarantined.
    """
    doc = passage_document(source_text)
    if expected_source_sha256 != doc.source_sha256:
        raise ValueError("Source text changed from the request snapshot")
    errors = list(_MODEL_ENVELOPE_VALIDATOR.iter_errors(payload))
    if errors:
        raise ValueError(
            "Invalid model-claims envelope: " + "; ".join(e.message for e in errors[:5])
        )
    return {
        "source_sha256": expected_source_sha256,
        "extractions": deepcopy(payload["extractions"]),
    }


def hydrate_claims(
    payload,
    source_text,
    *,
    meeting_date=None,
    legacy_evaluation=False,
    narrative_evaluation=False,
):
    """Validate a source-bound envelope before producing a stored projection."""
    if legacy_evaluation and narrative_evaluation:
        raise ValueError("Choose one historical replay contract")
    validator = (
        Draft202012Validator(LEGACY_CLAIMS_SCHEMA)
        if legacy_evaluation
        else Draft202012Validator(NARRATIVE_REPLAY_SCHEMA)
        if narrative_evaluation
        else _VALIDATOR
    )
    errors = sorted(validator.iter_errors(payload), key=lambda e: str(e.path))
    if errors:
        raise ValueError(
            "Invalid cited claims: "
            + "; ".join(f"{e.json_path}: {e.message}" for e in errors[:5])
        )
    doc = passage_document(source_text)
    if payload["source_sha256"] != doc.source_sha256:
        raise ValueError("Cited claims belong to a different source")
    output = []
    for item in payload["extractions"]:
        spans = {}

        def passages(ids, fields):
            selected = doc.resolve(payload["source_sha256"], ids)
            # Join only adjacent indexed ranges, never disjoint source passages.
            groups = []
            for p in selected:
                if groups and groups[-1][1] == p.start:
                    groups[-1] = (groups[-1][0], p.end)
                else:
                    groups.append((p.start, p.end))
            texts = []
            for start, end in groups:
                text = source_text[start:end]
                texts.append(text)
                entry = spans.setdefault(
                    (start, end),
                    {
                        "quote": text,
                        "fields": set(),
                        "source_sha256": doc.source_sha256,
                        "start": start,
                        "end": end,
                    },
                )
                entry["fields"].update(fields)
            return texts

        def claim(value, field, literal=False):
            if value is None:
                return None
            texts = passages(value["passage_ids"], [field])
            text = value["text"]
            if literal and not any(
                compact(text).casefold() in compact(q).casefold() for q in texts
            ):
                # Copy an explicit full date, never synthesize one from metadata.
                # A paraphrased milestone may be reduced to its exact source date;
                # its purpose remains in kind and its selected evidence.
                from countyiq.lib.proceeding_contract import literal_date_in

                date_text = (
                    literal_date_in(text, texts) if field == "milestones" else None
                )
                if date_text is not None:
                    return date_text
                if (
                    field == "event_date_text"
                    and meeting_date
                    and exact_date(text) == str(meeting_date)
                ):
                    header = doc.passages[0]
                    if compact(text).casefold() in compact(header.text).casefold():
                        passages([header.passage_id], [field])
                        return text
                raise ValueError(
                    f"{field} must preserve wording from its selected source passages"
                )
            return text

        result = {
            "contract_version": VERSION,
            "extraction_type": item["extraction_type"],
            "project_name": item["project_name"],
            "record_status": item["record_status"],
            "confidence": item["confidence"],
        }
        for field in (
            "what_happened",
            "applicant_name",
            "current_zoning",
            "proposed_zoning",
            "project_reference",
        ):
            result[field] = claim(
                item[field],
                field,
                literal=field
                in {
                    "applicant_name",
                    "current_zoning",
                    "proposed_zoning",
                    "project_reference",
                },
            )
        # Retired storage columns stay empty for current extractions. Historical
        # evaluation retains original claims and their evidence without rewriting
        # a saved response to make it conform to the current wire contract.
        for field in ("why_it_matters", "what_happens_next"):
            result[field] = (
                claim(item[field], field)
                if legacy_evaluation or narrative_evaluation
                else None
            )
        for field in (
            "conditions",
            "application_ids",
            "parcel_references",
            "related_entities",
            "identity_conflicts",
        ):
            result[field] = [
                claim(
                    c,
                    field,
                    literal=field
                    in {"application_ids", "parcel_references", "related_entities"},
                )
                for c in item[field]
            ]
        for index, condition in enumerate(item["conditions"]):
            passages(condition["passage_ids"], [f"condition:{index}"])
        result["identity_status"] = (
            "needs_review" if result["identity_conflicts"] else "source_identified"
        )
        if any(
            re.search(r"\b(?:SD|LD)-\d+-\d{5,}\b", value, re.I)
            for value in result["application_ids"]
        ):
            result["identity_status"] = "needs_review"
            result["identity_conflicts"].append(
                "Source application identifier may contain a concatenated address"
            )
        resolutions = {
            compact(value).casefold()
            for value in [*result["application_ids"], result["project_reference"] or ""]
            if re.match(r"resolution\b", value, re.I)
        }
        if len(resolutions) > 1:
            result["identity_status"] = "needs_review"
            result["identity_conflicts"].append(
                "Multiple resolution identifiers require review before identity linking"
            )
        result["parcel_reference"] = "; ".join(result["parcel_references"]) or None
        result["event_date_text"] = claim(
            item["event_date"], "event_date_text", literal=True
        )
        result["event_date"] = exact_date(result["event_date_text"])
        result["milestones"] = []
        for index, milestone in enumerate(item["milestones"]):
            text = claim(milestone, "milestones", literal=True)
            passages(milestone["passage_ids"], [f"milestone:{index}"])
            kind = milestone["kind"]
            # A source-labeled meeting is not necessarily a public hearing.
            # Preserve its exact text/date while withholding that added claim.
            if (
                kind == "hearing"
                and re.search(r"\bmeeting\b", text, re.I)
                and not re.search(r"\bhearing\b", text, re.I)
            ):
                kind = "other"
            result["milestones"].append(
                {
                    "kind": kind,
                    "text": text,
                    "date": exact_date(text),
                    "passage_ids": milestone["passage_ids"],
                }
            )
        # v3 consumers use the purpose-labeled list; never collapse it into one deadline.
        result["upcoming_date"] = None
        result["upcoming_date_iso"] = None
        if any(
            re.search(r"date|year|letter", conflict, re.I)
            for conflict in result["identity_conflicts"]
        ):
            result["event_date"] = None
            for milestone in result["milestones"]:
                milestone["date"] = None
        if result["record_status"] == "recommendation":
            wording = " ".join(
                passages(item["what_happened"]["passage_ids"], ["what_happened"])
            )
            from countyiq.lib.proceeding_semantics import cited_unanimous_recommendation

            if (
                re.search(r"approve\s*/\s*deny", wording, re.I)
                and not re.search(
                    r"recommended|recommendation (?:carried|passed)|motion (?:carried|passed)|voted",
                    wording,
                    re.I,
                )
                and not cited_unanimous_recommendation(
                    source_text,
                    result["application_ids"],
                    doc.resolve(
                        doc.source_sha256, item["what_happened"]["passage_ids"]
                    ),
                )
            ):
                raise ValueError(
                    "An unselected agenda template is not an advisory recommendation"
                )
        decision = item["decision"]
        result.update(
            decision=None,
            decision_scope=None,
            decision_authority=None,
            decision_outcome=None,
        )
        if decision:
            texts = passages(
                decision["passage_ids"],
                ["decision", "decision_scope", "decision_authority"],
            )
            # Advisory referrals may be labeled recommendations while also
            # carrying their completed procedural vote. Normalize only that
            # narrow combination; all source/authority/action validation below
            # still runs before the projected item can be accepted.
            from countyiq.lib.proceeding_semantics import recorded_vote

            action_claim = decision.get("action_text") or ""
            if (
                result["record_status"] == "recommendation"
                and decision["scope"] == "procedural"
                and decision["outcome"] == "approved"
                and re.search(
                    r"\b(?:PC|Planning Commission)\b", decision["authority"], re.I
                )
                and re.search(r"\b(?:forward|refer|recommend)\w*\b", action_claim, re.I)
                and recorded_vote(action_claim) is True
            ):
                result["record_status"] = "decision"
                result["status_projection_reason"] = (
                    "Source records a completed advisory procedural vote; no ordinance or plan approval inferred."
                )
            if result["record_status"] != "decision":
                raise ValueError("Only a completed decision can carry an outcome")
            if not any(
                compact(decision["authority"]).casefold() in compact(q).casefold()
                for q in texts
            ):
                header = doc.passages[0]
                from countyiq.lib.proceeding_semantics import header_authority_supported

                if header_authority_supported(
                    decision["authority"],
                    decision.get("action_text") or " ".join(texts),
                    header.text,
                ):
                    passages([header.passage_id], ["decision_authority"])
                else:
                    raise ValueError(
                        "Decision authority must occur in its source evidence"
                    )
            if decision["scope"] == "unknown":
                raise ValueError("A completed outcome requires a known decision scope")
            wording = " ".join(texts)
            if not legacy_evaluation:
                action = decision["action_text"]
                if not any(
                    compact(action).casefold() in compact(q).casefold() for q in texts
                ):
                    raise ValueError(
                        "Decision action_text must occur in its selected source passages"
                    )
                # Store the short action excerpt independently from header evidence.
                result["decision_action_text"] = action
            else:
                action = wording
            from countyiq.lib.proceeding_semantics import decision_errors

            problems = decision_errors(decision, action)
            if problems:
                raise ValueError("; ".join(problems))
            scope = decision["scope"]
            if scope == "plan" and re.search(
                r"Subdivision and Land Development Modification Request", action, re.I
            ):
                scope = "procedural"
            result.update(
                decision=decision["outcome"],
                decision_outcome=decision["outcome"],
                decision_scope=scope,
                decision_authority=decision["authority"],
            )
        relevance = item["relevance"]
        basis = claim(relevance["basis"], "relevance_basis")
        cited_basis = " ".join(
            passages(relevance["basis"]["passage_ids"], ["relevance_basis"])
        )
        if not legacy_evaluation:
            relevance_source = claim(
                {
                    "text": relevance["source_text"],
                    "passage_ids": relevance["basis"]["passage_ids"],
                },
                "relevance_source_text",
                literal=True,
            )
            result["relevance_source_text"] = relevance_source
        else:
            # Old outputs lack item excerpts: classify their stated claim only.
            # This replay is diagnostic and cannot produce a release receipt.
            relevance_source = result["what_happened"]
        from countyiq.lib.proceeding_semantics import (
            relevance_projection,
            agenda_update_errors,
        )

        problems = agenda_update_errors(
            result["record_status"],
            result["what_happened"],
            source_text,
            relevance_source if not legacy_evaluation else cited_basis,
        )
        if problems:
            raise ValueError("; ".join(problems))
        scope_context, context_ids = _scope_context(
            source_text,
            relevance_source,
            doc.resolve(doc.source_sha256, relevance["basis"]["passage_ids"]),
            document_passages=doc.passages,
        )
        if scope_context:
            result["relevance_context_text"] = scope_context
            passages(context_ids, ["relevance_context_text"])
        if result["record_status"] in {"removed", "withdrawn"}:
            lifecycle_text = scope_context or relevance_source
            for field in ("what_happens_next", "what_happened"):
                value = item.get(field)
                if value and any(
                    compact(value["text"]).casefold() in compact(q).casefold()
                    for q in passages(value["passage_ids"], [field])
                ):
                    lifecycle_text += " " + value["text"]
            terminal = re.search(
                r"\b(?:withdrawn|withdrew|withdraw|removed|remove)\b",
                lifecycle_text,
                re.I,
            )
            future = re.search(
                r"will be (?:in|on|at).{0,70}(?:meetings?|agenda)|"
                r"(?:deferred|rescheduled) (?:to|until|for)",
                lifecycle_text,
                re.I,
            )
            if future and not terminal:
                if re.search(
                    r"\b(?:withdrawn|withdrew|withdraw|removed|remove)\b",
                    result["what_happened"],
                    re.I,
                ):
                    raise ValueError(
                        "Terminal wording conflicts with source scheduling future consideration"
                    )
                result["record_status"] = "scheduled"
                result["status_projection_reason"] = (
                    "Source explicitly schedules future consideration; no terminal action."
                )
            elif not terminal:
                raise ValueError(
                    "Terminal case status requires explicit item-specific source action"
                )
        from countyiq.lib.proceeding_contract import distinctive_project_reference

        source_identity = bool(
            result["parcel_references"]
            or result["application_ids"]
            or distinctive_project_reference(result["project_reference"])
        )
        category, scope, positive = relevance_projection(
            relevance["category"],
            relevance["scope"],
            basis,
            relevance_source,
            summary=result["what_happened"],
            source_context=scope_context,
            decision_action=result.get("decision_action_text", ""),
            source_identity=source_identity,
        )
        result.update(
            matter_category=category, relevance_scope=scope, relevance_basis=basis
        )
        result["discovery_eligible"] = bool(
            positive
            and result["decision_scope"] not in {"bond", "naming"}
            and (
                result["decision_scope"] != "procedural"
                or category in {"landuse_policy", "public_works"}
                or result["decision_outcome"] in {"tabled", "continued"}
            )
            and result["record_status"] not in {"withdrawn", "removed"}
        )
        result["event_tags"] = []
        if result["record_status"] in {"withdrawn", "removed"}:
            result["event_tags"] = [result["record_status"]]
        elif decision:
            result["event_tags"] = [
                {
                    "approved": "approval",
                    "denied": "denial",
                    "tabled": "continuance",
                    "continued": "continuance",
                }[decision["outcome"]]
            ]
        elif result["record_status"] == "scheduled":
            result["event_tags"] = ["application"]
        elif result["record_status"] == "recommendation":
            result["event_tags"] = ["recommendation"]
        result["evidence_spans"] = [
            {**s, "fields": sorted(s["fields"])} for _, s in sorted(spans.items())
        ]
        result["supporting_text"] = next(
            s["quote"]
            for s in result["evidence_spans"]
            if "what_happened" in s["fields"]
        )
        # Reuse the fail-closed quote/date gate after hydration, not just wire shape.
        from countyiq.lib.intelligence_integrity import validate_pass0_extractions

        errors = validate_pass0_extractions(
            [result], source_text, meeting_date=meeting_date, require_contract=True
        )
        if errors:
            raise ValueError("; ".join(errors))
        output.append(result)
    return output


def _scope_context(source, excerpt, selected, *, document_passages=()):
    """Expand a unique excerpt only to its short source sentence in cited ranges."""
    matches = list(
        re.finditer(r"\s+".join(re.escape(w) for w in excerpt.split()), source, re.I)
    )
    if len(matches) != 1:
        return "", []
    match = matches[0]
    covering = [p for p in selected if p.start < match.end() and p.end > match.start()]
    if (
        not covering
        or match.start() < covering[0].start
        or match.end() > covering[-1].end
        or any(a.end != b.start for a, b in zip(covering, covering[1:]))
    ):
        return "", []
    # Expansion never crosses a source line or sentence boundary. The original
    # excerpt itself may span adjacent indexed passages.
    boundaries = [m.end() for m in re.finditer(r"[.!?;]\s+|\n", source)]
    start = max([covering[0].start, *[n for n in boundaries if n <= match.start()]])
    end = min([covering[-1].end, *[n for n in boundaries if n >= match.end()]])
    # An explicitly subordinate lettered entry may inherit its immediately
    # preceding numbered heading ("3.03 Comprehensive Plan:\na. Review...").
    # Never borrow a neighboring main entry or cross uncited passage bounds.
    line_start = source.rfind("\n", 0, match.start()) + 1
    if re.match(r"\s*[a-z][.)]\s+", source[line_start : match.end()]):
        heading_start = source.rfind("\n", 0, max(0, line_start - 1)) + 1
        heading = source[heading_start:line_start].strip()
        if re.fullmatch(r"\d+(?:\.\d+)*\s+[^:\n]{3,100}:", heading):
            if heading_start >= covering[0].start:
                start = heading_start
            else:
                # The index may split exactly between the heading and its child.
                # Recover that one adjacent source passage, preserving its ID
                # as additional evidence; never search another section.
                previous = next(
                    (
                        p
                        for p in document_passages
                        if p.start <= heading_start < p.end
                        and p.end == covering[0].start
                    ),
                    None,
                )
                if previous is not None:
                    covering.insert(0, previous)
                    start = heading_start
    if end - start > 750:
        return "", []
    return source[start:end], [p.passage_id for p in covering]


def _withhold_optional_entities(item, doc):
    """Drop unsupported optional entity names without losing a valid matter."""
    try:
        if not isinstance(item.get("related_entities"), list):
            return item, []
        validator = Draft202012Validator(CLAIM)
        kept, rejected = [], []
        for value in item["related_entities"]:
            if list(validator.iter_errors(value)):
                return item, []
            selected = doc.resolve(doc.source_sha256, value["passage_ids"])
            groups = []
            for p in selected:
                if groups and groups[-1][1] == p.start:
                    groups[-1] = (groups[-1][0] + p.text, p.end)
                else:
                    groups.append((p.text, p.end))
            if any(
                compact(value["text"]).casefold() in compact(text).casefold()
                for text, _ in groups
            ):
                kept.append(value)
            else:
                rejected.append(
                    {
                        "field": "related_entities",
                        "claim": deepcopy(value),
                        "reason": "Optional entity name is not literal in its cited source; omitted from projection.",
                    }
                )
        if not rejected:
            return item, []
        candidate = deepcopy(item)
        candidate["related_entities"] = kept
        return candidate, rejected
    except (AttributeError, KeyError, TypeError, ValueError):
        return item, []


def _repair_relevance_citation(item, doc, source_text):
    """Relocate one unique exact excerpt, only within the same cited matter.

    Never change its meaning, search distant sections, or repair decision votes.
    The original wire item remains in the inference archive.
    """
    try:
        relevance = item["relevance"]
        excerpt = relevance["source_text"]
        declared = doc.resolve(doc.source_sha256, relevance["basis"]["passage_ids"])
        narrative = doc.resolve(doc.source_sha256, item["what_happened"]["passage_ids"])
        if len(excerpt.split()) < 4 or len(excerpt) < 24:
            return item, None
        pattern = r"\s+".join(re.escape(w) for w in excerpt.split())
        matches = list(re.finditer(pattern, source_text, re.I))
        if len(matches) != 1:
            return item, None
        match = matches[0]
        actual = [
            p for p in doc.passages if p.start < match.end() and p.end > match.start()
        ]
        actual_ids = {p.passage_id for p in actual}
        declared_ids = {p.passage_id for p in declared}
        if actual_ids <= declared_ids:
            return item, None
        positions = {p.passage_id: i for i, p in enumerate(doc.passages)}
        if not actual_ids <= {p.passage_id for p in narrative} or any(
            min(
                abs(positions[p.passage_id] - positions[q.passage_id]) for q in declared
            )
            > 1
            for p in actual
        ):
            return item, None
        identities = [*item["parcel_references"], *item["application_ids"]]
        if item.get("project_reference"):
            identities.append(item["project_reference"])
        local_text = source_text[actual[0].start : actual[-1].end]
        anchored = any(
            len(value["text"].strip()) >= 6
            and actual_ids.intersection(value["passage_ids"])
            and compact(value["text"]).casefold() in compact(local_text).casefold()
            for value in identities
        )
        decision = item.get("decision")
        if decision and actual_ids <= set(decision["passage_ids"]):
            # The exact action can bind policy relevance without a parcel/name.
            anchored = anchored or (
                compact(excerpt).casefold()
                in compact(decision.get("action_text", "")).casefold()
                and len(decision.get("action_text", "")) >= 24
            )
        if not anchored:
            return item, None
        repaired = deepcopy(item)
        ids = [
            p.passage_id
            for p in doc.passages
            if p.passage_id in actual_ids | declared_ids
        ]
        repaired["relevance"]["basis"]["passage_ids"] = ids
        repaired["relevance"]["source_text"] = match[0]
        return repaired, {
            "field": "relevance.source_text",
            "from_passage_ids": list(relevance["basis"]["passage_ids"]),
            "to_passage_ids": ids,
            "source_quote": match[0],
            "reason": "unique exact excerpt in adjacent narrative/identity-cited passage",
        }
    except (KeyError, TypeError, ValueError, AttributeError):
        # Shape errors must still reach the normal per-item validator.
        return item, None


def review_claims(
    payload,
    source_text,
    *,
    meeting_date=None,
    legacy_evaluation=False,
    narrative_evaluation=False,
):
    """Validate the envelope once and quarantine bad items without publishing them.

    Empty model output differs from an entirely rejected document. All conflicting
    duplicate items are quarantined together; input order cannot pick a winner.
    """
    if legacy_evaluation and narrative_evaluation:
        raise ValueError("Choose one historical replay contract")
    schema = deepcopy(
        LEGACY_CLAIMS_SCHEMA
        if legacy_evaluation
        else NARRATIVE_REPLAY_SCHEMA
        if narrative_evaluation
        else PASS0_CLAIMS_SCHEMA
    )
    schema["properties"]["extractions"]["items"] = {}
    errors = list(Draft202012Validator(schema).iter_errors(payload))
    if errors:
        raise ValueError(
            "Invalid cited-claims envelope: " + "; ".join(e.message for e in errors[:5])
        )
    doc = passage_document(source_text)
    if payload["source_sha256"] != doc.source_sha256:
        raise ValueError("Cited claims belong to a different source")
    accepted, rejected, indices, repairs, field_rejections = [], [], [], [], []
    for index, item in enumerate(payload["extractions"]):
        try:
            candidate, fields = (
                (item, [])
                if legacy_evaluation
                else _withhold_optional_entities(item, doc)
            )
            candidate, repair = (
                (candidate, None)
                if legacy_evaluation
                else _repair_relevance_citation(candidate, doc, source_text)
            )
            value = hydrate_claims(
                {"source_sha256": payload["source_sha256"], "extractions": [candidate]},
                source_text,
                meeting_date=meeting_date,
                legacy_evaluation=legacy_evaluation,
                narrative_evaluation=narrative_evaluation,
            )[0]
            accepted.append(value)
            indices.append(index)
            if repair:
                repairs.append({"index": index, **repair})
            field_rejections.extend({"index": index, **field} for field in fields)
        except ValueError as exc:
            rejected.append({"index": index, "errors": [str(exc)]})
    groups = {}
    for index, value in zip(indices, accepted):
        key = tuple(
            str(value.get(k) or "").strip().casefold()
            for k in (
                "extraction_type",
                "applicant_name",
                "parcel_reference",
                "project_name",
            )
        )
        groups.setdefault(key, []).append(index)
    duplicates = {i for group in groups.values() if len(group) > 1 for i in group}
    rejected.extend(
        {"index": i, "errors": ["Duplicate or conflicting matter requires review"]}
        for i in duplicates
    )
    kept = [(i, v) for i, v in zip(indices, accepted) if i not in duplicates]
    from countyiq.lib.proceeding_coverage import review_coverage

    return {
        "extractions": [v for _, v in kept],
        "accepted_indices": [i for i, _ in kept],
        "citation_repairs": [r for r in repairs if r["index"] not in duplicates],
        "field_rejections": [
            r for r in field_rejections if r["index"] not in duplicates
        ],
        "coverage": review_coverage(source_text, [v for _, v in kept]),
        "rejected_items": sorted(rejected, key=lambda x: x["index"]),
    }
