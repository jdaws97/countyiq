export type SourceHealthStatus = 'green' | 'red'
export type OverallHealthStatus = SourceHealthStatus | 'yellow'
export type JobRunHealthStatus = 'success' | 'failure' | 'unknown'
export type SourceHealthReason =
  | 'healthy'
  | 'empty_source'
  | 'last_run_failed'
  | 'missing_table'
  | 'policy_overdue'
  | 'query_failed'
  | 'run_not_observed'
  | 'source_unhealthy'
  | 'stale'

export interface SourceStatus {
  status: SourceHealthStatus
  record_count: number
  status_reason?: SourceHealthReason
  refresh_job?: string
  freshness_basis?: 'asset' | 'job'
  expected_refresh_hours?: number
  last_run_status?: JobRunHealthStatus
  last_run_job?: string
  last_run_at?: string | null
  last_success_at?: string | null
  freshness_due_at?: string | null
  stale?: boolean
  configured_count?: number
  active_count?: number
  healthy_count?: number
  blocked_count?: number
  unchecked_count?: number
  stale_count?: number
  last_checked_at?: string | null
  oldest_checked_at?: string | null
  conditional_count?: number
  paused_count?: number
  overdue_count?: number
  due_soon_count?: number
  next_review_on?: string | null
}

export type IntelligenceIntegrityReason =
  | 'healthy'
  | 'unresolved_contradictions'
  | 'recent_validation_rejections'
  | 'stale_contradictions'
  | 'projection_unlinked'
  | 'projection_mismatch'
  | 'missing_table'
  | 'query_failed'

export interface IntelligenceIntegrityStatus {
  status: OverallHealthStatus
  status_reason: IntelligenceIntegrityReason
  history_count: number
  accepted_count: number
  quarantined_count: number
  human_resolution_inference_count: number
  contradiction_count: number
  unresolved_contradiction_count: number
  resolved_contradiction_count: number
  oldest_unresolved_at: string | null
  projection_count: number
  unlinked_projection_count: number
  projection_mismatch_count: number
  validation_rejection_count: number
  validation_rejections_last_24h: number
  latest_validation_rejection_at: string | null
  max_unresolved_age_hours: number
}

export interface HealthData {
  overall: OverallHealthStatus
  sources: Record<string, SourceStatus>
  intelligence_integrity: IntelligenceIntegrityStatus
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
