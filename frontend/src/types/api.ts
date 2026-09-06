export type NumericLike = number | string | null | undefined

export interface CountyMetadata {
  county_key: string
  county_name: string
  state: string
  product_stage: string
}

export interface OwnerSummary {
  owner_id: number
  canonical_name: string
  entity_type: string
  parcel_count: number
  municipality: string | null
  aliases?: string[]
  verification_status?: string | null
  verification_reasoning?: string | null
  verified_at?: string | null
}

export interface OwnerParcel {
  pidn: string
  owner_full: string
  propadr: string | null
  class: string | null
  aprtotal: NumericLike
  acres: NumericLike
  saledt: string | null
  price: NumericLike
  school_dis: string | null
}

export interface DelinquencyRecord {
  pidn: string
  tax_year: number | string
  authority_name: string
  total: NumericLike
  property_address: string | null
}

export interface LinkedLicense {
  source_name: string
  source_address: string | null
  confidence: number | null
  match_tier: string | null
}

export interface WatchlistParcelSummary {
  pidn: string
  owner_full: string | null
  propadr: string | null
  municipality: string | null
  aprtotal: number | null
  class: string | null
  acres: number | null
  changed_at: string | null
  changed_recently: boolean
  has_tax_delinquency: boolean
  momentum_score: number | null
  top_signal: string | null
}

export interface WatchlistSummaryResponse {
  parcels: WatchlistParcelSummary[]
  missing: string[]
}

export interface OwnerBrief {
  brief_text: string
  portfolio_strategy: string | null
  concentration_notes: string | null
  key_pattern: string | null
  recommendation: string | null
  urgency: string | null
  top_risk: string | null
  evidence_strength: string | null
  citations: string[]
  parcel_citations: string[]
  citation_evidence: EvidenceItem[]
  n_parcels: number | null
  confidence: number | null
  n_trials: number | null
  trial_agreement: number | null
  model_version: string | null
  prompt_version: string | null
  brief_version: number | null
  generated_at: string | null
}

export interface EntityRelationship {
  [key: string]: string | number | boolean | null | undefined
}

export interface OwnerProfileResponse {
  owner: OwnerSummary
  relationships: EntityRelationship[]
  verification_evidence: EvidenceItem[]
  brief: OwnerBrief | null
  portfolio: {
    parcel_count: number
    total_assessed: number
    parcels: OwnerParcel[]
  }
  delinquency: {
    /** False when exact claim rows are withheld by the restricted-distress gate. */
    detail_available?: boolean
    total_owed: number
    delinquent_parcels: number
    records: DelinquencyRecord[]
  }
  licenses: LinkedLicense[]
}

export interface ParcelFeatureProperties {
  pidn: string
  owner_full: string | null
  propadr: string | null
  aprtotal: number | null
  municipality: string | null
  class: string | null
  school_dis?: string | null
  saledt: string | null
  price: number | null
  has_tax_delinquency?: boolean
}

export type ParcelFeatureCollection = GeoJSON.FeatureCollection<
  GeoJSON.Geometry,
  ParcelFeatureProperties
>

export interface ZoningProperties {
  muni_name?: string | null
  zcode?: string | null
  zname?: string | null
  ztype?: string | null
  gen_zcode?: string | null
  gen_zname?: string | null
}

export interface MunicipalityProperties {
  name: string
  muni_type?: string | null
  county?: string | null
}

export interface FloodZoneProperties {
  fld_zone?: string | null
  zone_subty?: string | null
  sfha_tf?: string | null
  fld_ar_id?: string | null
}

export interface PenndotProjectProperties {
  project_id?: string | null
  project_name?: string | null
  description?: string | null
  status?: string | null
  start_date?: string | null
  end_date?: string | null
  cost?: number | null
  project_type?: string | null
  location_desc?: string | null
  project_manager?: string | null
  manager_email?: string | null
  under_construction?: string | null
  act89_status?: string | null
}

export interface ParcelRecord {
  pidn: string
  owner_id: number | null
  owner_full: string | null
  own_name1: string | null
  own_name2: string | null
  prev_owner: string | null
  propadr: string | null
  mail_addr_full: string | null
  municipality: string | null
  school_dis: string | null
  class: string | null
  luc: string | null
  acres: NumericLike
  style: string | null
  num_stories: NumericLike
  res_living_area: NumericLike
  yrblt: NumericLike
  heatsys: number | null
  fuel: number | null
  clean_green: string | null
  grade: string | null
  cdu: string | null
  aprland: number | null
  aprbldg: number | null
  aprtotal: number | null
  saledt: string | null
  price: number | null
  prev_price: number | null
  deed_bk: NumericLike
  deed_pg: NumericLike
  comm_struc: string | null
  comm_year_built: NumericLike
  comm_building_sq_ft: NumericLike
  lat: number | null
  lng: number | null
}

export interface TaxDelinquencyRecord {
  tax_year: number | null
  authority_name: string
  tax_owed: number | null
  penalty_owed: number | null
  interest_owed: number | null
  fees_owed: number | null
  total: number | null
}

export type PropertyTaxDelinquencyRecord = TaxDelinquencyRecord

export interface TaxDelinquency {
  detail_available: boolean
  is_delinquent: boolean
  total_owed: number | null
  records: TaxDelinquencyRecord[]
}

export interface FloodZoneInfo {
  in_flood_zone: boolean
  zone: string | null
  sfha: boolean
  overlap_pct: number | null
}

export interface SoilUnit {
  source_record_ids: number[]
  map_unit_key: string | null
  map_unit_symbol: string | null
  map_unit_name: string | null
  drainage: string | null
  capability_class: number | null
  permeability: number | null
  septic_rating: string | null
  slope_low: number | null
  slope_high: number | null
  representative_slope: number | null
  hydric_rating: string | null
  hydrologic_group: string | null
  relative_value: string | null
  coverage_pct: number
}

export interface SoilProfile {
  mapped_coverage_pct: number
  units: SoilUnit[]
  considerations: string[]
  source_record_ids: number[]
  source_url: string | null
  evidence?: EvidenceItem
}

export interface StructureBuilding {
  type: string
  sqm: number
  sqft: number
}

export interface ParcelStructures {
  count: number
  likely_vacant: boolean
  buildings: StructureBuilding[]
}

export interface ReasonSignal {
  key: string
  label: string
  weight: number
  is_direct: boolean
  is_risk: boolean
}

export type DevelopmentSignalValue =
  string | number | boolean | string[] | number[] | null | undefined
export type DevelopmentSignalEvidence = Record<string, unknown>

export interface SignalFact {
  label: string
  value: string
}

export interface SignalPresentation {
  title: string
  summary: string
  interpretation: string | null
  caveat: string | null
  facts: SignalFact[]
  score_impacts: {
    momentum: number
    opportunity: number
    site_screening: number
  }
  affects_eligibility: boolean
}

export interface DevelopmentSignal {
  weight?: number
  evidence?: DevelopmentSignalEvidence
  presentation?: SignalPresentation
  evidence_receipt?: EvidenceItem
  [key: string]: unknown
}

export interface DevelopmentMomentum {
  score: number
  opportunity_score: number
  site_readiness_score: number
  has_active_plan: boolean
  eligible: boolean
  exclusion_reasons: string[]
  signals: Record<string, DevelopmentSignal>
  top_signal: string | null
  signal_count: number
  score_version: number | null
  computed_at: string | null
  reason_signals: ReasonSignal[]
}

export interface ParcelBrief {
  brief_text: string
  recommendation: 'investigate' | 'watch' | 'insufficient_evidence' | null
  assessment: string | null
  assessment_reasoning: string | null
  key_questions: string[]
  signal_count: number | null
  citations: string[]
  citation_evidence: EvidenceItem[]
  brief_version: number | null
  generated_at: string | null
}

export interface CountyNarrative {
  narrative_id: number
  title: string
  body: string
  narrative_type: string
  trajectory: string | null
  key_entities: string[]
  citations: string[]
  citation_evidence: EvidenceItem[]
  generated_at: string | null
}

export interface IntelligenceSummary {
  cross_signal_insight: string | null
  last_run_at: string | null
  signals_validated_count: number | null
}

export interface LinkedProceeding {
  decision_scope?: string | null
  proceeding_id: number
  body_name: string | null
  meeting_date: string | null
  proceeding_type: string | null
  extraction_type: string | null
  applicant_name: string | null
  decision: string | null
  current_zoning: string | null
  proposed_zoning: string | null
  supporting_text: string | null
  document_url: string | null
  extraction_confidence: number | null
  page_number: number | null
  match_type: 'pidn' | 'address'
  evidence: EvidenceItem
}

export type IntelligenceCategory = 'parcel' | 'development'
export type IntelligenceInterpretationKind = 'deterministic' | 'llm'

export interface EvidenceItem {
  evidence_id: string
  citation_key: string
  label: string
  source_kind: string
  source_record_id: string | null
  url: string | null
  document_url: string | null
  internal_url: string | null
  excerpt: string | null
  details: Record<string, unknown>
  effective_at: string | null
  observed_at: string | null
  method: string
  caveat: string | null
  confidence: number | null
}

export type IntelligenceSource = EvidenceItem

export interface IntelligenceProject {
  key: string
  name: string
}

export interface IntelligenceEntityLink {
  owner_id: number
  name: string
  matched_name: string
  verification_status: string | null
}

export interface IntelligenceEvent {
  event_key: string
  category: IntelligenceCategory
  event_type: string
  event_tags: string[]
  title: string
  what_happened: string
  event_date: string | null
  detected_at: string
  confidence: number | null
  municipality: string | null
  project: IntelligenceProject | null
  related_entities: string[]
  entity_links: IntelligenceEntityLink[]
  related_pidns: string[]
  importance_score: number
  importance_reasons: string[]
  sources: IntelligenceSource[]
  interpretation: {
    kind: IntelligenceInterpretationKind
    model: string | null
    generated_at: string | null
  }
}

export interface IntelligenceFeedResponse {
  events: IntelligenceEvent[]
  limit: number
  offset: number
  has_more: boolean
}

export interface ZoningInfo {
  code: string | null
  name: string | null
  type: string | null
  general_code: string | null
  general_name: string | null
  municipality: string | null
  ordinance: string | null
  adopted: string | null
  source_url: string | null
}

export interface NearbyParcel {
  pidn: string
  propadr: string | null
  municipality: string | null
  class: string | null
  acres: number | null
  aprtotal: number | null
  saledt: string | null
  price: number | null
  distance_m: number | null
  lat: number | null
  lng: number | null
  owner_label: string | null
  owner_kind: string
  owner_id: number | null
  has_tax_delinquency: boolean | null
  likely_vacant: boolean
  opportunity_score: number | null
  momentum_score: number | null
  site_readiness_score: number | null
  top_signal: string | null
  has_active_plan: boolean
}

export interface NearbyParcelsResponse {
  anchor_pidns: string[]
  anchor_lat: number | null
  anchor_lng: number | null
  radius_m: number
  count: number
  parcels: NearbyParcel[]
}

export interface PropertyReport {
  parcel: ParcelRecord
  tax_delinquency: TaxDelinquency
  flood_zone: FloodZoneInfo
  soil_profile: SoilProfile
  structures: ParcelStructures
  zoning?: ZoningInfo | null
  development_momentum: DevelopmentMomentum | null
  parcel_brief: ParcelBrief | null
  related_narratives: CountyNarrative[]
  intelligence_summary: IntelligenceSummary | null
  linked_proceedings: LinkedProceeding[]
  evidence: EvidenceItem[]
}

export interface MunicipalityProfile {
  name: string
  muni_type: string | null
  county: string | null
  stats: MunicipalityStats
  delinquency: MunicipalityDelinquency
  licenses: LicenseRecord[]
  development_pipeline?: MunicipalityPipeline | null
  radar_top?: MunicipalityRadarTop[]
}

export interface MunicipalityPipelineMatter {
  event_key: string
  event_type: string
  title: string
  event_date: string | null
  project_key: string | null
  project_name: string | null
  related_pidns: string[]
}

export interface MunicipalityPipeline {
  policy?: MunicipalityPipelineMatter[]
  window_days: number
  total_matters: number
  by_event_type: { event_type: string; count: number }[]
  upcoming: MunicipalityPipelineMatter[]
  recent: MunicipalityPipelineMatter[]
}

export interface MunicipalityRadarTop {
  pidn: string
  propadr: string | null
  acres: number | null
  opportunity_score: number
  score: number
  top_signal: string | null
  opportunity_delta: number | null
  is_new: boolean
}

export interface MunicipalityStats {
  parcel_count: number
  total_assessed: number
}

export interface MunicipalityDelinquency {
  delinquent_parcels: number
  total_delinquent: number
  oldest_delinquent_year: number | null
  delinquent_years: number
}

export interface MunicipalitySummary {
  name: string
  muni_type: string
  delinquent_parcels: number
  total_delinquent: number
}

export interface LicenseRecord {
  licensee: string | null
  premises_name: string | null
  premises_address: string | null
  license_type: string
  status?: string
  municipality?: string
  last_issue_date?: string | null
  expiration_date?: string | null
}

export type RadarViewMode = 'opportunity' | 'momentum' | 'readiness'
export type RadarMoversDirection = 'up' | 'down' | 'new'

export interface RadarParcel {
  pidn: string
  score: number
  top_signal: string | null
  signal_count: number
  signals: Record<string, DevelopmentSignal> | null
  eligible: boolean
  has_active_plan?: boolean
  site_readiness_score?: number
  score_version: number | null
  computed_at: string | null
  owner_full: string | null
  propadr: string | null
  municipality: string | null
  acres: number | null
  aprtotal: number | null
  class: string | null
  reason_signals: ReasonSignal[]
  previous_score?: number | null
  previous_opportunity_score?: number | null
  score_delta?: number | null
  opportunity_delta?: number | null
  previous_computed_at?: string | null
  is_new?: boolean
}

export interface RadarMoversResponse {
  count: number
  view: 'opportunity' | 'momentum'
  direction: RadarMoversDirection
  previous_computed_at: string | null
  parcels: RadarParcel[]
}

export interface RadarParcelListResponse {
  count: number
  parcels: RadarParcel[]
  coverage?: {
    loaded_count: number
    total_count: number
    loaded_layers: string[]
    missing_layers: string[]
  }
}

export interface RadarBboxItem {
  pidn: string
  score: number
  eligible: boolean
  top_signal: string | null
  lng: number | null
  lat: number | null
}

export interface RadarBboxResponse {
  count: number
  limit: number
  truncated: boolean
  parcels: RadarBboxItem[]
}

export interface RadarMunicipalitiesResponse {
  municipalities: string[]
}

export type SearchMode = 'fuzzy' | 'smart' | 'redirect' | 'aggregate'
export type SearchScalar = string | number | boolean | null

export type SearchResult = {
  result_type?: string
  title?: string
  subtitle?: string
  lat?: number | null
  lng?: number | null
  score?: number
  pidn?: string
  _link?: string
} & Record<string, SearchScalar | undefined>

export interface SearchResponse {
  mode: SearchMode
  description?: string
  redirect_path?: string
  results: SearchResult[]
  label?: string
  value?: string
  format?: string
}

export interface ProjectStatusItem {
  event_key: string
  evidence_id: string
  record_date: string | null
  text: string
  status: string
  date?: string | null
  kind?: string | null
}
export interface ProjectDecision {
  event_key: string
  evidence_id: string
  record_date: string | null
  decision: string
  body: string | null
  matter: string | null
  scope?: string | null
}

export interface ProjectCaseResponse extends IntelligenceFeedResponse {
  summary: {
    status: string
    as_of: string | null
    latest_event_key: string | null
    latest_change: string | null
    decisions: ProjectDecision[]
    conditions: ProjectStatusItem[]
    milestones: ProjectStatusItem[]
    history_incomplete: boolean
    caveat: string
  }
}
