"""Pass 4 — County Narratives.

Detects cross-parcel patterns via 4 scan types and synthesizes narratives:
  A. Corridor Activity — clusters of parcels with shared signals within 500m
  B. Owner Portfolio — entities with 3+ briefed parcels meeting criteria
  C. Municipal Trends — per-municipality assessment/signal/ZHB/distress stats
  D. Distress Migration — current vs 90-day-prior tax distress comparison

Public entry points per scan:
  - build_corridor_prompt(cluster) -> str
  - build_portfolio_prompt(portfolio) -> str
  - build_municipal_prompt(data) -> str
  - build_distress_prompt(data) -> str

Shared:
  - parse_narrative_output(output) -> dict
"""

from __future__ import annotations

from typing import Any


# =============================================================================
# CONSTANTS
# =============================================================================

VALID_NARRATIVE_TYPES = {
    "corridor",
    "municipality",
    "owner_portfolio",
    "market_segment",
}

VALID_TRAJECTORIES = {
    "accelerating",
    "steady",
    "stalling",
    "growing",
    "stable",
    "declining",
    "transitioning",
    "expanding",
    "holding",
    "unwinding",
    "distressed",
    "concentrating",
    "spreading",
    "resolving",
}


# =============================================================================
# SCAN A: CORRIDOR ACTIVITY
# =============================================================================

CORRIDOR_SCAN_QUERY = """
    WITH adjacent_pairs AS (
        -- Find pairs of parcels with the SAME signal type within 500m
        SELECT
            e1.signal_key,
            e1.pidn AS pidn_a,
            e2.pidn AS pidn_b,
            p1.municipality
        FROM public.evidence e1
        JOIN staging.parcels p1
            ON p1.pidn = e1.pidn AND p1.valid_to IS NULL AND p1.geom IS NOT NULL
        JOIN public.evidence e2
            ON e1.signal_key = e2.signal_key AND e1.pidn < e2.pidn
        JOIN staging.parcels p2
            ON p2.pidn = e2.pidn AND p2.valid_to IS NULL AND p2.geom IS NOT NULL
        WHERE ST_DWithin(p1.geom::geography, p2.geom::geography, 500)
    ),
    signal_clusters AS (
        -- Group by signal_key AND municipality to avoid merging
        -- geographically distant parcels that share a signal type.
        -- Collect BOTH sides of each pair to avoid dropping PIDNs.
        SELECT
            signal_key,
            municipality,
            ARRAY(
                SELECT DISTINCT unnest
                FROM unnest(
                    ARRAY_AGG(pidn_a) || ARRAY_AGG(pidn_b)
                )
                ORDER BY unnest
            ) AS cluster_pidns
        FROM adjacent_pairs
        GROUP BY signal_key, municipality
    )
    SELECT
        signal_key,
        municipality,
        cluster_pidns,
        array_length(cluster_pidns, 1) AS cluster_size
    FROM signal_clusters
    WHERE array_length(cluster_pidns, 1) >= 3
    ORDER BY array_length(cluster_pidns, 1) DESC
"""

CORRIDOR_TEMPLATE = """You are a county intelligence analyst identifying corridor-level development patterns in York County, PA.

Your job is to synthesize cluster data into a narrative about what is happening along this corridor and whether the activity is coordinated or independent.

CLUSTER:
- Signal type: {signal_key}
- Cluster size: {cluster_size} parcels
- PIDNs: {cluster_pidns}

PARCELS IN CLUSTER:
{parcels_text}

RECENT PROCEEDINGS:
{proceedings_text}

CONSTRAINTS:
1. Every claim MUST be grounded in the data above. Do not invent facts.
2. Do not provide legal or financial advice.
3. If evidence is ambiguous, say so explicitly.

TASKS:
1. Write a corridor-level story explaining what is happening across these parcels.
2. Assess whether the activity appears coordinated (single developer/entity) or independent (unrelated owners).
3. Describe the trajectory of this corridor — is development accelerating, steady, or stalling?
4. Identify who should care about this corridor (municipal planners, developers, adjacent owners).

OUTPUT FORMAT:
Return ONLY valid JSON with this structure:
{{
  "title": "Short corridor narrative title",
  "narrative": "2-4 paragraph corridor narrative",
  "narrative_type": "corridor",
  "trajectory": "accelerating|steady|stalling",
  "affected_pidns": ["pidn1", "pidn2", ...],
  "key_entities": ["entity name 1", ...],
  "citations": ["signal_key_1", ...]
}}

Return ONLY valid JSON. Do not include commentary outside the JSON object."""


def _format_corridor_parcels(parcels: list[dict]) -> str:
    """Format parcel list for corridor prompt."""
    if not parcels:
        return "(no parcel data available)"

    sections = []
    for p in parcels:
        lines = [
            f"- PIDN: {p.get('pidn', '')}",
            f"  Address: {p.get('address', '')}",
            f"  Assessment: {p.get('assessment', 'unknown')}",
            f"  Brief excerpt: {p.get('brief_excerpt', 'N/A')}",
        ]
        sections.append("\n".join(lines))
    return "\n\n".join(sections)


def _format_corridor_proceedings(proceedings: list[dict]) -> str:
    """Format proceedings list for corridor prompt."""
    if not proceedings:
        return "(no recent proceedings)"

    sections = []
    for pr in proceedings:
        lines = [
            f"- Type: {pr.get('type', '')}",
            f"  Applicant: {pr.get('applicant', '')}",
            f"  Decision: {pr.get('decision', '')}",
            f"  Date: {pr.get('meeting_date', '')}",
            f"  Body: {pr.get('body', '')}",
        ]
        sections.append("\n".join(lines))
    return "\n\n".join(sections)


def build_corridor_prompt(cluster: dict) -> str:
    """Format cluster data into the corridor narrative prompt.

    Args:
        cluster: Dict with keys: signal_key, cluster_size, cluster_pidns,
                 parcels (list of dicts), proceedings (list of dicts).

    Returns:
        Fully formatted prompt string ready for LLM invocation.
    """
    parcels_text = _format_corridor_parcels(cluster.get("parcels", []))
    proceedings_text = _format_corridor_proceedings(cluster.get("proceedings", []))

    pidns_str = ", ".join(cluster.get("cluster_pidns", []))

    return CORRIDOR_TEMPLATE.format(
        signal_key=cluster.get("signal_key", ""),
        cluster_size=cluster.get("cluster_size", 0),
        cluster_pidns=pidns_str,
        parcels_text=parcels_text,
        proceedings_text=proceedings_text,
    )


# =============================================================================
# SCAN B: OWNER PORTFOLIO
# =============================================================================

PORTFOLIO_SCAN_QUERY = """
    WITH entity_briefs AS (
        SELECT
            eg.entity_id,
            eg.canonical_name,
            eg.entity_type,
            COUNT(DISTINCT pb.pidn) AS briefed_parcels,
            ARRAY_AGG(DISTINCT p.municipality) FILTER (WHERE p.municipality IS NOT NULL) AS municipalities,
            COALESCE(SUM(p.acres), 0) AS total_acres,
            ARRAY_AGG(DISTINCT pb.pidn) AS pidns,
            COUNT(DISTINCT pb.pidn) FILTER (
                WHERE pb.assessment IN ('constrained', 'not_actionable')
            ) AS distressed_count,
            COUNT(DISTINCT pb.pidn) FILTER (
                WHERE p.saledt >= (CURRENT_DATE - INTERVAL '180 days')::text
            ) AS recent_acquisitions
        FROM public.entity_graph eg
        JOIN staging.parcels p
            ON (p.owner_full = eg.canonical_name OR p.owner_full = ANY(eg.linked_names))
            AND p.valid_to IS NULL
        JOIN public.parcel_briefs pb
            ON pb.pidn = p.pidn
        GROUP BY eg.entity_id, eg.canonical_name, eg.entity_type
        HAVING COUNT(DISTINCT pb.pidn) >= 3
    )
    SELECT
        entity_id,
        canonical_name,
        entity_type,
        briefed_parcels,
        municipalities,
        total_acres,
        pidns
    FROM entity_briefs
    WHERE distressed_count >= 2
       OR recent_acquisitions >= 2
       OR ARRAY_LENGTH(municipalities, 1) >= 3
    ORDER BY briefed_parcels DESC
"""

PORTFOLIO_TEMPLATE = """You are a county intelligence analyst profiling an entity's real estate portfolio in York County, PA.

Your job is to synthesize the entity's parcel briefs and deed history into a narrative about the entity's strategy and trajectory.

ENTITY:
- Name: {canonical_name}
- Type: {entity_type}
- Briefed parcels: {briefed_parcels}
- Municipalities: {municipalities}
- Total acres: {total_acres}

PARCEL BRIEFS:
{briefs_text}

DEED HISTORY:
{deeds_text}

CONSTRAINTS:
1. Every claim MUST be grounded in the data above. Do not invent facts.
2. Do not provide legal or financial advice.
3. If the entity's intent is unclear, say so explicitly.

TASKS:
1. Describe the entity's apparent real estate strategy based on their portfolio composition and activity.
2. Construct a timeline of key portfolio moves (acquisitions, dispositions, development activity).
3. Assess whether the entity is expanding, holding, or unwinding their portfolio.
4. Identify the entity's impact on the municipalities where they operate.

OUTPUT FORMAT:
Return ONLY valid JSON with this structure:
{{
  "title": "Short entity portfolio narrative title",
  "narrative": "2-4 paragraph entity narrative",
  "narrative_type": "owner_portfolio",
  "trajectory": "expanding|holding|unwinding",
  "affected_pidns": ["pidn1", "pidn2", ...],
  "key_entities": ["entity name"],
  "citations": ["signal_key_1", ...]
}}

Return ONLY valid JSON. Do not include commentary outside the JSON object."""


def _format_portfolio_briefs(briefs: list[dict]) -> str:
    """Format brief summaries for portfolio prompt."""
    if not briefs:
        return "(no parcel briefs available)"

    sections = []
    for b in briefs:
        lines = [
            f"- PIDN: {b.get('pidn', '')}",
            f"  Address: {b.get('address', '')}",
            f"  Assessment: {b.get('assessment', 'unknown')}",
            f"  Brief excerpt: {b.get('brief_excerpt', 'N/A')}",
        ]
        sections.append("\n".join(lines))
    return "\n\n".join(sections)


def _format_portfolio_deeds(deeds: list[dict]) -> str:
    """Format deed history for portfolio prompt."""
    if not deeds:
        return "(no deed history available)"

    sections = []
    for d in deeds:
        price = d.get("price", 0)
        price_str = f"${price:,.0f}" if price else "N/A"
        lines = [
            f"- PIDN: {d.get('pidn', '')}",
            f"  Grantor: {d.get('grantor', '')}",
            f"  Grantee: {d.get('grantee', '')}",
            f"  Date: {d.get('date', '')}",
            f"  Price: {price_str}",
        ]
        sections.append("\n".join(lines))
    return "\n\n".join(sections)


def build_portfolio_prompt(portfolio: dict) -> str:
    """Format entity portfolio data into the portfolio narrative prompt.

    Args:
        portfolio: Dict with keys: entity_id, canonical_name, entity_type,
                   briefed_parcels, municipalities, total_acres, pidns,
                   briefs (list of dicts), deeds (list of dicts).

    Returns:
        Fully formatted prompt string ready for LLM invocation.
    """
    briefs_text = _format_portfolio_briefs(portfolio.get("briefs", []))
    deeds_text = _format_portfolio_deeds(portfolio.get("deeds", []))

    municipalities = portfolio.get("municipalities", [])
    municipalities_str = ", ".join(municipalities) if municipalities else "N/A"

    return PORTFOLIO_TEMPLATE.format(
        canonical_name=portfolio.get("canonical_name", ""),
        entity_type=portfolio.get("entity_type", "unknown"),
        briefed_parcels=portfolio.get("briefed_parcels", 0),
        municipalities=municipalities_str,
        total_acres=portfolio.get("total_acres", 0),
        briefs_text=briefs_text,
        deeds_text=deeds_text,
    )


# =============================================================================
# SCAN C: MUNICIPAL TRENDS
# =============================================================================

MUNICIPAL_SCAN_QUERY = """
    WITH tax_by_muni AS (
        -- Pre-aggregate tax totals per municipality to avoid fan-out
        -- when joining with evidence (which is also one-to-many per parcel)
        SELECT
            p.municipality,
            COUNT(DISTINCT tc.pidn) AS delinquent_parcels,
            COALESCE(SUM(tc.total), 0) AS total_owed
        FROM staging.parcels p
        JOIN staging.tax_claims tc ON tc.pidn = p.pidn AND tc.valid_to IS NULL
        WHERE p.valid_to IS NULL AND p.municipality IS NOT NULL
        GROUP BY p.municipality
    )
    SELECT
        p.municipality,
        -- Assessment distribution from parcel_briefs
        COUNT(DISTINCT pb.pidn) FILTER (WHERE pb.assessment = 'strong_opportunity') AS strong_opportunity_count,
        COUNT(DISTINCT pb.pidn) FILTER (WHERE pb.assessment = 'emerging') AS emerging_count,
        COUNT(DISTINCT pb.pidn) FILTER (WHERE pb.assessment = 'speculative') AS speculative_count,
        COUNT(DISTINCT pb.pidn) FILTER (WHERE pb.assessment = 'constrained') AS constrained_count,
        COUNT(DISTINCT pb.pidn) FILTER (WHERE pb.assessment = 'not_actionable') AS not_actionable_count,
        -- Signal distribution from evidence
        COUNT(DISTINCT e.pidn) FILTER (WHERE e.adjusted_significance = 'high') AS high_signal_count,
        COUNT(DISTINCT e.pidn) FILTER (WHERE e.adjusted_significance = 'medium') AS medium_signal_count,
        COUNT(DISTINCT e.pidn) FILTER (WHERE e.adjusted_significance = 'low') AS low_signal_count,
        -- Distress summary (from pre-aggregated CTE — no fan-out)
        COALESCE(tbm.delinquent_parcels, 0) AS delinquent_parcels,
        COALESCE(tbm.total_owed, 0) AS total_owed
    FROM staging.parcels p
    LEFT JOIN public.parcel_briefs pb ON pb.pidn = p.pidn
    LEFT JOIN public.evidence e ON e.pidn = p.pidn
    LEFT JOIN tax_by_muni tbm ON tbm.municipality = p.municipality
    WHERE p.valid_to IS NULL
      AND p.municipality IS NOT NULL
    GROUP BY p.municipality, tbm.delinquent_parcels, tbm.total_owed
    HAVING COUNT(DISTINCT pb.pidn) >= 1
    ORDER BY p.municipality
"""

MUNICIPAL_TEMPLATE = """You are a county intelligence analyst assessing municipal-level development and distress trends in York County, PA.

Your job is to synthesize the data below into a narrative about the municipality's current development posture and tensions.

MUNICIPALITY: {municipality}

ASSESSMENT DISTRIBUTION (from parcel briefs):
{assessment_text}

SIGNAL DISTRIBUTION (from validated evidence):
{signal_text}

ZHB DECISIONS (from proceeding extractions):
{zhb_text}

DISTRESS SUMMARY (from tax claims):
{distress_text}

CONSTRAINTS:
1. Every claim MUST be grounded in the data above. Do not invent facts.
2. Do not provide legal or financial advice.
3. If trends are ambiguous, say so explicitly.

TASKS:
1. Characterize the municipality's overall development posture — is it growing, stable, declining, or transitioning?
2. Identify ZHB decision patterns — is the board generally permissive or restrictive?
3. Highlight tension points where development activity conflicts with distress or constraints.
4. Summarize what a decision-maker should know about this municipality.

OUTPUT FORMAT:
Return ONLY valid JSON with this structure:
{{
  "title": "Short municipality narrative title",
  "narrative": "2-4 paragraph municipality narrative",
  "narrative_type": "municipality",
  "trajectory": "growing|stable|declining|transitioning",
  "affected_pidns": ["pidn1", ...],
  "key_entities": ["entity name 1", ...],
  "citations": ["signal_key_1", ...]
}}

Return ONLY valid JSON. Do not include commentary outside the JSON object."""


def _format_assessment_distribution(data: dict) -> str:
    """Format assessment distribution for municipal prompt."""
    dist = data.get("assessment_distribution", {})
    if not dist:
        return "(no assessment data available)"

    lines = []
    for assessment, count in sorted(dist.items()):
        lines.append(f"- {assessment}: {count} parcels")
    return "\n".join(lines)


def _format_signal_distribution(data: dict) -> str:
    """Format signal distribution for municipal prompt."""
    dist = data.get("signal_distribution", {})
    if not dist:
        return "(no signal data available)"

    lines = []
    for signal_key, count in sorted(dist.items()):
        lines.append(f"- {signal_key}: {count} parcels")
    return "\n".join(lines)


def _format_zhb_decisions(data: dict) -> str:
    """Format ZHB decision summary for municipal prompt."""
    zhb = data.get("zhb_decisions", {})
    if not zhb:
        return "(no ZHB decision data available)"

    lines = []
    for decision, count in sorted(zhb.items()):
        lines.append(f"- {decision}: {count}")
    return "\n".join(lines)


def _format_distress_summary(data: dict) -> str:
    """Format distress summary for municipal prompt."""
    distress = data.get("distress_summary", {})
    if not distress:
        return "(no distress data available)"

    lines = []
    delinquent = distress.get("delinquent_parcels", 0)
    total_owed = distress.get("total_owed", 0)
    sheriff = distress.get("sheriff_sale_count", 0)

    lines.append(f"- Delinquent parcels: {delinquent}")
    lines.append(f"- Total owed: ${total_owed:,.0f}")
    if sheriff:
        lines.append(f"- Sheriff sale count: {sheriff}")
    return "\n".join(lines)


def build_municipal_prompt(data: dict) -> str:
    """Format municipal trend data into the municipal narrative prompt.

    Args:
        data: Dict with keys: municipality, assessment_distribution,
              signal_distribution, zhb_decisions, distress_summary.

    Returns:
        Fully formatted prompt string ready for LLM invocation.
    """
    assessment_text = _format_assessment_distribution(data)
    signal_text = _format_signal_distribution(data)
    zhb_text = _format_zhb_decisions(data)
    distress_text = _format_distress_summary(data)

    return MUNICIPAL_TEMPLATE.format(
        municipality=data.get("municipality", ""),
        assessment_text=assessment_text,
        signal_text=signal_text,
        zhb_text=zhb_text,
        distress_text=distress_text,
    )


# =============================================================================
# SCAN D: DISTRESS MIGRATION
# =============================================================================

DISTRESS_SCAN_QUERY = """
    WITH current_distress AS (
        SELECT
            p.municipality,
            p.school_dis,
            COUNT(DISTINCT tc.pidn) AS current_count,
            COALESCE(SUM(tc.total), 0) AS current_total_owed
        FROM staging.tax_claims tc
        JOIN staging.parcels p ON p.pidn = tc.pidn AND p.valid_to IS NULL
        WHERE tc.valid_to IS NULL
        GROUP BY p.municipality, p.school_dis
    ),
    prior_distress AS (
        SELECT
            p.municipality,
            p.school_dis,
            COUNT(DISTINCT tc.pidn) AS prior_count,
            COALESCE(SUM(tc.total), 0) AS prior_total_owed
        FROM staging.tax_claims tc
        JOIN staging.parcels p ON p.pidn = tc.pidn AND p.valid_to IS NULL
        WHERE tc.valid_from <= (CURRENT_DATE - INTERVAL '90 days')
          AND (tc.valid_to IS NULL OR tc.valid_to > (CURRENT_DATE - INTERVAL '90 days'))
        GROUP BY p.municipality, p.school_dis
    )
    SELECT
        COALESCE(c.municipality, pr.municipality) AS municipality,
        COALESCE(c.school_dis, pr.school_dis) AS school_dis,
        COALESCE(c.current_count, 0) AS current_count,
        COALESCE(pr.prior_count, 0) AS prior_count,
        COALESCE(c.current_total_owed, 0) AS current_total_owed,
        COALESCE(pr.prior_total_owed, 0) AS prior_total_owed,
        COALESCE(c.current_count, 0) - COALESCE(pr.prior_count, 0) AS count_delta,
        COALESCE(c.current_total_owed, 0) - COALESCE(pr.prior_total_owed, 0) AS total_delta
    FROM current_distress c
    FULL OUTER JOIN prior_distress pr
        ON c.municipality = pr.municipality AND c.school_dis = pr.school_dis
    WHERE ABS(COALESCE(c.current_count, 0) - COALESCE(pr.prior_count, 0)) >= 5
       OR ABS(COALESCE(c.current_total_owed, 0) - COALESCE(pr.prior_total_owed, 0)) >= 10000
    ORDER BY ABS(COALESCE(c.current_total_owed, 0) - COALESCE(pr.prior_total_owed, 0)) DESC
"""

DISTRESS_TEMPLATE = """You are a county intelligence analyst tracking tax distress migration patterns in York County, PA.

Your job is to analyze how tax delinquency is changing across municipalities and school districts, identifying where distress is concentrating, spreading, or resolving.

DISTRESS CHANGE DATA:
- Municipality: {municipality}
- School district: {school_dis}
- Current delinquent parcels: {current_count}
- Prior delinquent parcels (90 days ago): {prior_count}
- Parcel count change: {count_delta:+d}
- Current total owed: ${current_total_owed:,.0f}
- Prior total owed (90 days ago): ${prior_total_owed:,.0f}
- Total owed change: ${total_delta:+,.0f}

CONSTRAINTS:
1. Every claim MUST be grounded in the data above. Do not invent facts.
2. Do not provide legal or financial advice.
3. If the direction of change is ambiguous, say so explicitly.

TASKS:
1. Identify whether distress is concentrating in this area or resolving.
2. Assess the school district impact — is delinquency affecting revenue significantly?
3. Determine if distress is spreading (new parcels) vs deepening (same parcels, more owed).
4. Predict whether forced sales are likely based on the trend direction and magnitude.

OUTPUT FORMAT:
Return ONLY valid JSON with this structure:
{{
  "title": "Short distress migration narrative title",
  "narrative": "2-4 paragraph distress narrative",
  "narrative_type": "market_segment",
  "trajectory": "concentrating|spreading|resolving|distressed",
  "affected_pidns": ["pidn1", ...],
  "citations": ["signal_key_1", ...]
}}

Return ONLY valid JSON. Do not include commentary outside the JSON object."""


def build_distress_prompt(data: dict) -> str:
    """Format distress migration data into the distress narrative prompt.

    Args:
        data: Dict with keys: municipality, school_dis, current_count,
              prior_count, current_total_owed, prior_total_owed,
              count_delta, total_delta.

    Returns:
        Fully formatted prompt string ready for LLM invocation.
    """
    return DISTRESS_TEMPLATE.format(
        municipality=data.get("municipality", ""),
        school_dis=data.get("school_dis", ""),
        current_count=data.get("current_count", 0),
        prior_count=data.get("prior_count", 0),
        count_delta=data.get("count_delta", 0),
        current_total_owed=data.get("current_total_owed", 0),
        prior_total_owed=data.get("prior_total_owed", 0),
        total_delta=data.get("total_delta", 0),
    )


# =============================================================================
# SHARED: OUTPUT PARSER
# =============================================================================

def parse_narrative_output(output: Any) -> dict:
    """Validate and normalize LLM narrative output.

    Required: title, narrative.
    Clamps narrative_type to VALID_NARRATIVE_TYPES (default: "corridor").
    Clamps trajectory to VALID_TRAJECTORIES (default: "stable").
    Returns an error key if title or narrative is missing or empty.

    Args:
        output: Parsed JSON dict from LLM response.

    Returns:
        Normalized dict with title, narrative, narrative_type, trajectory,
        affected_pidns, key_entities, citations.
        Or dict with 'error' key if the output is invalid.
    """
    if not isinstance(output, dict):
        return {"error": "Output is not a dict"}

    title = output.get("title")
    if not title:
        return {"error": "Missing or empty 'title' in output"}

    narrative = output.get("narrative")
    if not narrative:
        return {"error": "Missing or empty 'narrative' in output"}

    # Clamp narrative_type
    narrative_type = output.get("narrative_type", "corridor")
    if narrative_type not in VALID_NARRATIVE_TYPES:
        narrative_type = "corridor"

    # Clamp trajectory
    trajectory = output.get("trajectory", "stable")
    if trajectory not in VALID_TRAJECTORIES:
        trajectory = "stable"

    # Normalize list fields
    affected_pidns = output.get("affected_pidns", [])
    if not isinstance(affected_pidns, list):
        affected_pidns = []

    key_entities = output.get("key_entities", [])
    if not isinstance(key_entities, list):
        key_entities = []

    citations = output.get("citations", [])
    if not isinstance(citations, list):
        citations = []

    return {
        "title": title,
        "narrative": narrative,
        "narrative_type": narrative_type,
        "trajectory": trajectory,
        "affected_pidns": affected_pidns,
        "key_entities": key_entities,
        "citations": citations,
    }
