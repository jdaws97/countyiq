"""Synthetic adversarial cases for consequential Pass 0 boundaries."""
from copy import deepcopy
import pytest
from countyiq.lib.proceeding_semantics import decision_errors, scheduled_action_errors, relevance_projection
from countyiq.lib.proceeding_claims import hydrate_claims, review_claims, passage_document
from countyiq.lib.proceeding_contract import details_for
from tests.test_proceeding_item_review import simple


@pytest.mark.parametrize("vote,allowed", [("2/0", True), ("2-0", True), ("0/2", False), ("2/2", False)])
def test_recorded_motion_result_respects_the_vote(vote, allowed):
    decision = {"authority": "Council", "outcome": "approved", "scope": "plan"}
    action = f"Motion to approve the final plan by Cedar, second by Ash, vote {vote}."
    assert (not decision_errors(decision, action)) == allowed


@pytest.mark.parametrize("action", [
    "Council made a motion to deny the plan. Motion carried.",
    "Council made a motion to table the plan. Motion carried.",
    "Motion to approve the plan. Vote 0/2. Motion carried.",
    "The plan was not approved.",
    "Motion to approve the plan. Motion did not pass.",
    "Motion to approve the plan. Council discussed the next plan. Motion carried.",
])
def test_carried_or_approval_words_do_not_override_the_actual_motion(action):
    assert decision_errors({"authority": "Council", "outcome": "approved", "scope": "plan"}, action)


@pytest.mark.parametrize("summary,allowed", [
    ("A variance is scheduled to add a fourth unit to a currently approved three-unit conversion.", True),
    ("The previously approved plan is scheduled for a new variance hearing.", True),
    ("Council previously approved the plan.", False),
    ("The Board has been approved to proceed.", False),
    ("The Council approved the proposal.", False),
])
def test_historical_modifier_is_distinct_from_completed_action(summary, allowed):
    assert bool(scheduled_action_errors(summary)) != allowed


def decision_fixture(action, *, scope="procedural", outcome="approved"):
    header = "SYNTHETIC Pine Township Planning Commission.\n"
    source = header + "Administrative material. " * 90 + "\n" + action
    wire = simple(source, action)
    item = wire["extractions"][0]
    ids = [p.passage_id for p in passage_document(source).passages if action in p.text]
    assert ids
    item["what_happened"]["passage_ids"] = ids
    item["relevance"]["basis"]["passage_ids"] = ids
    item["relevance"]["source_text"] = action
    item["record_status"] = "decision"
    item["decision"] = dict(authority="Planning Commission", outcome=outcome, scope=scope,
                            action_text=action, passage_ids=ids)
    return source, wire


def test_referral_recipient_cannot_steal_deciding_body():
    source, wire = decision_fixture("The draft be forwarded to the Board of Supervisors for review. Motion carried.")
    assert hydrate_claims(wire, source)[0]["decision_authority"] == "Planning Commission"


@pytest.mark.parametrize("body", ["Board of Supervisors", "Zoning Hearing Board", "County Planning Commission", "Court"])
def test_header_never_lends_authority_to_a_different_actor(body):
    source, wire = decision_fixture(f"{body} approved the proposed ordinance.")
    assert review_claims(wire, source)["extractions"] == []


def test_abbreviated_actor_and_carried_vote_can_use_header():
    source, wire = decision_fixture("PC voted to table the draft. Vote carried unanimously.", scope="ordinance", outcome="tabled")
    assert hydrate_claims(wire, source)[0]["decision"] == "tabled"


def test_unsupported_optional_entity_is_withheld_and_audited():
    source = "SYNTHETIC AGENDA. YCPC comments on a proposed apartment building."
    wire = simple(source, "A proposed apartment building is scheduled.")
    item = wire["extractions"][0]
    item["related_entities"] = [{"text": "York County Planning Commission",
                                 "passage_ids": item["what_happened"]["passage_ids"]}]
    original = deepcopy(wire)
    reviewed = review_claims(wire, source)
    assert len(reviewed["extractions"]) == 1
    assert reviewed["extractions"][0]["related_entities"] == []
    assert reviewed["field_rejections"][0]["claim"] == original["extractions"][0]["related_entities"][0]
    assert wire == original
    # Critical identity cannot use the optional-name exception.
    item["applicant_name"] = item["related_entities"][0]
    assert review_claims(wire, source)["extractions"] == []


def test_unknown_passage_does_not_use_optional_entity_exception():
    source = "SYNTHETIC AGENDA. Proposed apartment building."
    wire = simple(source, source)
    wire["extractions"][0]["related_entities"] = [{"text": "YCPC", "passage_ids": ["unknown"]}]
    assert review_claims(wire, source)["extractions"] == []


def test_scope_context_preserves_source_sentence_and_stops_at_neighbor():
    first = "Seven-year Agricultural Security Area review removes 10 acres across the township."
    second = "A separate Agricultural Security Area designation for one parcel."
    source = "SYNTHETIC AGENDA. " + first + " " + second
    wire = simple(source, "The township review is scheduled.")
    item = wire["extractions"][0]
    item["relevance"].update(category="minor_property", scope="property_relief", source_text="removes 10 acres")
    review = hydrate_claims(wire, source)[0]
    assert review["discovery_eligible"]
    assert second not in review["relevance_context_text"]
    assert details_for(review)["relevance_context_text"] in source
    item["relevance"]["source_text"] = second
    item["what_happened"]["text"] = "A separate one-parcel designation is scheduled."
    assert not hydrate_claims(wire, source)[0]["discovery_eligible"]


def test_existing_tower_summary_prevents_positive_scope_from_selective_excerpt():
    assert not relevance_projection("development", "new_lots", "Creating a building lot.",
        "Subdividing 10 acres from a parcel.", summary="An existing tower is on the proposed lot.")[2]


@pytest.mark.parametrize("excerpt,allowed", [
    ("A 1.2-acre proposed new lot with 10 acres remaining.", False),
    ("A new building lot for a single-family detached dwelling.", True),
    ("A proposed five-lot subdivision.", True),
])
def test_new_lot_requires_material_scope(excerpt, allowed):
    assert relevance_projection("development", "new_lots", excerpt, excerpt)[2] is allowed


def test_tabled_hotel_remains_discoverable_without_claiming_approval():
    action = "PC made a motion to table the plan for construction of a hotel. Motion carried."
    source, wire = decision_fixture(action, scope="procedural", outcome="tabled")
    wire["extractions"][0]["relevance"].update(category="development", scope="new_construction")
    value = hydrate_claims(wire, source)[0]
    assert value["discovery_eligible"]
    assert value["decision"] == "tabled"


def test_deferred_case_is_scheduled_and_contradictory_terminal_prose_is_rejected():
    action = "WILL BE IN AUGUST MEETINGS-MORE DETAILS NEEDED"
    source = "SYNTHETIC AGENDA. ZHB 2026-09: " + action
    wire = simple(source, "The case is identified for August because more details are needed.")
    item = wire["extractions"][0]
    item["record_status"] = "removed"
    item["what_happens_next"] = {"text": action, "passage_ids": item["what_happened"]["passage_ids"]}
    value = hydrate_claims(wire, source)[0]
    assert value["record_status"] == "scheduled"
    assert value["event_tags"] == ["application"]
    item["what_happened"]["text"] = "The applicant withdrew the application."
    assert review_claims(wire, source)["extractions"] == []


def test_actual_removal_is_preserved():
    source = "SYNTHETIC MINUTES. Council voted to remove Cedar Plan from future agendas."
    wire = simple(source, source)
    wire["extractions"][0]["record_status"] = "removed"
    value = hydrate_claims(wire, source)[0]
    assert value["record_status"] == "removed"
    assert not value["discovery_eligible"]


def test_tennis_court_is_not_a_judicial_deciding_body():
    decision = {"authority": "Board of Supervisors", "scope": "contract", "outcome": "approved"}
    action = "Motion to approve the road agreement for the tennis court, by Cedar second by Ash, vote 2/0."
    assert not decision_errors(decision, action)


def test_court_action_cannot_be_attributed_to_council():
    assert decision_errors({"authority": "Council", "scope": "plan", "outcome": "denied"},
                           "Court denied the appeal.")


@pytest.mark.parametrize("outcome,word", [("approved", "approved"), ("denied", "denied"),
                                         ("tabled", "tabled"), ("continued", "continued")])
def test_explicit_negation_never_becomes_completed_outcome(outcome, word):
    assert decision_errors({"authority": "Council", "scope": "plan", "outcome": outcome},
                           f"The plan was not {word}.")


@pytest.mark.parametrize("outcome,word", [("tabled", "table"), ("continued", "continue")])
def test_failed_procedural_motion_does_not_change_case_state(outcome, word):
    assert decision_errors({"authority": "Council", "scope": "plan", "outcome": outcome},
                           f"Motion to {word} the plan. Vote 0/2.")


def test_second_application_vote_cannot_complete_first_application_motion():
    assert decision_errors({"authority": "Council", "scope": "plan", "outcome": "approved"},
        "Motion to approve Cedar Plan. No result recorded. Motion to approve Birch Plan. Vote 2/0.")


@pytest.mark.parametrize("yes,no", [(y,n) for y in range(5) for n in range(5)])
def test_numeric_vote_variants_do_not_invert_majority(yes, no):
    for separator in ["/", "-", " / ", " - "]:
        errors = decision_errors({"authority": "Council", "scope": "plan", "outcome": "approved"},
            f"Motion to approve Cedar Plan, seconded by Ash. Vote {yes}{separator}{no}.")
        assert bool(errors) == (yes <= no)


def test_future_pc_meeting_or_law_firm_suffix_is_not_the_deciding_actor():
    decision = {"authority": "Council", "scope": "procedural", "outcome": "approved"}
    action = "Council approved sending the draft to a future PC meeting with comments from Cedar Law, PC."
    assert not decision_errors(decision, action)


def test_neighbor_line_cannot_promote_single_parcel_to_municipal_policy():
    source = ("SYNTHETIC AGENDA\nSeven-year Agricultural Security Area review\n"
              "Separate parcel designation: 10 acres to be added to Agricultural Security Area\n")
    wire = simple(source, "Separate parcel designation is scheduled.")
    wire["extractions"][0]["relevance"].update(category="minor_property", scope="property_relief",
                                               source_text="10 acres to be added")
    assert not hydrate_claims(wire, source)[0]["discovery_eligible"]


@pytest.mark.parametrize("source", [
    "Ordinance reducing the number of members of the Planning Commission.",
    "Draft homeless encampment ordinance for police enforcement.",
    "Truck traffic study recommending axle and weight restrictions.",
])
def test_governance_and_behavior_rules_are_context_not_development_policy(source):
    assert relevance_projection("landuse_policy", "policy_change", source, source) == (
        "context_only", "unknown", False)


@pytest.mark.parametrize("source,eligible", [
    ("Setback relief to add an elevator addition.", False),
    ("New building with an elevator addition.", True),
    ("A 20,000-square-foot office addition including an elevator addition.", True),
])
def test_accessibility_only_work_does_not_hide_independent_building_expansion(source, eligible):
    assert relevance_projection("development", "expansion", source, source)[2] is eligible


@pytest.mark.parametrize("action", [
    "Motion to increase the surety for sidewalks and fencing. Vote 2/0.",
    "Council approved the developer's agreement. Motion carried.",
    "Council adopted the declaration of taking for roads, streets or alleys.",
])
def test_financial_action_remains_history_despite_physical_improvements_in_rationale(action):
    assert not relevance_projection(
        "public_works", "capital_project", "Physical improvements to roads and sidewalks.",
        "sidewalks and fencing", decision_action=action)[2]


def test_pending_agreement_does_not_create_a_capital_opportunity():
    assert not relevance_projection("public_works", "capital_project", "Road improvements.",
        "Cedar Way improvements", summary="Unsigned agreements were sent for signatures.")[2]


@pytest.mark.parametrize("action,source", [
    ("Council awarded the roof construction contract. Motion carried.", "Roof replacement construction."),
    ("Council accepted a grant for the pump station. Motion carried.", "Grant for the Cedar Pump Station."),
])
def test_real_construction_contracts_and_capital_grants_remain_useful(action, source):
    assert relevance_projection("public_works", "capital_project", source, source, decision_action=action)[2]


def test_maintenance_code_governance_does_not_become_landuse_policy():
    source = "Review of the International Property Maintenance Code and Quality of Life Ordinances."
    assert not relevance_projection("landuse_policy", "policy_change", source, source)[2]


def test_completed_advisory_referral_preserves_valid_vote_and_original_claim():
    action = "PC moved to forward the draft to the Board of Supervisors for review. Vote carried unanimously."
    source, wire = decision_fixture(action)
    wire["extractions"][0]["record_status"] = "recommendation"
    original = deepcopy(wire)
    reviewed = hydrate_claims(wire, source)[0]
    assert reviewed["record_status"] == "decision"
    assert reviewed["decision_scope"] == "procedural"
    assert reviewed["decision_authority"] == "Planning Commission"
    assert "advisory procedural vote" in details_for(reviewed)["status_projection_reason"]
    assert wire == original


@pytest.mark.parametrize("failure", ["failed", "invented", "ordinance", "scheduled"])
def test_advisory_normalization_cannot_supply_a_missing_or_substantive_approval(failure):
    action = "PC moved to forward the draft to the Board of Supervisors for review. Vote carried unanimously."
    source, wire = decision_fixture(action)
    item = wire["extractions"][0]
    item["record_status"] = "recommendation"
    if failure == "failed":
        source, wire = decision_fixture(action.replace("Vote carried unanimously.", "Vote 0/2."))
        wire["extractions"][0]["record_status"] = "recommendation"
    elif failure == "invented":
        item["decision"]["action_text"] = action.replace("the draft", "the invented draft")
    elif failure == "ordinance":
        item["decision"]["scope"] = "ordinance"
    else:
        item["record_status"] = "scheduled"
    assert review_claims(wire, source)["extractions"] == []


@pytest.mark.parametrize("category,scope,source", [
    ("development", "new_construction", "Cedar Homes Lot 7 & 8"),
    ("development", "new_construction", "LD-26-15 School District Turf Field, 8 Maple Lane"),
    ("public_works", "capital_project", "Small Water & Sewer grant submitted on 12/21/2022"),
    ("public_works", "capital_project", "Oak Glen issue with water main, removal of trees"),
    ("public_works", "capital_project", "Road work: Approve Change Order #2 for Contract #1"),
    ("landuse_policy", "policy_change", "Updated Nuisance Ordinance"),
])
def test_opportunity_requires_scope_beyond_a_model_label(category, scope, source):
    assert not relevance_projection(category, scope, "A major new construction opportunity.", source)[2]


@pytest.mark.parametrize("category,scope,source", [
    ("development", "new_construction", "A proposed six-home development."),
    ("development", "new_construction", "New warehouse construction."),
    ("public_works", "capital_project", "Multimodal grant award for Cedar Street & Maple Lane: Updated costs"),
    ("public_works", "capital_project", "A grant for Cedar Business Park pump station"),
    ("public_works", "capital_project", "North Cedar Street project needs to relocate water lines."),
    ("public_works", "capital_project", "Street Improvements: update on Cedar Street"),
    ("landuse_policy", "policy_change", "Amendment to zoning ordinance setback requirements."),
    ("landuse_policy", "policy_change", "Hardship Housing review of Section 403E."),
])
def test_grounded_opportunities_survive_conservative_qualification(category, scope, source):
    assert relevance_projection(category, scope, source, source)[2]


def test_new_in_a_street_name_does_not_establish_new_construction():
    source = "LD-26-15 School District Turf Field, 700 New School Lane"
    assert not relevance_projection("development", "new_construction", source, source)[2]


@pytest.mark.parametrize("category,scope,source", [
    ("development", "new_construction", "Six-home plan. Motion to approve failed."),
    ("landuse_policy", "policy_change", "Proposed Redevelopment Overlay"),
    ("landuse_policy", "policy_change", "From Commercial Shopping District to Residential High Density District"),
    ("public_works", "capital_project", "Cedar Road intersection and Exit 7 improvements"),
])
def test_explicit_scope_can_be_brief_without_inventing_a_project(category, scope, source):
    assert relevance_projection(category, scope, source, source)[2]


def test_numbered_policy_heading_belongs_only_to_its_lettered_child():
    source = ("SYNTHETIC AGENDA\n3.03 Comprehensive Plan:\n"
              "a. Consultant Review and Discussion Re: Final Scope of Work\n"
              "3.04 Separate property matter: consultant review.\n")
    wire = simple(source, "Consultant review of the comprehensive plan is scheduled.")
    item = wire["extractions"][0]
    item["relevance"].update(category="landuse_policy", scope="policy_change",
                             source_text="Consultant Review and Discussion Re: Final Scope of Work")
    value = hydrate_claims(wire, source)[0]
    assert value["discovery_eligible"]
    assert "3.03 Comprehensive Plan:" in value["relevance_context_text"]
    assert "3.04" not in value["relevance_context_text"]
    item["relevance"]["source_text"] = "Separate property matter: consultant review."
    assert not hydrate_claims(wire, source)[0]["discovery_eligible"]


@pytest.mark.parametrize("category,scope,source", [
    ("landuse_policy", "policy_change", "Chapter X - Future Land Use Plan"),
    ("landuse_policy", "policy_change", "Revisions to ZO Sections 203 and 711 (Wireless Communications Facilities)"),
    ("public_works", "capital_project", "Stormwater restoration project at Cedar Heights."),
    ("public_works", "capital_project", "Completed the base map for Cedar Road crosswalk and working on permitting."),
    ("development", "expansion", "Discussion of the landfill plan to increase in height."),
])
def test_source_supported_policy_and_infrastructure_terms(category, scope, source):
    assert relevance_projection(category, scope, source, source)[2]


def test_numbered_parent_heading_across_passage_boundary_keeps_exact_evidence():
    excerpt = "Consultant Review and Discussion Re: Final Scope of Work"
    source = ("SYNTHETIC AGENDA\n" + "Administrative padding. " * 47
              + "\n3.03 Comprehensive Plan:\na. " + excerpt + "\n"
              + "4. Other Business\n" + "Administrative padding. " * 60)
    doc = passage_document(source)
    child = next(p for p in doc.passages if excerpt in p.text)
    parent = next(p for p in doc.passages if "3.03 Comprehensive Plan:" in p.text)
    assert child.passage_id != parent.passage_id
    wire = simple(source, "Consultant review of the comprehensive plan is scheduled.")
    item = wire["extractions"][0]
    item["what_happened"]["passage_ids"] = [child.passage_id]
    item["relevance"]["basis"]["passage_ids"] = [child.passage_id]
    item["relevance"].update(category="landuse_policy", scope="policy_change", source_text=excerpt)
    value = hydrate_claims(wire, source)[0]
    assert value["discovery_eligible"]
    assert "3.03 Comprehensive Plan:" in value["relevance_context_text"]
    assert "4. Other Business" not in value["relevance_context_text"]
    for span in value["evidence_spans"]:
        assert span["quote"] == source[span["start"]:span["end"]]


@pytest.mark.parametrize('authority,header,action,allowed', [
    ('Board', 'Pine Township BOARD OF SUPERVISORS', 'Motion to approve the easement. All members voted aye.', True),
    ('Board', 'Pine Township BOARD OF SUPERVISORS', 'Planning Commission approved the plan.', False),
    ('Board', 'Board of Supervisors and Zoning Hearing Board', 'Motion carried.', False),
    ('Board', 'Pine School Board', 'Motion carried.', False),
])
def test_short_board_authority_requires_one_unambiguous_meeting_body(authority, header, action, allowed):
    from countyiq.lib.proceeding_semantics import header_authority_supported
    assert header_authority_supported(authority, action, header) is allowed


@pytest.mark.parametrize('matter,identity,eligible', [
    ('Final Land Development Plan – 674 Cedar Road', True, True),
    ('Final Revised Land Development Plan – Cedar Village Phase 1 #26-1009', True, True),
    ('Land Development Plan', False, False),
    ('Bond reduction for the land development plan at 674 Cedar Road', True, False),
    ('Time extension for the land development plan at 674 Cedar Road', True, False),
    ('Minor subdivision and land development plan at 674 Cedar Road', True, False),
])
def test_identified_plan_review_remains_explicitly_unknown_scope(matter, identity, eligible):
    result = relevance_projection('context_only', 'unknown', matter, matter, source_identity=identity)
    assert result[2] is eligible
    if eligible:
        assert result[:2] == ('development', 'plan_review')


def test_model_plan_review_label_cannot_supply_missing_scope_or_identity():
    assert not relevance_projection('development', 'plan_review', 'A development plan.',
        'Other business.', source_identity=True)[2]
    assert not relevance_projection('development', 'plan_review', 'Land Development Plan',
        'Land Development Plan', source_identity=False)[2]


@pytest.mark.parametrize('matter,eligible', [
    ('Payment Application No. 5 for Pine Township WWTP Generator Upgrade.', True),
    ('Electrical contract for the Wastewater Treatment Plant UV Upgrade.', True),
    ('Award the Cedar Park Phase II Project to the lowest responsible bidder.', True),
    ('Traffic Study for a potential crosswalk on Cedar Drive.', True),
    ('Cedar Street Ext. – waiting for PennDOT to execute the project.', True),
    ('Payment Application No. 1 for the 2026 Road Program.', False),
    ('Storm Sewer – preconstruction meeting held, work starts the week of the 19th.', False),
    ('Upgrade the municipal website.', False),
    ('Park naming ceremony.', False),
])
def test_capital_scope_is_distinct_from_generic_financial_or_routine_work(matter, eligible):
    assert relevance_projection('public_works', 'capital_project', matter, matter)[2] is eligible


def test_bid_authorization_keeps_capital_project_discoverable_without_plan_approval():
    action = 'Council approved advertising bids for the Cedar Street water main replacement. Motion carried.'
    source = 'SYNTHETIC MINUTES. ' + action
    wire = simple(source, action)
    item = wire['extractions'][0]
    item.update(record_status='decision', decision=dict(authority='Council', outcome='approved',
        scope='procedural', action_text=action, passage_ids=item['what_happened']['passage_ids']))
    item['relevance'].update(category='public_works', scope='capital_project', source_text=action)
    result = hydrate_claims(wire, source)[0]
    assert result['discovery_eligible']
    assert result['decision_scope'] == 'procedural'


@pytest.mark.parametrize('action', ['Motion carried: 6-0', 'Motion carried.', 'Vote passed unanimously.', 'Vote: 2/0'])
def test_bare_vote_cannot_support_an_unidentified_action(action):
    assert decision_errors(dict(authority='Council', outcome='approved', scope='procedural'), action)


def test_bare_vote_in_same_passage_cannot_borrow_the_neighboring_action():
    source = 'SYNTHETIC MINUTES. Council discussed Cedar Plan. Motion carried: 6-0. Council approved Birch Plan.'
    wire = simple(source, 'Council approved Cedar Plan.')
    item = wire['extractions'][0]
    item.update(record_status='decision', decision=dict(authority='Council', outcome='approved', scope='plan',
        action_text='Motion carried: 6-0', passage_ids=item['what_happened']['passage_ids']))
    assert review_claims(wire, source)['extractions'] == []


@pytest.mark.parametrize('text,expected', [('September 22 Planning Commission Meeting', 'other'), ('Public hearing at the September 22 Council meeting', 'hearing')])
def test_meeting_milestone_does_not_invent_public_hearing(text, expected):
    source = 'SYNTHETIC AGENDA. ' + text
    wire = simple(source, 'The item is scheduled.')
    wire['extractions'][0]['milestones'] = [dict(kind='hearing', text=text,
        passage_ids=wire['extractions'][0]['what_happened']['passage_ids'])]
    result = hydrate_claims(wire, source)[0]
    assert result['milestones'][0]['kind'] == expected
    assert result['milestones'][0]['text'] == text
    assert result['milestones'][0]['date'] is None
