"""Synthetic regressions from the capped municipal evaluation; no external calls."""

from copy import deepcopy
import pytest
from tests.test_proceeding_claims import payload, SOURCE
from countyiq.lib.proceeding_claims import (
    hydrate_claims,
    review_claims,
    passage_document,
)
from countyiq.lib.proceeding_contract import (
    project_aliases,
    details_for,
    distinctive_project_reference,
)
from countyiq.assets.enrichment.proceeding_extraction import has_landuse_vocabulary
from eval.municipal_pilot import evaluate_format


def simple(source, summary=None):
    wire = payload(source)
    item = wire["extractions"][0]
    item.update(
        project_name="Synthetic proposal",
        record_status="scheduled",
        decision=None,
        event_date=None,
        milestones=[],
        conditions=[],
        application_ids=[],
        parcel_references=[],
        project_reference=None,
    )
    item["what_happened"]["text"] = summary or source
    item["relevance"].update(
        category="context_only", scope="unknown", source_text=source
    )
    item["relevance"]["basis"]["text"] = source
    return wire


def test_bad_sibling_quarantined_and_source_envelope_still_global():
    wire = payload()
    bad = deepcopy(wire["extractions"][0])
    bad["application_ids"][0]["text"] = "SD-99-2026"
    wire["extractions"].append(bad)
    before = deepcopy(wire)
    result = review_claims(wire, SOURCE)
    assert result["accepted_indices"] == [0]
    assert result["rejected_items"][0]["index"] == 1
    assert wire == before
    report = evaluate_format(wire, SOURCE)
    assert report["runtime_gate_passed"]
    assert not report["complete_document_gate_passed"]
    assert report["extraction_count"] == 1
    wire["source_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="different source"):
        review_claims(wire, SOURCE)


def test_item_schema_failure_does_not_drop_valid_sibling():
    wire = payload()
    wire["extractions"].append({"malformed": "item"})
    result = evaluate_format(wire, SOURCE)
    assert result["schema_errors"]
    assert result["runtime_gate_passed"]
    assert result["extraction_count"] == 1
    assert len(result["rejected_items"]) == 1


def test_all_rejected_is_not_a_successful_empty_extraction():
    wire = payload()
    wire["extractions"][0]["application_ids"][0]["text"] = "invented"
    result = evaluate_format(wire, SOURCE)
    assert not result["runtime_gate_passed"]
    assert result["extraction_count"] == 0
    assert result["rejected_items"]


def test_both_conflicting_or_duplicate_siblings_quarantined():
    wire = payload()
    wire["extractions"].append(deepcopy(wire["extractions"][0]))
    result = review_claims(wire, SOURCE)
    assert result["extractions"] == []
    assert {x["index"] for x in result["rejected_items"]} == {0, 1}


@pytest.mark.parametrize(
    "summary,allowed",
    [
        (
            "The agenda requests a waiver that a preliminary plan be submitted and approved before a final plan.",
            True,
        ),
        ("The application is scheduled to be considered.", True),
        ("Council approved the application.", False),
        ("The application has been approved.", False),
    ],
)
def test_prospective_prerequisite_does_not_become_completed_action(summary, allowed):
    source = "SYNTHETIC AGENDA. " + summary
    result = review_claims(simple(source, summary), source)
    assert bool(result["extractions"]) == allowed


def test_neighbor_vote_cannot_validate_moved_to_grant():
    source = (
        "SYNTHETIC MINUTES. Council approved another item. Motion carried unanimously. "
        "Council moved to grant the garage variance subject to five conditions. "
        "Council discussed the next property."
    )
    wire = simple(source, "Council approved the garage variance.")
    item = wire["extractions"][0]
    item["record_status"] = "decision"
    item["decision"] = dict(
        outcome="approved",
        scope="variance",
        authority="Council",
        passage_ids=item["what_happened"]["passage_ids"],
        action_text=source,
    )
    with pytest.raises(ValueError, match="motion without a recorded outcome"):
        hydrate_claims(wire, source)


@pytest.mark.parametrize(
    "action,scope,allowed",
    [
        (
            "Council approved edits to the draft ordinance and submitted it for review.",
            "ordinance",
            False,
        ),
        (
            "Council approved edits to the draft ordinance and submitted it for review.",
            "procedural",
            True,
        ),
        ("Council adopted Ordinance 2026-4.", "ordinance", True),
        (
            "Council moved to grant the variance. Motion carried unanimously.",
            "variance",
            True,
        ),
    ],
)
def test_draft_preparation_and_completed_vote_have_distinct_scope(
    action, scope, allowed
):
    source = "SYNTHETIC MINUTES. " + action
    wire = simple(source, action)
    item = wire["extractions"][0]
    item["record_status"] = "decision"
    item["decision"] = dict(
        outcome="approved",
        scope=scope,
        authority="Council",
        passage_ids=item["what_happened"]["passage_ids"],
        action_text=action,
    )
    result = review_claims(wire, source)
    assert bool(result["extractions"]) == allowed
    if allowed and scope == "procedural":
        assert not result["extractions"][0]["discovery_eligible"]


def test_narrative_cannot_invent_decision_excerpt_or_relevance_excerpt():
    for field in ("decision", "relevance"):
        wire = payload()
        wire["extractions"][0][field][
            "action_text" if field == "decision" else "source_text"
        ] = "Invented excerpt."
        assert review_claims(wire, SOURCE)["extractions"] == []


def test_old_wire_shape_is_offline_only():
    wire = payload()
    wire["extractions"][0].update(why_it_matters=None, what_happens_next=None)
    del wire["extractions"][0]["decision"]["action_text"]
    del wire["extractions"][0]["relevance"]["source_text"]
    assert review_claims(wire, SOURCE)["extractions"] == []
    assert review_claims(wire, SOURCE, legacy_evaluation=True)["extractions"]


@pytest.mark.parametrize("negative_scope", ["", " No building expansion is proposed."])
def test_identified_interior_project_is_discoverable_without_building_expansion(
    negative_scope,
):
    action = (
        "The first phase of renovations includes a kitchen, restroom facilities, office space and a multipurpose meeting area."
        + negative_scope
    )
    source = "SYNTHETIC APPLICATION. 5 Oak St. " + action
    wire = simple(
        source,
        "Interior renovations at 5 Oak St. are scheduled for review; no building expansion is proposed.",
    )
    item = wire["extractions"][0]
    item["parcel_references"] = [
        {"text": "5 Oak St.", "passage_ids": item["what_happened"]["passage_ids"]}
    ]
    item["relevance"].update(
        category="development", scope="redevelopment", source_text=action
    )
    result = hydrate_claims(wire, source)[0]
    assert result["discovery_eligible"]
    assert result["relevance_scope"] == "redevelopment"
    assert result["decision"] is None


@pytest.mark.parametrize(
    "excerpt",
    [
        "The first phase of renovations was completed in 2020 and includes a kitchen and office space.",
        "No renovations to the kitchen or office space are proposed.",
        "Routine renovations repair paint in the kitchen and office space.",
        "The neighboring project has renovations including a kitchen and office space.",
        "Permission to operate a center with a kitchen and office space.",
    ],
)
def test_interior_context_does_not_establish_a_current_physical_proposal(excerpt):
    source = "SYNTHETIC APPLICATION. 5 Oak St. " + excerpt
    wire = simple(source)
    item = wire["extractions"][0]
    item["parcel_references"] = [
        {"text": "5 Oak St.", "passage_ids": item["what_happened"]["passage_ids"]}
    ]
    item["relevance"].update(
        category="development", scope="redevelopment", source_text=excerpt
    )
    result = hydrate_claims(wire, source)[0]
    assert not result["discovery_eligible"]


@pytest.mark.parametrize(
    "scope", ["signalization upgrade", "traffic signal system upgrade"]
)
def test_signal_upgrade_procurement_retains_physical_scope_without_implying_completion(
    scope,
):
    source = f"SYNTHETIC AGENDA. Maple Avenue {scope} project: consider readvertising after no bids were received."
    wire = simple(source)
    item = wire["extractions"][0]
    item["project_reference"] = {
        "text": f"Maple Avenue {scope} project",
        "passage_ids": item["what_happened"]["passage_ids"],
    }
    item["relevance"].update(category="public_works", scope="capital_project")
    result = hydrate_claims(wire, source)[0]
    assert result["discovery_eligible"]
    assert result["relevance_scope"] == "capital_project"
    assert result["record_status"] == "scheduled" and result["decision"] is None


def test_model_rationale_cannot_turn_signal_timing_maintenance_into_capital_upgrade():
    source = (
        "SYNTHETIC AGENDA. Maple Avenue: routine traffic signal timing maintenance."
    )
    wire = simple(
        source, "The Maple Avenue traffic signal system upgrade is scheduled."
    )
    item = wire["extractions"][0]
    item["relevance"].update(category="public_works", scope="capital_project")
    result = hydrate_claims(wire, source)[0]
    assert not result["discovery_eligible"]


@pytest.mark.parametrize(
    "guessed_scope", ["new_construction", "expansion", "redevelopment"]
)
def test_formal_plan_remains_discoverable_after_unsupported_physical_scope_is_removed(
    guessed_scope,
):
    source = "SYNTHETIC AGENDA. Maple Commerce Center preliminary/final land development plan: review."
    wire = simple(source)
    item = wire["extractions"][0]
    item["project_reference"] = {
        "text": "Maple Commerce Center",
        "passage_ids": item["what_happened"]["passage_ids"],
    }
    item["relevance"].update(category="development", scope=guessed_scope)
    result = hydrate_claims(wire, source)[0]
    assert result["discovery_eligible"]
    assert result["relevance_scope"] == "plan_review"
    assert result["decision"] is None


def test_formal_plan_time_extension_does_not_establish_new_development_scope():
    source = "SYNTHETIC AGENDA. Time extension for Maple Commerce Center land development plan."
    wire = simple(source)
    item = wire["extractions"][0]
    item["project_reference"] = {
        "text": "Maple Commerce Center",
        "passage_ids": item["what_happened"]["passage_ids"],
    }
    item["relevance"].update(category="development", scope="new_construction")
    assert not hydrate_claims(wire, source)[0]["discovery_eligible"]


def test_neighbor_compliance_report_does_not_suppress_bess_policy():
    matter = "Proposed Battery Energy Storage System Ordinance."
    source = "SYNTHETIC AGENDA. " + matter + "\nAct 537 update: review compliance rate."
    wire = simple(source, "The BESS ordinance is scheduled for discussion.")
    item = wire["extractions"][0]
    item["relevance"].update(
        category="landuse_policy", scope="policy_change", source_text=matter
    )
    item["relevance"]["basis"]["text"] = "A proposed storage-system ordinance."
    result = hydrate_claims(wire, source)[0]
    assert result["matter_category"] == "landuse_policy"
    assert result["discovery_eligible"]
    assert details_for(result)["relevance_source_text"] == matter


@pytest.mark.parametrize(
    "matter,category,scope",
    [
        ("A variance for an inground pool.", "development", "new_construction"),
        (
            "A variance for an accessory garage in a commercial district.",
            "development",
            "new_construction",
        ),
        ("A 350 sf homeowner carport.", "development", "new_construction"),
        ("An accessory building setback variance.", "development", "new_construction"),
        (
            "Subdivision of 10 acres containing existing communication towers.",
            "development",
            "new_lots",
        ),
        (
            "Designation of one parcel as Agricultural Security Area.",
            "landuse_policy",
            "policy_change",
        ),
        (
            "A driveway slope modification for a single home.",
            "development",
            "new_construction",
        ),
        (
            "A material and equipment bid for routine road supplies.",
            "public_works",
            "capital_project",
        ),
    ],
)
def test_minor_or_administrative_matter_cannot_become_discovery(
    matter, category, scope
):
    source = "SYNTHETIC AGENDA. " + matter
    wire = simple(source, matter)
    item = wire["extractions"][0]
    item["relevance"].update(category=category, scope=scope, source_text=matter)
    item["relevance"]["basis"]["text"] = matter
    result = hydrate_claims(wire, source)[0]
    assert not result["discovery_eligible"]


@pytest.mark.parametrize(
    "matter,category,scope",
    [
        ("A proposed 73-unit apartment building.", "development", "new_construction"),
        (
            "Public bid for historical roof replacement.",
            "public_works",
            "capital_project",
        ),
        ("Sidewalk and ADA ramp construction.", "public_works", "capital_project"),
    ],
)
def test_substantive_construction_remains_discoverable(matter, category, scope):
    source = "SYNTHETIC AGENDA. " + matter
    wire = simple(source, matter)
    item = wire["extractions"][0]
    item["relevance"].update(category=category, scope=scope, source_text=matter)
    item["relevance"]["basis"]["text"] = matter
    assert hydrate_claims(wire, source)[0]["discovery_eligible"]


def test_milestone_paraphrase_reduced_to_exact_date_without_guessing_year():
    wire = payload()
    wire["extractions"][0]["milestones"][0]["text"] = (
        "The bid opening is scheduled for September 10, 2026."
    )
    result = hydrate_claims(wire, SOURCE)[0]
    assert result["milestones"][0]["text"] == "September 10, 2026"
    assert result["milestones"][0]["date"] == "2026-09-10"
    wire["extractions"][0]["milestones"][0]["text"] = "September 10, 2027"
    assert review_claims(wire, SOURCE)["extractions"] == []


def test_header_date_and_authority_are_added_as_their_own_evidence():
    header = "SYNTHETIC Pine Township Board of Supervisors. July 20, 2026.\n"
    action = "Board approved the proposed commercial expansion."
    source = header + ("Administrative padding. " * 80) + "\n" + action
    doc = passage_document(source)
    wire = simple(source, "The Board approved the proposed commercial expansion.")
    item = wire["extractions"][0]
    ids = [doc.passages[-1].passage_id]
    item["record_status"] = "decision"
    item["what_happened"]["passage_ids"] = ids
    item["relevance"]["basis"]["passage_ids"] = ids
    item["relevance"]["source_text"] = action
    item["event_date"] = {"text": "July 20, 2026", "passage_ids": ids}
    item["decision"] = dict(
        outcome="approved",
        scope="plan",
        authority="Pine Township Board of Supervisors",
        passage_ids=ids,
        action_text=action,
    )
    result = hydrate_claims(wire, source, meeting_date="2026-07-20")[0]
    assert result["event_date"] == "2026-07-20"
    assert any(
        "decision_authority" in s["fields"] and header.strip() in s["quote"]
        for s in result["evidence_spans"]
    )
    assert any(
        "event_date_text" in s["fields"] and header.strip() in s["quote"]
        for s in result["evidence_spans"]
    )


def test_footer_case_does_not_remove_legitimate_sibling():
    source = "SYNTHETIC AGENDA. Young Subdivision time extension. Next Conditional Use Case # CUH 2026-10."
    wire = simple(source, "Young Subdivision time extension is scheduled.")
    bad = deepcopy(wire["extractions"][0])
    bad["project_name"] = "CUH 2026-10"
    bad["application_ids"] = [
        {"text": "CUH 2026-10", "passage_ids": bad["what_happened"]["passage_ids"]}
    ]
    wire["extractions"].append(bad)
    assert review_claims(wire, source)["accepted_indices"] == [0]


@pytest.mark.parametrize(
    "name",
    [
        "Agricultural Security Area",
        "Shrewsbury Township Grant Project",
        "model ordinance pertaining to data centers",
    ],
)
def test_generic_policy_or_grant_is_not_named_identity(name):
    assert not distinctive_project_reference(name)


def test_typed_policy_id_is_scoped_to_municipality_not_generic_title():
    details = {
        "contract_version": 3,
        "matter_category": "landuse_policy",
        "application_ids": [],
        "project_reference": "Resolution 2026-04",
    }
    row = dict(
        body_name="Pine Township Board of Supervisors", extraction_details=details
    )
    aliases = project_aliases(row)
    assert len(aliases) == 1
    assert aliases[0].startswith("application|")
    details["project_reference"] = "Data Center Model Ordinance"
    assert project_aliases(row) == []


@pytest.mark.parametrize(
    "source",
    [
        "Historical Roof - Public Bid",
        "Named bridge work",
        "Pedestrian improvements",
        "Energy storage litigation update",
    ],
)
def test_capital_project_terms_reach_extraction(source):
    assert has_landuse_vocabulary(source)


def test_agenda_report_does_not_become_completed_update():
    source = "SYNTHETIC COUNCIL AGENDA. Engineer report: Main Street paving grant."
    wire = simple(source, "The engineer report included a Main Street paving grant.")
    item = wire["extractions"][0]
    item["record_status"] = "update"
    assert review_claims(wire, source)["extractions"] == []
    item["record_status"] = "scheduled"
    item["what_happened"]["text"] = (
        "The engineer report on the paving grant is scheduled."
    )
    assert review_claims(wire, source)["extractions"]


def test_conditions_with_abbreviations_do_not_hide_carried_vote():
    action = "Council moved to grant the variance at 1 N. Main St. subject to the engineer letter. Motion carried unanimously."
    source = "SYNTHETIC MINUTES. " + action
    wire = simple(source, "Council approved the variance with conditions.")
    item = wire["extractions"][0]
    item["record_status"] = "decision"
    item["decision"] = dict(
        outcome="approved",
        scope="variance",
        authority="Council",
        passage_ids=item["what_happened"]["passage_ids"],
        action_text=action,
    )
    assert review_claims(wire, source)["extractions"]


@pytest.mark.parametrize("invalid_optional_entity", [False, True])
def test_partial_projection_preserves_rejected_claims_for_operator_review(
    monkeypatch, invalid_optional_entity
):
    import importlib
    from types import SimpleNamespace
    from countyiq.lib.llm_harness import HarnessConfig, HarnessResult

    module = importlib.import_module("countyiq.assets.enrichment.proceeding_extraction")
    source = SOURCE.replace("TEST RECORD", "TEST SUBDIVISION RECORD")
    wire = payload(source)
    source_fingerprint = wire.pop("source_sha256")
    bad = deepcopy(wire["extractions"][0])
    bad["application_ids"][0]["text"] = "invented"
    wire["extractions"].append(bad)
    if invalid_optional_entity:
        wire["extractions"][0]["related_entities"] = [
            {
                "text": "Invented Engineering Company",
                "passage_ids": wire["extractions"][0]["what_happened"]["passage_ids"],
            }
        ]
    rows = [
        (
            1,
            "Pine Township Council",
            "2026-08-01",
            "council",
            "https://example.test/minutes.pdf",
            source,
            "hash",
        )
    ]

    class Database:
        def execute(self, sql, *args):
            return rows if sql == module.PENDING_PROCEEDINGS_QUERY else []

    calls = {}
    monkeypatch.setattr(
        module,
        "get_county_config",
        lambda: SimpleNamespace(
            name="York County", state="PA", municipality_websites=[]
        ),
    )
    monkeypatch.setattr(module, "authorize_source", lambda *a, **k: None)
    monkeypatch.setattr(module, "require_source_use", lambda *a, **k: None)
    monkeypatch.setattr(module, "municipality_source_key", lambda x: "pine")
    monkeypatch.setattr(
        module, "authorize_municipality_sources", lambda *a, **k: {"pine": None}
    )
    monkeypatch.setattr(module, "fetch_prior_pass_attempts", lambda *a, **k: {})
    monkeypatch.setattr(
        module,
        "resolve_pass_harness",
        lambda *a, **k: (
            HarnessConfig(model_path="test/model"),
            lambda *a, **k: HarnessResult(
                raw_output="synthetic", parsed=wire, success=True, metadata={}
            ),
        ),
    )
    monkeypatch.setattr(
        module,
        "PassItemBudget",
        lambda _: SimpleNamespace(
            mode="test", limit=1, claimed=1, claim=lambda *a, **k: True
        ),
    )
    monkeypatch.setattr(
        module,
        "record_validation_rejection",
        lambda *a, **k: calls.setdefault("rejection", k),
    )
    monkeypatch.setattr(
        module,
        "record_inference_decision",
        lambda *a, **k: (
            calls.setdefault("inference", k)
            and SimpleNamespace(accepted=True, inference_id=123)
        ),
    )
    monkeypatch.setattr(
        module,
        "_write_proceeding_extractions",
        lambda *a, **k: (
            calls.setdefault("projection", k) and (0, len(k["extractions"]))
        ),
    )
    monkeypatch.setattr(
        module, "_update_pass_status", lambda *a, **k: calls.setdefault("status", a)
    )
    monkeypatch.setattr(module, "check_error_budget", lambda *a, **k: None)
    log = SimpleNamespace(info=lambda *a: None, warning=lambda *a: None)
    result = module.proceeding_extraction.op.compute_fn.decorated_fn(
        SimpleNamespace(log=log, run_id="synthetic", op_config={}), Database()
    )
    assert len(calls["projection"]["extractions"]) == 1
    assert calls["inference"]["payload"]["model_claims"] == wire
    assert calls["inference"]["payload"]["source_sha256"] == source_fingerprint
    assert "source_sha256" not in wire
    assert calls["inference"]["payload"]["coverage"]["version"] == 1
    assert calls["inference"]["payload"]["citation_repairs"] == []
    fields = calls["inference"]["payload"]["field_rejections"]
    assert len(fields) == int(invalid_optional_entity)
    assert result.metadata["withheld_entity_claims"].value == int(
        invalid_optional_entity
    )
    if invalid_optional_entity:
        assert "Invented Engineering Company" in str(fields)
        assert calls["projection"]["extractions"][0]["related_entities"] == []
        assert "field_rejections" in calls["status"][-1]
    assert calls["inference"]["payload"]["rejected_items"][0]["index"] == 1
    assert "item 1" in calls["rejection"]["errors"][0]
    assert calls["status"][2] == "complete"
    assert "quarantined_items" in calls["status"][-1]
    assert result.metadata["partial_documents"].value == 1
    assert result.metadata["quarantined_items"].value == 1


def test_conflicting_policy_reference_cannot_alias_two_resolutions():
    source = SOURCE + " Resolution 2026-18 and Resolution 2026-19."
    wire = payload(source)
    item = wire["extractions"][0]
    ids = item["what_happened"]["passage_ids"]
    item["application_ids"] = [{"text": "Resolution 2026-18", "passage_ids": ids}]
    item["project_reference"] = {"text": "Resolution 2026-19", "passage_ids": ids}
    value = hydrate_claims(wire, source)[0]
    assert value["identity_status"] == "needs_review"
    assert project_aliases({"extraction_details": details_for(value)}) == []


def test_substantive_draft_policy_remains_discoverable_with_procedural_scope():
    action = "Council approved edits to the draft data-center ordinance and submitted it for review."
    source = "SYNTHETIC MINUTES. " + action
    wire = simple(source, action)
    item = wire["extractions"][0]
    item["record_status"] = "decision"
    item["decision"] = dict(
        outcome="approved",
        scope="procedural",
        authority="Council",
        passage_ids=item["what_happened"]["passage_ids"],
        action_text=action,
    )
    item["relevance"].update(
        category="landuse_policy", scope="policy_change", source_text=action
    )
    result = hydrate_claims(wire, source)[0]
    assert result["discovery_eligible"]
    assert result["decision_scope"] == "procedural"


def test_plan_modification_cannot_set_whole_plan_approval():
    action = "Council approved the Subdivision and Land Development Modification Request for sidewalk location."
    source = "SYNTHETIC MINUTES. " + action
    wire = simple(source, action)
    item = wire["extractions"][0]
    item["record_status"] = "decision"
    item["decision"] = dict(
        outcome="approved",
        scope="plan",
        authority="Council",
        passage_ids=item["what_happened"]["passage_ids"],
        action_text=action,
    )
    result = hydrate_claims(wire, source)[0]
    assert result["decision_scope"] == "procedural"


def test_header_can_supply_authority_for_named_members_carried_vote():
    header = "SYNTHETIC Pine Township Board of Supervisors. July 20, 2026.\n"
    action = "Motion by Chairman Cedar to approve the final plan. All members voted aye; motion carried."
    source = header + ("Administrative padding. " * 80) + "\n" + action
    wire = simple(source, "The Board approved the final plan.")
    item = wire["extractions"][0]
    ids = [passage_document(source).passages[-1].passage_id]
    item["what_happened"]["passage_ids"] = ids
    item["relevance"]["basis"]["passage_ids"] = ids
    item["relevance"]["source_text"] = action
    item["record_status"] = "decision"
    item["decision"] = dict(
        outcome="approved",
        scope="plan",
        authority="Pine Township Board of Supervisors",
        passage_ids=ids,
        action_text=action,
    )
    assert (
        hydrate_claims(wire, source)[0]["decision_authority"]
        == "Pine Township Board of Supervisors"
    )
    # The header cannot lend its authority to a different body's action.
    other_action = "Zoning Hearing Board approved the final plan."
    other_source = source + "\n" + other_action
    wire["source_sha256"] = passage_document(other_source).source_sha256
    item["decision"]["action_text"] = other_action
    assert review_claims(wire, other_source)["extractions"] == []
