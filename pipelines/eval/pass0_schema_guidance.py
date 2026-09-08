"""Experimental field-local guidance without changing the extraction wire format."""

from copy import deepcopy

TERMINOLOGY_GUIDANCE = """
Interpret category labels using any definition supplied with the claim; the source need not literally contain the category label. A modification of a subdivision or land-development ordinance requirement belongs to a waiver category that includes modifications. Names of code provisions within that request identify the requirements being modified: a provision called Preliminary Plan does not turn the requirement-modification request into approval of the development plan. This differs from an action approving an amended development plan itself. Likewise, authorization or a resolution to apply for a grant establishes an application action, not a grant award by the funding body.
"""


def annotated_schema(schema: dict) -> dict:
    result = deepcopy(schema)
    definitions = result["$defs"]
    matter = definitions["matter"]["properties"]
    matter["title"]["description"] = (
        "Copy a concise, contiguous subject label from the numbered source, "
        "preserving its abbreviations. Inventory display titles are generated "
        "hints, not source quotations. Do not append a noncontiguous action label."
    )
    definitions["identifier"]["properties"]["kind"]["description"] = (
        "parcel means an explicit tax-parcel/PIDN reference. Subdivision lot labels "
        "and counts of lots are not parcel IDs. project requires a distinctive "
        "project name, not a street fragment, person or generic matter heading."
    )
    definitions["participant"]["properties"]["role"]["description"] = (
        "Use a known role only when the quoted source states that relationship. "
        "A named plan does not establish applicant or owner; a bill does not "
        "establish ownership or development. Otherwise use unknown."
    )
    definitions["participant"]["description"] = (
        "One person or one organization per record. Keep a representative's "
        "personal name separate from their employer or affiliated firm. "
        "Preserve relevant named firms separately with unknown role when "
        "the source does not explicitly state their project relationship."
    )
    matter["participants"]["description"] = (
        "People and organizations that are parties to this matter, including "
        "named agreement counterparties. Exclude municipal staff, reviewers "
        "and motion makers acting in their official capacity; consult the "
        "document's attendance and staff introductions to identify them."
    )
    matter["conditions"]["description"] = (
        "Preserve EVERY material requirement, undertaking, prerequisite and "
        "action constraint, including contractor promises and requirements "
        "for proposed or tabled plans. Include submissions, signatures, service "
        "proof, studies, fees, deadlines, spending limits and reporting duties. "
        "Retain the complete if/when trigger, responsible party and whether "
        "the obligation is proposed, current or historical. Waiting for a "
        "permit or external approval is a pending prerequisite; retain that "
        "condition even when it appears in a later progress report. A table heading "
        "alone is not a condition. Empty only when none are stated."
    )
    matter["summary"]["properties"]["excerpts"]["description"] = (
        "Preserve this matter's full action and requirements. Split excerpts to "
        "exclude separately inventoried work or policy, even inside its report."
    )
    definitions["location"]["properties"]["kind"]["description"] = (
        "intersection requires roads meeting at a junction. A work segment from "
        "one road to another is not an intersection; record its endpoint streets "
        "separately as street mentions."
    )
    definitions["location"]["properties"]["text"]["description"] = (
        "For street, identify one road per record, not a list of distinct roads. "
        "When distinct roads share a suffix in the source, preserve each "
        "literal name fragment without inventing an expanded suffix."
    )
    definitions["decision"]["properties"]["scope"]["description"] = (
        "Classify the actual object of the decision. grant_application is "
        "action on a grant application; funding_award requires an award or "
        "allocation of funds. reconsideration is whether to reopen or "
        "entertain a revised submission, not the resulting plan or waiver "
        "decision. legal_agreement includes approving a grant agreement or "
        "authorizing execution of its documents; calling a signatory the "
        "designated applicant does not turn agreement execution into submission "
        "of an application. A requirement modification is waiver, not plan approval."
    )
    definitions["relevance"]["properties"]["scope"]["description"] = (
        "Physical scope must be stated. A named public project, contractor, "
        "final payment or completed-project report alone does not describe "
        "capital work: use project_milestone when that physical scope is "
        "unstated. capital_project requires described physical construction, "
        "removal, replacement, rehabilitation or upgrade. A subdivision, "
        "reverse subdivision, lot consolidation or lot add-on with no stated "
        "new building lots is subdivision_only. plan_review describes a land "
        "development plan whose physical development scope is unstated."
    )
    matter["milestones"]["description"] = (
        "Preserve stated deadlines and expiration dates, including dates "
        "labeled EXP, with their actual purpose. An extension table may state "
        "both an existing expiration and its replacement: preserve both dates "
        "with their source evidence. Preserve relative triggers. "
        "Resolution numbers and dates of historical review memos are not "
        "project deadlines."
    )
    matter["conflicts"]["description"] = (
        "Preserve unresolved malformed dates and incompatible date statements, "
        "including an upcoming hearing predating the document header. Cite both "
        "statements; do not silently repair or choose a date."
    )
    return result
