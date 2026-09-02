"""Shared response types for FastAPI routes."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal, NotRequired

from typing_extensions import TypedDict

SourceHealthStatus = Literal["green", "red"]
OverallHealthStatus = Literal["green", "yellow", "red"]
SourceHealthReason = Literal[
    "healthy",
    "empty_source",
    "last_run_failed",
    "missing_table",
    "policy_overdue",
    "query_failed",
    "run_not_observed",
    "source_unhealthy",
    "stale",
]
JobRunHealthStatus = Literal["success", "failure", "unknown"]


class SourceStatus(TypedDict):
    status: SourceHealthStatus
    record_count: int
    status_reason: NotRequired[SourceHealthReason]
    error: NotRequired[Literal["missing_table", "query_failed"]]
    refresh_job: NotRequired[str]
    expected_refresh_hours: NotRequired[int]
    last_run_status: NotRequired[JobRunHealthStatus]
    last_run_job: NotRequired[str]
    last_run_at: NotRequired[datetime | None]
    last_success_at: NotRequired[datetime | None]
    freshness_due_at: NotRequired[datetime | None]
    stale: NotRequired[bool]
    configured_count: NotRequired[int]
    active_count: NotRequired[int]
    healthy_count: NotRequired[int]
    blocked_count: NotRequired[int]
    unchecked_count: NotRequired[int]
    stale_count: NotRequired[int]
    last_checked_at: NotRequired[datetime | None]
    oldest_checked_at: NotRequired[datetime | None]
    conditional_count: NotRequired[int]
    paused_count: NotRequired[int]
    overdue_count: NotRequired[int]
    due_soon_count: NotRequired[int]
    next_review_on: NotRequired[date | None]


class IntelligenceIntegrityStatus(TypedDict):
    status: OverallHealthStatus
    status_reason: Literal[
        "healthy",
        "unresolved_contradictions",
        "recent_validation_rejections",
        "stale_contradictions",
        "projection_unlinked",
        "projection_mismatch",
        "missing_table",
        "query_failed",
    ]
    history_count: int
    accepted_count: int
    quarantined_count: int
    human_resolution_inference_count: int
    contradiction_count: int
    unresolved_contradiction_count: int
    resolved_contradiction_count: int
    oldest_unresolved_at: datetime | None
    projection_count: int
    unlinked_projection_count: int
    projection_mismatch_count: int
    validation_rejection_count: int
    validation_rejections_last_24h: int
    latest_validation_rejection_at: datetime | None
    max_unresolved_age_hours: int


class OpsHealthResponse(TypedDict):
    overall: OverallHealthStatus
    sources: dict[str, SourceStatus]
    intelligence_integrity: IntelligenceIntegrityStatus
    summary: str


class HomepageStatsResponse(TypedDict):
    total_records: float
    parcel_count: int
    municipality_count: int
    delinquent_parcels: int
    total_delinquent: float
    flood_zone_count: int
    liquor_license_count: int
    address_point_count: int
    structure_count: int
    total_assessed: float
    county_tax_owed: float
    school_tax_owed: float
    municipal_tax_owed: float
    oldest_delinquent_year: int | None
    districts_affected: int
    tax_claim_report_date: date | None


class TaxDelinquencyRecord(TypedDict):
    tax_year: int | None
    authority_name: str
    tax_owed: float | int | None
    penalty_owed: float | int | None
    interest_owed: float | int | None
    fees_owed: float | int | None
    total: float | int | None


class TaxDelinquencyPayload(TypedDict):
    detail_available: bool
    is_delinquent: bool
    total_owed: float | None
    records: list[TaxDelinquencyRecord]


class FloodZonePayload(TypedDict):
    in_flood_zone: bool
    zone: str | None
    sfha: bool
    overlap_pct: float | None


class StructureBuilding(TypedDict):
    type: str
    sqm: int
    sqft: int


class ParcelStructuresPayload(TypedDict):
    count: int
    likely_vacant: bool
    buildings: list[StructureBuilding]


class ReasonSignalPayload(TypedDict):
    key: str
    label: str
    weight: float
    is_direct: bool
    is_risk: bool


class DevelopmentMomentumPayload(TypedDict):
    score: float | int
    opportunity_score: float | int
    site_readiness_score: float | int
    has_active_plan: bool
    eligible: bool
    exclusion_reasons: list[str]
    signals: dict[str, object]
    top_signal: str | None
    signal_count: int
    score_version: int | None
    computed_at: str | None
    reason_signals: list[ReasonSignalPayload]


class ParcelBriefPayload(TypedDict):
    brief_text: str
    assessment: str | None
    assessment_reasoning: str | None
    key_questions: list[str]
    signal_count: int | None
    citations: list[str]
    citation_evidence: list[EvidencePayload]
    brief_version: int | None
    generated_at: str | None


class CountyNarrativePayload(TypedDict):
    narrative_id: int
    title: str
    body: str
    narrative_type: str
    trajectory: str | None
    key_entities: list[str]
    citations: list[str]
    citation_evidence: list[EvidencePayload]
    generated_at: str | None


class EvidencePayload(TypedDict):
    evidence_id: str
    citation_key: str
    label: str
    source_kind: str
    source_record_id: str | None
    url: str | None
    document_url: str | None
    internal_url: str | None
    excerpt: str | None
    details: dict[str, object]
    effective_at: str | None
    observed_at: str | None
    method: str
    caveat: str | None
    confidence: float | None


class SoilUnitPayload(TypedDict):
    objectid: int
    map_unit_symbol: str | None
    map_unit_name: str | None
    drainage: str | None
    capability_class: float | None
    permeability: float | None
    septic_rating: str | None
    slope_low: int | None
    slope_high: int | None
    representative_slope: float | None
    hydric_rating: str | None
    hydrologic_group: str | None
    relative_value: str | None
    source_url: str | None
    valid_from: datetime | None
    coverage_pct: float


class SoilProfilePayload(TypedDict):
    mapped_coverage_pct: float
    units: list[SoilUnitPayload]
    considerations: list[str]
    source_record_ids: list[int]
    source_url: str | None
    evidence: NotRequired[EvidencePayload]


class IntelligenceSourcePayload(EvidencePayload):
    pass


class IntelligenceProjectPayload(TypedDict):
    key: str
    name: str


class IntelligenceEntityLinkPayload(TypedDict):
    owner_id: int
    name: str
    matched_name: str
    verification_status: str | None


class IntelligenceInterpretationPayload(TypedDict):
    kind: Literal["deterministic", "llm"]
    model: str | None
    generated_at: str | None


class IntelligenceEventPayload(TypedDict):
    event_key: str
    category: Literal["parcel", "development"]
    event_type: str
    event_tags: list[str]
    title: str
    what_happened: str
    why_it_matters: str
    what_happens_next: str
    event_date: str | None
    detected_at: str
    confidence: float | None
    municipality: str | None
    project: IntelligenceProjectPayload | None
    related_entities: list[str]
    entity_links: list[IntelligenceEntityLinkPayload]
    related_pidns: list[str]
    importance_score: int
    importance_reasons: list[str]
    sources: list[IntelligenceSourcePayload]
    interpretation: IntelligenceInterpretationPayload


class IntelligenceFeedResponse(TypedDict):
    events: list[IntelligenceEventPayload]
    limit: int
    offset: int
    has_more: bool


class IntelligenceSummaryPayload(TypedDict):
    cross_signal_insight: str | None
    last_run_at: str | None
    signals_validated_count: int | None


class LinkedProceedingPayload(TypedDict):
    proceeding_id: int
    body_name: str | None
    meeting_date: str | None
    proceeding_type: str | None
    extraction_type: str | None
    applicant_name: str | None
    decision: str | None
    current_zoning: str | None
    proposed_zoning: str | None
    supporting_text: str | None
    document_url: str | None
    extraction_confidence: float | None
    page_number: int | None
    match_type: Literal["pidn", "address"]
    evidence: EvidencePayload


ParcelPayload = TypedDict(
    "ParcelPayload",
    {
        "pidn": str,
        "owner_full": str | None,
        "own_name1": str | None,
        "own_name2": str | None,
        "prev_owner": str | None,
        "propadr": str | None,
        "mail_addr_full": str | None,
        "municipality": str | None,
        "school_dis": str | None,
        "class": str | None,
        "luc": str | None,
        "acres": float | int | str | None,
        "style": str | None,
        "num_stories": float | int | str | None,
        "res_living_area": float | int | str | None,
        "yrblt": float | int | str | None,
        "heatsys": int | None,
        "fuel": int | None,
        "clean_green": str | None,
        "grade": str | None,
        "cdu": str | None,
        "aprland": float | None,
        "aprbldg": float | None,
        "aprtotal": float | None,
        "saledt": str | None,
        "price": float | None,
        "prev_price": float | None,
        "deed_bk": float | int | str | None,
        "deed_pg": float | int | str | None,
        "comm_struc": str | None,
        "comm_year_built": float | int | str | None,
        "comm_building_sq_ft": float | int | str | None,
        "lat": float | None,
        "lng": float | None,
    },
)


class PropertyReportResponse(TypedDict):
    parcel: ParcelPayload
    tax_delinquency: TaxDelinquencyPayload
    flood_zone: FloodZonePayload
    soil_profile: SoilProfilePayload
    structures: ParcelStructuresPayload
    development_momentum: DevelopmentMomentumPayload | None
    parcel_brief: ParcelBriefPayload | None
    related_narratives: list[CountyNarrativePayload]
    intelligence_summary: IntelligenceSummaryPayload | None
    linked_proceedings: list[LinkedProceedingPayload]
    evidence: list[EvidencePayload]


RadarParcelPayload = TypedDict(
    "RadarParcelPayload",
    {
        "pidn": str,
        "score": float | int,
        "top_signal": str | None,
        "signal_count": int,
        "signals": dict[str, object] | None,
        "eligible": bool,
        "has_active_plan": NotRequired[bool],
        "site_readiness_score": NotRequired[float | int],
        "score_version": int | None,
        "computed_at": str | None,
        "owner_full": str | None,
        "propadr": str | None,
        "municipality": str | None,
        "acres": float | None,
        "aprtotal": float | None,
        "class": str | None,
        "reason_signals": list[ReasonSignalPayload],
        # Movers (score_version 6+): previous snapshot and deltas.
        "previous_score": NotRequired[int | None],
        "previous_opportunity_score": NotRequired[int | None],
        "score_delta": NotRequired[int | None],
        "opportunity_delta": NotRequired[int | None],
        "previous_computed_at": NotRequired[str | None],
        "is_new": NotRequired[bool],
    },
)


class RadarMoversResponse(TypedDict):
    count: int
    view: Literal["opportunity", "momentum"]
    direction: Literal["up", "down", "new"]
    previous_computed_at: str | None
    parcels: list[RadarParcelPayload]


class MunicipalityPipelineCountPayload(TypedDict):
    event_type: str
    count: int


class MunicipalityPipelineMatterPayload(TypedDict):
    event_key: str
    event_type: str
    title: str
    event_date: str | None
    project_key: str | None
    project_name: str | None
    related_pidns: list[str]


class MunicipalityPipelinePayload(TypedDict):
    window_days: int
    total_matters: int
    by_event_type: list[MunicipalityPipelineCountPayload]
    upcoming: list[MunicipalityPipelineMatterPayload]
    recent: list[MunicipalityPipelineMatterPayload]


class MunicipalityRadarTopPayload(TypedDict):
    pidn: str
    propadr: str | None
    acres: float | None
    opportunity_score: int
    score: int
    top_signal: str | None
    opportunity_delta: int | None
    is_new: bool


class RadarParcelListResponse(TypedDict):
    count: int
    parcels: list[RadarParcelPayload]
    coverage: NotRequired[dict[str, object]]


class RadarMunicipalitiesResponse(TypedDict):
    municipalities: list[str]


class ParcelBboxProperties(TypedDict, total=False):
    pidn: str
    owner_full: str | None
    propadr: str | None
    aprtotal: float | None
    municipality: str | None
    class_: str | None
    saledt: str | None
    price: float | None
    has_tax_delinquency: bool


class ParcelBboxFeature(TypedDict):
    type: Literal["Feature"]
    geometry: dict[str, object] | None
    properties: dict[str, object]


class ParcelBboxResponse(TypedDict):
    type: Literal["FeatureCollection"]
    count: int
    limit: int
    truncated: bool
    features: list[ParcelBboxFeature]


class RadarBboxItem(TypedDict):
    pidn: str
    score: float | int
    eligible: bool
    top_signal: str | None
    lng: float | None
    lat: float | None


class RadarBboxResponse(TypedDict):
    count: int
    limit: int
    truncated: bool
    parcels: list[RadarBboxItem]


class MunicipalitySummary(TypedDict):
    name: str
    muni_type: str | None
    delinquent_parcels: int
    total_delinquent: float


class MunicipalityStatsPayload(TypedDict):
    parcel_count: int
    total_assessed: float


class MunicipalityDelinquencyPayload(TypedDict):
    delinquent_parcels: int
    total_delinquent: float
    oldest_delinquent_year: int | None
    delinquent_years: int


class TopDelinquentOwnerPayload(TypedDict):
    owner_name: str
    parcel_count: int
    total_owed: float
    oldest_year: int | None
    newest_year: int | None
    years_delinquent: int
    districts: list[str]


class MunicipalityLicenseSummaryPayload(TypedDict):
    licensee: str | None
    premises_name: str | None
    premises_address: str | None
    license_type: str
    status: str | None
    municipality: str | None
    last_issue_date: str | None
    expiration_date: str | None


class MunicipalityProfileResponse(TypedDict):
    name: str
    muni_type: str | None
    county: str | None
    stats: MunicipalityStatsPayload
    delinquency: MunicipalityDelinquencyPayload
    licenses: list[MunicipalityLicenseSummaryPayload]
    development_pipeline: NotRequired["MunicipalityPipelinePayload | None"]
    radar_top: NotRequired[list["MunicipalityRadarTopPayload"]]


class HealthResponse(TypedDict):
    status: Literal["ok"]


class LayerConfig(TypedDict):
    table: str
    properties: list[str]
    extra_sql: NotRequired[str]
