import type { PropertyReport } from './api'

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
  scope_note: string
}
