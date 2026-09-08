import type { EvidenceItem } from './api'

export type HypothesisFamily =
  | 'business_expansion'
  | 'land_assembly'
  | 'construction_timing'
  | 'infrastructure_unlock'
  | 'use_transition'
  | 'project_stall'

export type HypothesisStatus =
  'early_signal' | 'supported' | 'weakened' | 'closed' | 'insufficient_evidence'

export type OpportunityAudience = 'investor' | 'service_business'
export type ActionReadiness = 'research' | 'qualify' | 'act' | 'wait' | 'closed'
export type ProjectType =
  'industrial' | 'logistics' | 'housing' | 'mixed_use' | 'commercial' | 'infrastructure'

export interface IntelligenceAlternative {
  explanation: string
  why_plausible: string
  distinguishing_check: string
}

export interface IntelligenceNextCheck {
  question: string
  source_to_check: string
  why_it_changes_the_case: string
}

export interface IntelligenceOpportunity {
  opportunity_key: string
  audience: OpportunityAudience
  services: string[]
  title: string
  rationale: string
  next_action: string
  target_role: string
  readiness: ActionReadiness
  blockers: string[]
  disqualifiers: string[]
  commercial_basis: { need: string; timing: string; qualification_route: string } | null
}

export interface EmergingProperty {
  pidn: string
  address: string | null
  owner: string | null
  acres: number | null
  relationship: 'subject' | 'adjoining'
}

export interface EmergingCase {
  case_key: string
  family: HypothesisFamily
  title: string
  hypothesis: string
  status: HypothesisStatus
  evidence_strength: 'limited' | 'moderate' | 'strong'
  stage: string
  supporting_facts: string[]
  contrary_evidence: string[]
  alternatives: IntelligenceAlternative[]
  unknowns: string[]
  next_checks: IntelligenceNextCheck[]
  opportunities: IntelligenceOpportunity[]
  implications: IntelligenceOpportunity[]
  project_types: ProjectType[]
  municipalities: string[]
  properties: EmergingProperty[]
  source_document_count: number
  latest_record_date: string | null
  assessed_at: string
  as_of: string
  scope_note: string
  change_summary: string | null
  revision: string
  citation_evidence: EvidenceItem[]
  activity_links: Array<{ label: string; path: string }>
}

export interface EmergingCoverage {
  available_records: number
  assessed_scopes: number
  current_cases: number
  awaiting_refresh: number
  note: string
  missing_source_families: string[]
}

export interface EmergingResponse {
  cases: EmergingCase[]
  total: number
  coverage: EmergingCoverage
}

export interface IntelligenceProfile {
  audience: OpportunityAudience | 'all'
  municipalities: string[]
  services: string[]
  families: HypothesisFamily[]
  project_types?: ProjectType[]
  preferred_readiness?: ActionReadiness[]
}

export interface IntelligenceWorkItem {
  case_key: string
  status: 'saved' | 'qualifying' | 'waiting' | 'acted' | 'rejected'
  note: string
  last_seen_revision: string
  updated_at: string
}
