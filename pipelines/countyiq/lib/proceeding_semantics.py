"""Deterministic counterexamples on item-specific source evidence.

These checks do not replace a semantic release evaluation. Never use neighboring
agenda items or votes as the evidence for the current claim.
"""
import re


def scheduled_action_errors(summary):
    text = str(summary or "")
    # Remove only explicit prospective/passive prerequisites, not past actions.
    # An attributive historical approval describes the existing use, not the
    # scheduled request's outcome ("a currently approved three-unit conversion").
    text = re.sub(r"\b(a|an|the|its)\s+(?:currently|previously|already)\s+(?:approved|reviewed|discussed)\s+",
                  r"\1 existing ", text, flags=re.I)
    prospective = re.sub(
        r"\b(?:be|been)\s+(?:submitted\s+and\s+)?(?:approved|denied|considered|held|voted on|reviewed|discussed)\b",
        "", text, flags=re.I)
    # A past perfect action remains completed; it is not prospective.
    if re.search(r"\b(?:has|had|have)\s+been\s+(?:approved|denied|considered|held|reviewed|discussed)\b", text, re.I):
        return ["scheduled item uses completed-action wording"]
    if re.search(r"\b(?:held|considered|approved|denied|voted|reviewed|discussed)\b", prospective, re.I):
        return ["scheduled item uses completed-action wording"]
    return []


_BODY = re.compile(r"\b(?:County Planning Commission|YCPC|Planning Commission|PC|"
                   r"Zoning Hearing Board|ZHB|Board of Supervisors|BOS|Council|"
                   r"Court(?=\s+(?:upheld|ruled|ordered|approved|denied|rejected)))\b", re.I)


def _body_kind(name):
    value = name.casefold()
    return {"pc": "planning commission", "ycpc": "county planning commission",
            "bos": "board of supervisors", "zhb": "zoning hearing board"}.get(value, value)


def deciding_bodies(action):
    """Recognize an actor's action, not every organization named in the excerpt."""
    actors = set()
    active = r"\s+(?:(?:members|has|had|have|unanimously|formally)\s+)*(?:approved|denied|adopted|enacted|granted|voted|tabled|continued|recommended|decided|moved|made|motion|upheld|ruled|ordered|rejected)\b"
    for m in _BODY.finditer(action):
        before, after = action[:m.start()], action[m.end():]
        passive = re.search(r"(?:approved|denied|adopted|granted|tabled|continued)\s+by\s+(?:the\s+)?$", before, re.I)
        if re.match(active, after, re.I) or passive:
            actors.add(_body_kind(m[0]))
    return actors


def authority_compatible(authority, action):
    body = _BODY.search(authority) or re.search(r"\bCourt\b", authority, re.I)
    actors = deciding_bodies(action)
    return bool(body) and (not actors or actors == {_body_kind(body[0])})


def recorded_vote(action):
    """Return the recorded motion result, not an inferred result of discussion."""
    scores = re.findall(r"\bvote(?:d)?(?:\s+(?:on the motion|was|of))?\s*:?\s*(\d{1,2})\s*[-/]\s*(\d{1,2})\b",
                        action, re.I)
    if scores:
        outcomes = {int(yes) > int(no) for yes, no in scores}
        # Conflicting vote totals cannot certify one action.
        return outcomes.pop() if len(outcomes) == 1 else None
    if re.search(r"\b(?:motion|vote)\s+(?:failed|defeated)|motion did not (?:carry|pass)|"
                 r"\b(?:motion|vote)\s+(?:was\s+)?not (?:carried|passed)", action, re.I):
        return False
    if re.search(r"\b(?:motion|vote)\s+(?:carried|passed)|all members.{0,60}(?:aye|yes)|"
                 r"vote on the motion:\s*all yes", action, re.I):
        return True
    return None


def cited_unanimous_recommendation(source, application_ids, selected):
    """Recognize a seconded advisory motion within one cited application section.

    This narrow minutes form can coexist with an unselected agenda template.
    A neighboring application's vote or an uncited result cannot rescue it.
    """
    from countyiq.lib.proceeding_coverage import _CASE

    headings = list(re.finditer(r"(?m)^[ \t]*(" + _CASE.pattern + r")[^\n]*", source, re.I))
    targets = [i for i, heading in enumerate(headings)
               if heading[1].casefold() in {value.casefold() for value in application_ids}]
    if len(targets) != 1:
        return False
    index = targets[0]
    start = headings[index].start()
    end = headings[index + 1].start() if index + 1 < len(headings) else len(source)
    groups = []
    for passage in selected:
        left, right = max(start, passage.start), min(end, passage.end)
        if left >= right:
            continue
        if groups and groups[-1][1] == left:
            groups[-1] = (groups[-1][0], right)
        else:
            groups.append((left, right))
    for left, right in groups:
        for motion in re.finditer(
                r"\bmotion to recommend (?:approval|denial)\b(?P<result>[\s\S]{0,160}?)\bUnanimous\b",
                source[left:right], re.I):
            between = motion["result"]
            if (re.search(r"\b(?:seconded|second|2nd)\b", between, re.I)
                    and not re.search(r"\b(?:not|failed|tied|defeated|withdrawn|deferred|tabled|continued|motion)\b|no vote", between, re.I)
                    and recorded_vote(motion[0]) is not False):
                return True
    return False


def header_authority_supported(authority, action, header):
    from countyiq.lib.proceeding_contract import compact
    if authority.casefold().strip() == "board":
        bodies = {_body_kind(match[0]) for match in _BODY.finditer(header)}
        if len(bodies) != 1 or not bodies <= {"board of supervisors", "zoning hearing board"}:
            return False
        authority = next(iter(bodies))
    if compact(authority).casefold() not in compact(header).casefold():
        return False
    if not authority_compatible(authority, action):
        return False
    # A bare case entry "Tabled" in minutes can use the declared meeting body.
    # This never supplies approval where no completed action is recorded.
    return (bool(deciding_bodies(action)) or recorded_vote(action) is not None
            or bool(re.search(r"\b(?:tabled|continued)\b", action, re.I))
            or ("board" in authority.casefold()
                and bool(re.search(r"\bBoard\s+(?:approved|denied|adopted|granted)\b", action, re.I))))


def decision_errors(decision, action):
    text = " ".join(action.split())
    errors = []
    if re.fullmatch(r"(?:motion|vote)(?:\s+(?:was|carried|passed|unanimously|approved))*\s*[:;,.]?\s*"
                    r"(?:\d{1,2}\s*[-/]\s*\d{1,2}|all (?:aye|yes))?[.!]?", text, re.I):
        errors.append("A vote result alone does not identify the action being decided")
    actors = deciding_bodies(text)
    body = _BODY.search(decision["authority"]) or re.search(r"\bCourt\b", decision["authority"], re.I)
    if body and actors and not authority_compatible(decision["authority"], text):
        errors.append("Decision action names a different deciding body")
    vote = recorded_vote(text)
    if re.search(r"approve\s*/\s*deny", text, re.I):
        errors.append("An unselected agenda template is not a completed decision")
    for match in re.finditer(r"\b(?:moved to grant|motion to (?:grant|approve))\b", text, re.I):
        tail = text[match.end():]
        outcome = re.search(r"\b(?:motion|vote)\s+(?:carried|passed)|"
                            r"\bvote(?:d)?(?:\s+(?:was|of))?\s*:?\s*\d{1,2}\s*[-/]\s*\d{1,2}|"
                            r"all members.{0,60}(?:aye|yes)", tail, re.I)
        before_outcome = tail[:outcome.start()] if outcome else tail
        another_action = re.search(r"\b(?:Council|Board)\s+(?:approved|discussed|adopted)|"
                                   r"\b(?:motion (?:to|by|was made)|made a motion|moved to)\b", before_outcome, re.I)
        if outcome is None or another_action:
            errors.append("A motion without a recorded outcome does not establish approval")
    if decision["scope"] == "ordinance" and decision["outcome"] == "approved" and re.search(
            r"amend(?:ed)? the draft|draft ordinance|submit.{0,70}(?:ordinance|review)|"
            r"integrate.{0,80}(?:adopted|standalone)|advertis.{0,60}for adoption", text, re.I):
        if not re.search(r"(?:adopted|enacted)\s+(?:the\s+)?(?:ordinance|ordinances)", text, re.I):
            errors.append("Draft amendment, referral or advertisement is not ordinance adoption")
    if decision["scope"] == "plan" and re.search(
            r"\b(?:execut\w*|record\w*)\b.{0,100}\bdeed\b", text, re.I):
        if not re.search(r"\b(?:approv\w*|reapprov\w*|grant\w*)\b.{0,100}\bplan\b", text, re.I):
            errors.append("Deed execution or recording does not establish plan approval")
    if decision["scope"] == "contract" and re.search(
            r"\b(?:advertis\w*|administer\w*)\b.{0,80}\bbids?\b", text, re.I):
        if not re.search(r"\b(?:award\w*|accept\w*|purchas\w*)\b|"
                         r"\bapprov\w*\b.{0,80}\b(?:contract|proposal|purchase)\b", text, re.I):
            errors.append("Advertising or administering bids does not establish a contract award")
    if decision["outcome"] == "continued" and re.search(r"remove.{0,100}(?:future|agenda)", text, re.I):
        errors.append("Removal from future agendas is not a continuance")
    explicit = {
        "approved": r"\b(?:approved|adopted|enacted|granted)\b",
        "denied": r"\b(?:denied|deny|rejected)\b",
        "tabled": r"\btabl(?:e|ed|ing)\b",
        "continued": r"\bcontinu(?:e|ed|ance)\b",
    }
    outcome = decision["outcome"]
    support = bool(re.search(explicit[outcome], text, re.I))
    if outcome == "approved":
        motion_object = re.search(r"\b(?:to|motion)\s+(approve|grant|deny|reject|table|continue)\b", text, re.I)
        if vote is True and not (motion_object and motion_object[1].casefold() in {"deny", "reject", "table", "continue"}):
            support = True
        if vote is False or re.search(r"\bnot (?:been )?(?:approved|adopted|enacted|granted)", text, re.I):
            support = False
        if vote is True and motion_object and motion_object[1].casefold() in {"deny", "reject", "table", "continue"}:
            support = False
    if outcome == "denied" and vote is False and re.search(r"\bto (?:deny|reject)\b", text, re.I):
        support = False
    if re.search(r"\b(?:not|never)\s+(?:been\s+)?" + explicit[outcome], text, re.I):
        support = False
    if vote is False and outcome in {"tabled", "continued"}:
        support = False
    if not support:
        errors.append("Decision excerpt does not establish the claimed completed outcome")
    return list(dict.fromkeys(errors))


def relevance_projection(category, scope, basis, evidence, *, summary='', source_context='', decision_action='', source_identity=False):
    """Return conservative product classification using only this item's text."""
    text = " ".join((basis, evidence))
    negative_context = " ".join((text, summary))
    minor = re.search(
        r"\b(?:homeowner|inground pool|in-ground pool|accessory garage|carport|"
        r"accessory building|driveway slope|lot.line adjustment|lot consolidation|minor subdivision|"
        r"two existing|existing (?:communication |communications )?towers|"
        r"tower.{0,45}exist|existing.{0,45}tower)\b", negative_context, re.I)
    # A commercial zoning district alone is not evidence of a commercial project.
    if minor and not re.search(r"\b(?:multi.family|apartments|warehouse|retirement|townhomes|townhouses)\b", text, re.I):
        category, scope = "minor_property", "property_relief"
    # These matters can remain source-backed context without becoming a
    # development opportunity. Use negative narrative context only to demote.
    if category == "landuse_policy" and re.search(
            r"number of members|commission membership|homeless encampment|"
            r"truck traffic|axle.{0,30}restrictions|weight restrictions|"
            r"property maintenance code|quality of life ordinances?",
            negative_context, re.I):
        category, scope = "context_only", "unknown"
    # A bond/developer-agreement vote is project history even if the model
    # labels it a construction contract. The caller supplies validated action
    # wording, so unrelated source paragraphs cannot provide this demotion.
    financial_action = re.search(
        r"\bsurety\b|bond (?:release|reduc|increas)|"
        r"(?:developer.?s?|development)(?: and stormwater)? agreements?|"
        r"deed of dedication|declaration of taking|road (?:use|maintenance).{0,30}agreement", decision_action, re.I)
    pending_agreement = re.search(
        r"unsigned agreements|agreements.{0,60}(?:awaiting|pending).{0,20}signatures",
        negative_context, re.I)
    if category == "public_works" and (financial_action or pending_agreement):
        category, scope = "context_only", "project_milestone"
    if (re.search(r"elevator addition|accessibility.only", negative_context, re.I)
            and not re.search(r"new building|additional dwelling units|"
                              r"\d[\d,]*[ -](?:square[ -]foot|sf).{0,35}(?:office|building|warehouse)",
                              evidence + " " + source_context, re.I)):
        category, scope = "minor_property", "property_relief"
    if re.search(r"agricultural security|ag security", text + " " + source_context, re.I):
        if re.search(r"(?:7|seven)[ -]year(?: Agricultural Security Area)? review|(?:municipality|township|borough)[ -]wide", source_context, re.I):
            category, scope = "landuse_policy", "policy_change"
        else:
            category, scope = "minor_property", "property_relief"
    if category == "development" and scope == "new_lots":
        explicit_use = re.search(r"residential|dwelling|housing|homes?|new building lot|"
                                 r"(?:[3-9]|[1-9]\d+|three|four|five|six|seven|eight|nine|ten)[ -]lots?\b",
                                 evidence + " " + source_context, re.I)
        if not explicit_use:
            category, scope = "context_only", "subdivision_only"
    if re.search(r"sewage (?:plan|planning) revision", text, re.I) and category == "landuse_policy":
        category, scope = "context_only", "project_milestone"
    if re.search(r"park rules|threatening wildlife|material and equipment bid|"
                 r"ordinary maintenance|compliance rate|deteriorated (?:inlet|covers)|"
                 r"naming the (?:new )?park", text, re.I):
        category, scope = "context_only", "unknown"
    if re.search(r"no new development|no development (?:is |was )?proposed|"
                 r"existing.lot split|lot.line adjustments? only", text, re.I):
        category, scope = "minor_property", "property_relief"
    # An explicit change in residential use is meaningful even inside an
    # existing shell. Require the source excerpt, never a model rationale alone.
    housing = re.search(r"multi[ -]?family|apartments?|dwelling units?|two[ -]unit|[2-9][ -]units?", evidence, re.I)
    conversion = re.search(r"\bconver(?:sion|t(?:ed|ing)?)\b|change of use", evidence, re.I)
    negative = re.search(r"\b(?:no|not|without)\s+(?:a\s+)?(?:proposed\s+)?conver|"
                         r"conversion.{0,60}(?:not proposed|prohibited)|"
                         r"existing (?:lawful|legal) (?:multi.family|apartments?)", evidence, re.I)
    historical = re.search(r"previously converted|converted in \d{4}|existing conversion|"
                           r"existing (?:multi.family|apartment).{0,60}(?:parking|repair)", evidence, re.I)
    linked = re.search(
        r"(?:conver(?:sion|t(?:ed|ing)?)|change of use)[^.;:\n]{0,100}"
        r"(?:multi[ -]?family|apartments?|dwelling units?|two[ -]unit|[2-9][ -]units?)|"
        r"(?:multi[ -]?family|apartments?|dwelling units?)[^.;:\n]{0,100}"
        r"conver(?:sion|t(?:ed|ing)?)", evidence, re.I)
    if housing and conversion and linked and not negative and not historical:
        category, scope = "development", "conversion"
    # Repurposing a building can be stated without the word "conversion".
    # Require an explicit destination use in the exact excerpt; renovations or
    # repairs alone do not establish a change of use.
    reuse_text = " ".join(evidence.split())
    adaptive_reuse = bool(re.search(
        r"\b(?:renovat|repurpos|adapt)\w*\b[^.;:]{0,100}\b(?:building|structure)\s+into\s+"
        r"(?:an?\s+)?(?:[a-z-]+\s+){0,2}(?:shelter|community cent(?:er|re)|apartments?|housing|offices?|school|hotel|retail|warehouse)\b",
        reuse_text, re.I)) and not re.search(
        r"\b(?:no|not|without)\s+(?:plans? to\s+|proposed\s+)?(?:renovat|repurpos|adapt)|"
        r"\bpreviously\b|\bin \d{4}\b|\bnot proposed\b", reuse_text, re.I)
    if adaptive_reuse:
        category, scope = "development", "conversion"
    # Model labels alone cannot qualify an opportunity. Require physical scope
    # or a land-use subject in the item's exact excerpt/limited source context.
    # Unknown work remains available as context instead of guessed construction.
    grounded = " ".join((" ".join((evidence, source_context))).split())
    # An identified formal plan is useful even when the agenda omits its use or
    # size. Keep that uncertainty explicit; a docket heading or time extension
    # alone does not establish a development proposal.
    formal_plan = source_identity and re.search(r"\bland development plan\b", grounded, re.I)
    administrative_plan = re.search(r"bond|surety|time.extension|deed|dedication|lot consolidation|lot.line|minor subdivision", negative_context, re.I)
    if formal_plan and not administrative_plan and category == "context_only" and scope == "unknown":
        category, scope = "development", "plan_review"
    if category == "development" and scope == "plan_review" and not (formal_plan and not administrative_plan):
        category, scope = "context_only", "unknown"
    if category == "development" and scope == "new_construction":
        proposal = re.search(r"\bpropos|\bconstruct|"
                             r"\bnew\s+(?:[\w-]+\s+){0,2}(?:building|homes?|housing|units?|"
                             r"apartments?|warehouse|barn|silo|office|hotel|field|facility|facilities)\b|"
                             r"\b(?:\d+|two|three|four|five|six|seven|eight|nine|ten)[ -]"
                             r"(?:homes?|units?|townhomes?|apartments?)\b", grounded, re.I)
        physical = re.search(r"building|homes?\b|hous(?:e|ing)|units?\b|apartments?|"
                             r"warehouse|barn|silo|office|hotel|commercial|industrial|field|facility|facilities", grounded, re.I)
        # A company containing Homes and a list of lot numbers provides no
        # construction action. Nor does the term land development by itself.
        if not (proposal and physical):
            category, scope = "context_only", "unknown"
    if category == "development" and scope in {"expansion", "conversion", "redevelopment"}:
        work = {
            "expansion": r"expan|addition|another.{0,40}(?:barn|building|unit)|add.{0,45}(?:unit|building|barn)|enlarg|landfill.{0,100}(?:height|capacity)",
            "conversion": r"conver|change of use",
            "redevelopment": r"redevelop|rehabilitat|adaptive reuse",
        }
        if not re.search(work[scope], grounded, re.I) and not (scope == "conversion" and adaptive_reuse):
            category, scope = "context_only", "unknown"
    if category == "landuse_policy" and scope == "policy_change":
        subject = re.search(r"zon(?:e|ing)|rezon|comprehensive plan|land use plan|ZO Sections?|wireless communications facilities|stormwater|"
                            r"agricultural security|ag security|data[ -]?cent(?:er|re)|"
                            r"warehouse|sawmill|hardship housing|battery|BESS\b|"
                            r"redevelopment overlay|(?:residential|commercial|industrial).{0,40}(?:district|zone)|"
                            r"development (?:fee|charge|moratorium)|"
                            r"(?:building|housing|residential) (?:density|capacity)|setback", grounded, re.I)
        if not subject:
            category, scope = "context_only", "unknown"
    if category == "public_works" and scope == "capital_project":
        # Payments/change orders and agreements are administrative even when
        # a generic heading calls them road work.
        administration = re.search(r"change orders?|payment requests?|"
                                   r"approv.{0,25}payments?|road (?:use|maintenance).{0,30}agreement",
                                   negative_context + " " + decision_action, re.I)
        physical = re.search(r"\bconstruct|\breconstruct|\breplac|\brelocat|\bpav(?:e|ed|ing)\b|"
                             r"\bwiden|\binstall|\bconver|\brenovat|\brestor|\bstabiliz|"
                             r"crosswalk.{0,60}(?:permitt|design|map|study)|(?:permitt|design|map|study).{0,60}crosswalk|"
                             r"\b(?:street|road|way|intersection|bridge|sidewalk|drainage).{0,45}improvements?\b|"
                             r"\b(?:street|road|sewer|water main).{0,25}(?:extension|ext\.)|"
                             r"\bnew roofs?\b|embankment.{0,40}complet|"
                             r"(?:roof|building).{0,30}(?:bid|addition)|"
                             r"(?:bid|addition).{0,30}(?:roof|building)", grounded, re.I)
        # Named capital scope survives its payment or procurement stage. Generic
        # road-program payments remain context; bond/developer agreements were
        # already demoted above and cannot be rescued by a rationale.
        named_upgrade = re.search(r"\b(?:WWTP|wastewater treatment plant|water treatment plant|pump station|generator).{0,35}\bupgrade\b", grounded, re.I)
        park_phase = re.search(r"\bpark\s+phase\s+(?:[IVX]+|\d+)\b.{0,20}\bproject\b", grounded, re.I)
        named_capital_grant = re.search(
            r"(?i:grant).{0,110}(?:(?i:pump station)|[A-Z][\w.'-]+ (?:Street|Road|Lane|Bridge))",
            grounded)  # Capitalized source location; a funding program alone is insufficient.
        if (administration and not named_upgrade) or not (physical or named_upgrade or park_phase or named_capital_grant):
            category, scope = "context_only", "project_milestone"
    positive = ((category == "development" and scope in {
        "new_construction", "expansion", "conversion", "redevelopment", "new_lots", "plan_review"})
        or (category == "landuse_policy" and scope == "policy_change")
        or (category == "public_works" and scope == "capital_project"))
    return category, scope, positive


def agenda_update_errors(status, summary, source_text, item_excerpt):
    if (status == "update" and re.search(r"\bagenda\b", source_text[:600], re.I)
            and re.search(r"\b(?:reported|reviewed|noted|discussed|considered)\b|report.{0,20}included", summary, re.I)
            and not re.search(r"motion (?:carried|passed)|all members.{0,60}aye", source_text, re.I)
            and not re.search(r"\b(?:reported|reviewed|noted|discussed|considered|completed|received|issued|awarded)\b", item_excerpt, re.I)):
        return ["An agenda-listed report is scheduled, not a completed report"]
    return []
