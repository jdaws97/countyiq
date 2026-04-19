"""Shared response types for FastAPI routes."""

from __future__ import annotations

from typing import Literal

from typing_extensions import NotRequired, TypedDict


SourceHealthStatus = Literal["green", "red"]
OverallHealthStatus = Literal["green", "yellow", "red"]


class SourceStatus(TypedDict):
    status: SourceHealthStatus
    record_count: int
    error: NotRequired[Literal["missing_table", "query_failed"]]


class OpsHealthResponse(TypedDict):
    overall: OverallHealthStatus
    sources: dict[str, SourceStatus]
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


class TaxDelinquencyRecord(TypedDict):
    tax_year: int | None
    authority_name: str
    tax_owed: float | int | None
    penalty_owed: float | int | None
    interest_owed: float | int | None
    fees_owed: float | int | None
    total: float | int | None
    owner_name: str | None
    property_address: str | None


class TaxDelinquencyPayload(TypedDict):
    is_delinquent: bool
    total_owed: float
    records: list[TaxDelinquencyRecord]


class FloodZonePayload(TypedDict):
    in_flood_zone: bool
    zone: str | None
    sfha: bool


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
    has_active_plan: bool
    eligible: bool
    exclusion_reasons: list[str]
    signals: dict[str, object]
    top_signal: str | None
    signal_count: int
    score_version: str | None
    computed_at: str | None
    reason_signals: list[ReasonSignalPayload]


class ParcelBriefPayload(TypedDict):
    brief_text: str
    assessment: str | None
    assessment_reasoning: str | None
    key_questions: list[str]
    signal_count: int | None
    citations: list[str]
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
    generated_at: str | None


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
    match_type: Literal["pidn", "address"]


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
        "heatsys": str | None,
        "fuel": str | None,
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
    structures: ParcelStructuresPayload
    development_momentum: DevelopmentMomentumPayload | None
    parcel_brief: ParcelBriefPayload | None
    related_narratives: list[CountyNarrativePayload]
    intelligence_summary: IntelligenceSummaryPayload | None
    linked_proceedings: list[LinkedProceedingPayload]


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
        "score_version": str | None,
        "computed_at": str | None,
        "owner_full": str | None,
        "propadr": str | None,
        "municipality": str | None,
        "acres": float | None,
        "aprtotal": float | None,
        "class": str | None,
        "reason_signals": list[ReasonSignalPayload],
    },
)


class RadarParcelListResponse(TypedDict):
    count: int
    parcels: list[RadarParcelPayload]


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
    delinquent_total: float
    years_delinquent: int | None


class ParcelBboxFeature(TypedDict):
    type: Literal["Feature"]
    geometry: dict[str, object] | None
    properties: dict[str, object]


class ParcelBboxResponse(TypedDict):
    type: Literal["FeatureCollection"]
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
    parcels: list[RadarBboxItem]


class MunicipalitySummary(TypedDict):
    name: str
    muni_type: str | None
    delinquent_parcels: int
    total_delinquent: float


class HealthResponse(TypedDict):
    status: Literal["ok"]


class LayerConfig(TypedDict):
    table: str
    properties: list[str]
    extra_sql: NotRequired[str]
