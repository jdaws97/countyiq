import { commitBrowserStorage, workspaceStorageKey } from './browserStorage'
import type { SiteInquiry } from '../types/siteIntake'

const KEY = 'countyiq_site_inquiries_v1'

export function isSiteInquiries(value: unknown): value is SiteInquiry[] {
  if (!Array.isArray(value) || value.length > 50) {
    return false
  }
  return (
    value.every((item) => {
      return (
        item &&
        typeof item === 'object' &&
        typeof item.id === 'string' &&
        /^[a-f0-9-]{36}$/.test(item.id) &&
        typeof item.pidn === 'string' &&
        /^[A-Za-z0-9_-]{1,100}$/.test(item.pidn) &&
        typeof item.label === 'string' &&
        item.label.length > 0 &&
        item.label.length <= 200 &&
        typeof item.proposed_use === 'string' &&
        item.proposed_use.length <= 2000 &&
        typeof item.note === 'string' &&
        item.note.length <= 4000 &&
        typeof item.questions === 'string' &&
        item.questions.length <= 4000 &&
        ['researching', 'ready_for_handoff', 'on_hold'].includes(item.status) &&
        (item.reviewed_revision === null || /^[a-f0-9]{64}$/.test(item.reviewed_revision)) &&
        typeof item.updated_at === 'string' &&
        Number.isFinite(Date.parse(item.updated_at))
      )
    }) && new Set(value.map((item) => item.id)).size === value.length
  )
}

export function getSiteInquiries(): SiteInquiry[] {
  const value: unknown = JSON.parse(localStorage.getItem(workspaceStorageKey(KEY)) ?? '[]')
  if (!isSiteInquiries(value)) {
    throw new Error(
      'Saved site inquiries could not be read. Export your workspace before replacing them.',
    )
  }
  return value
}

export function siteInquiryStorageEntries(items: SiteInquiry[]): Record<string, string> {
  if (!isSiteInquiries(items)) {
    throw new Error('Site inquiries must contain at most 50 valid entries.')
  }
  return { [KEY]: JSON.stringify(items) }
}

export function saveSiteInquiry(item: SiteInquiry): void {
  const items = getSiteInquiries()
  const next = [item, ...items.filter((previous) => previous.id !== item.id)]
  commitBrowserStorage(siteInquiryStorageEntries(next))
  window.dispatchEvent(new Event('countyiq-investigation-changed'))
}

export function removeSiteInquiry(id: string): void {
  commitBrowserStorage(
    siteInquiryStorageEntries(getSiteInquiries().filter((item) => item.id !== id)),
  )
  window.dispatchEvent(new Event('countyiq-investigation-changed'))
}
