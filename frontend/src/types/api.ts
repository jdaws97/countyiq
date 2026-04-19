export type NumericLike = number | string | null | undefined

export interface OwnerSummary {
  owner_id: number
  canonical_name: string
  entity_type: string
  parcel_count: number
  municipality: string | null
  source_mode?: 'entity_graph' | 'owner_resolution'
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

export interface OwnerProfileResponse {
  owner: OwnerSummary
  portfolio: {
    parcel_count: number
    total_assessed: number
    parcels: OwnerParcel[]
  }
  delinquency: {
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
  delinquent_total?: number | null
  years_delinquent?: number | null
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
  heatsys: string | null
  fuel: string | null
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
  owner_name: string | null
  property_address: string | null
}

export type PropertyTaxDelinquencyRecord = TaxDelinquencyRecord

export interface TaxDelinquency {
  is_delinquent: boolean
  total_owed: number
  records: TaxDelinquencyRecord[]
}

export interface FloodZoneInfo {
  in_flood_zone: boolean
  zone: string | null
  sfha: boolean
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

export type DevelopmentSignalValue = string | number | boolean | null | undefined
export type DevelopmentSignalEvidence = Record<string, DevelopmentSignalValue>

export interface DevelopmentSignal {
  weight?: number
  evidence?: DevelopmentSignalEvidence
  [key: string]: DevelopmentSignalValue | DevelopmentSignalEvidence
}

export interface DevelopmentMomentum {
  score: number
  opportunity_score: number
  has_active_plan: boolean
  eligible: boolean
  exclusion_reasons: string[]
  signals: Record<string, DevelopmentSignal>
  top_signal: string | null
  signal_count: number
  score_version: string | null
  computed_at: string | null
  reason_signals: ReasonSignal[]
}

export interface ParcelBrief {
  brief_text: string
  assessment: string | null
  assessment_reasoning: string | null
  key_questions: string[]
  signal_count: number | null
  citations: string[]
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
  generated_at: string | null
}

export interface IntelligenceSummary {
  cross_signal_insight: string | null
  last_run_at: string | null
  signals_validated_count: number | null
}

export interface LinkedProceeding {
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
  match_type: 'pidn' | 'address'
}

export type CountyFeedNarrative = CountyNarrative & { affected_pidns: string[] }

export interface CountyFeedResponse {
  narratives: CountyFeedNarrative[]
  limit: number
  offset: number
}

export interface PropertyReport {
  parcel: ParcelRecord
  tax_delinquency: TaxDelinquency
  flood_zone: FloodZoneInfo
  structures: ParcelStructures
  development_momentum: DevelopmentMomentum | null
  parcel_brief: ParcelBrief | null
  related_narratives: CountyNarrative[]
  intelligence_summary: IntelligenceSummary | null
  linked_proceedings: LinkedProceeding[]
}

export interface MunicipalityProfile {
  name: string
  muni_type: string
  county: string
  delinquency: {
    delinquent_parcels: number
    total_delinquent: number
    oldest_delinquent_year: number | null
    delinquent_years: number
  }
}

export interface MunicipalitySummary {
  name: string
  muni_type: string
  delinquent_parcels: number
  total_delinquent: number
}

export interface LicenseRecord {
  licensee: string
  premises_name: string | null
  premises_address: string | null
  license_type: string
  status?: string
  municipality?: string
  last_issue_date?: string | null
  expiration_date?: string | null
}

export interface MunicipalityLicenseResponse {
  licenses: LicenseRecord[]
}

export interface LicenseTypeSummary {
  license_type: string
  count: number
}

export interface LicenseListResponse {
  licenses: LicenseRecord[]
  type_summary: LicenseTypeSummary[]
  total: number
}

export interface TopDelinquentOwner {
  owner_name: string
  parcel_count: number
  total_owed: number
  oldest_year: number | null
  newest_year: number | null
  years_delinquent: number
  districts: string[]
}

export interface DelinquentParcelSummary {
  pidn: string
  owner_name: string
  address: string
  district: string
  years_delinquent: number
  total_owed: number
}

export interface DistressedParcel {
  pidn: string
  owner_full: string
  propadr: string | null
  class: string | null
  acres: number | null
  aprtotal: number | null
  saledt: string | null
  price: number | null
  school_dis: string | null
  years_delinquent: number | null
  total_owed: number | null
  vacant_score: number | null
  no_flood_score: number | null
  sheriff_score: number | null
  sheriff_judgment: number | null
  traffic_score: number | null
  delinquency_score: number | null
  sale_stage_score: number | null
  acreage_score: number | null
  value_score: number | null
  class_score: number | null
  hold_score: number | null
  distress_score: number
}

export interface DistressedResponse {
  count: number
  parcels: DistressedParcel[]
}

export interface AssemblageNeighbor {
  pidn: string
  owner: string
  address: string | null
  acres: NumericLike
  assessed: NumericLike
  class: string | null
  delinquent: boolean
  vacant: boolean
}

export interface AssemblageCluster {
  seed_pidn: string
  seed_owner: string
  seed_address: string | null
  seed_class: string | null
  school_dis: string | null
  seed_acres: number | null
  seed_assessed: number | null
  lat: number | null
  lng: number | null
  adjacent_count: number
  delinquent_neighbors: number
  vacant_neighbors: number
  different_owners: number
  total_neighbor_acres: number | null
  total_neighbor_assessed: number | null
  total_acres: number | null
  total_assessed: number | null
  unique_owners: number
  neighbors: AssemblageNeighbor[]
}

export interface AssemblageResponse {
  count: number
  clusters: AssemblageCluster[]
}

export type RadarViewMode = 'opportunity' | 'momentum'

export interface RadarParcel {
  pidn: string
  score: number
  top_signal: string | null
  signal_count: number
  signals: Record<string, DevelopmentSignal> | null
  eligible: boolean
  has_active_plan?: boolean
  score_version: string | null
  computed_at: string | null
  owner_full: string | null
  propadr: string | null
  municipality: string | null
  acres: number | null
  aprtotal: number | null
  class: string | null
  reason_signals: ReasonSignal[]
}

export interface RadarParcelResponse {
  count: number
  parcels: RadarParcel[]
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
