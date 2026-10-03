import type { PropertyReport } from './api'

export type SiteQuestionKey =
  'identity' | 'zoning' | 'site_conditions' | 'utilities_access' | 'municipal_history'

export interface SiteQuestionReview {
  key: SiteQuestionKey
  status: 'open' | 'answered' | 'not_applicable'
  note: string
}

export interface SiteInquiry {
  id: string
  pidn: string
  label: string
  proposed_use: string
  note: string
  questions: string
  status: 'researching' | 'ready_for_handoff' | 'on_hold'
  reviewed_revision: string | null
  updated_at: string
  question_reviews?: SiteQuestionReview[]
}

export interface SiteIntakePacket {
  revision: string
  report: PropertyReport
  sources: Array<{
    key: string
    label: string
    status: 'current' | 'stale' | 'unknown'
    last_successful_run_at: string | null
  }>
  municipal_collection: Array<{
    body_name: string
    status: string
    checked_at: string | null
  }>
  questions: string[]
  review_topics?: Array<{ key: SiteQuestionKey; question: string }>
  scope_note: string
}
