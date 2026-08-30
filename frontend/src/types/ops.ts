export type SourceHealthStatus = 'green' | 'red'
export type OverallHealthStatus = SourceHealthStatus | 'yellow'

export interface SourceStatus {
  status: SourceHealthStatus
  record_count: number
  configured_count?: number
  active_count?: number
  healthy_count?: number
  blocked_count?: number
  unchecked_count?: number
  conditional_count?: number
  paused_count?: number
  overdue_count?: number
  due_soon_count?: number
  next_review_on?: string | null
}

export interface HealthData {
  overall: OverallHealthStatus
  sources: Record<string, SourceStatus>
  summary: string
}

export interface StatsData {
  total_records: number
  parcel_count: number
  municipality_count: number
  delinquent_parcels: number
  total_delinquent: number
  flood_zone_count: number
  liquor_license_count: number
  address_point_count: number
  structure_count: number
  total_assessed: number
  county_tax_owed: number
  school_tax_owed: number
  municipal_tax_owed: number
  oldest_delinquent_year: number | null
  districts_affected: number
  tax_claim_report_date: string | null
}
