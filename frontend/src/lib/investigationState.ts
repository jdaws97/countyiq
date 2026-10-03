import type { RadarViewMode } from '../types/api'
import { commitBrowserStorage, workspaceStorageKey } from './browserStorage'
import { watchlistStorageEntries } from './watchlist'
import type { IntelligenceProfile, IntelligenceWorkItem } from '../types/emerging'
import type { SiteInquiry } from '../types/siteIntake'
import { getSiteInquiries, isSiteInquiries, siteInquiryStorageEntries } from './siteInquiries'
import {
  getIntelligenceProfile,
  getIntelligenceWork,
  intelligenceStorageEntries,
  isIntelligenceProfile,
  isIntelligenceWork,
} from './intelligenceState'

const TRIAGE_KEY = 'countyiq_event_triage_v1'
const LAST_FEED_KEY = 'countyiq_last_feed_visit_v1'
const LAST_WATCH_KEY = 'countyiq_last_watch_visit_v1'
const SAVED_SEARCH_KEY = 'countyiq_saved_searches_v1'
const COMPARE_KEY = 'countyiq_compare_v1' // gitleaks:allow -- public localStorage name

export type TriageStatus = 'reviewed' | 'dismissed'

export interface SavedSearch {
  id: string
  name: string
  kind: 'feed' | 'radar'
  path: string
  createdAt: string
}

function getStoredValue(key: string): string | null {
  try {
    return localStorage.getItem(workspaceStorageKey(key))
  } catch {
    return null
  }
}

function setStoredValue(key: string, value: string): boolean {
  try {
    commitBrowserStorage({ [key]: value })
    return true
  } catch {
    return false
  }
}

function notifyStorageFailure(): void {
  window.alert('Could not save this change. Browser storage is full or unavailable.')
}

function removeStoredValue(key: string): void {
  try {
    localStorage.removeItem(workspaceStorageKey(key))
  } catch {
    // Storage can be unavailable in hardened/private browser contexts.
  }
}

function parseJson<T>(key: string, fallback: T): T {
  try {
    const raw = getStoredValue(key)
    return raw ? (JSON.parse(raw) as T) : fallback
  } catch {
    return fallback
  }
}

function emit(): void {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event('countyiq-investigation-changed'))
  }
}

export function getEventTriage(): Record<string, TriageStatus> {
  const value = parseJson<unknown>(TRIAGE_KEY, {})
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {}
  }
  return Object.fromEntries(
    Object.entries(value).filter(([, status]) => status === 'reviewed' || status === 'dismissed'),
  )
}

export function setEventTriage(eventKey: string, status: TriageStatus | null): void {
  const current = getEventTriage()
  if (status) {
    current[eventKey] = status
  } else {
    delete current[eventKey]
  }
  if (!setStoredValue(TRIAGE_KEY, JSON.stringify(current))) {
    return notifyStorageFailure()
  }
  emit()
}

export function getLastFeedVisit(): string | null {
  return getStoredValue(LAST_FEED_KEY)
}

export function setLastFeedVisit(value = new Date().toISOString()): void {
  setStoredValue(LAST_FEED_KEY, value)
}

export function getLastWatchVisit(): string | null {
  return getStoredValue(LAST_WATCH_KEY)
}

export function setLastWatchVisit(value = new Date().toISOString()): void {
  setStoredValue(LAST_WATCH_KEY, value)
}

function isSavedSearch(value: unknown): value is SavedSearch {
  if (!value || typeof value !== 'object') {
    return false
  }
  const item = value as Partial<SavedSearch>
  return (
    typeof item.id === 'string' &&
    typeof item.name === 'string' &&
    (item.kind === 'feed' || item.kind === 'radar') &&
    typeof item.path === 'string' &&
    /^\/(feed|radar)(\?[^#\\]*)?$/.test(item.path) &&
    typeof item.createdAt === 'string' &&
    Number.isFinite(Date.parse(item.createdAt))
  )
}

export function getSavedSearches(): SavedSearch[] {
  const value = parseJson<unknown>(SAVED_SEARCH_KEY, [])
  return Array.isArray(value) ? value.filter(isSavedSearch).slice(0, 20) : []
}

export function saveSearch(
  name: string,
  kind: SavedSearch['kind'],
  path: string,
): SavedSearch | null {
  const saved: SavedSearch = {
    id: `${kind}-${Date.now()}`,
    name,
    kind,
    path,
    createdAt: new Date().toISOString(),
  }
  if (
    !setStoredValue(SAVED_SEARCH_KEY, JSON.stringify([saved, ...getSavedSearches()].slice(0, 20)))
  ) {
    notifyStorageFailure()
    return null
  }
  emit()
  return saved
}

export function removeSavedSearch(id: string): void {
  if (
    !setStoredValue(
      SAVED_SEARCH_KEY,
      JSON.stringify(getSavedSearches().filter((item) => item.id !== id)),
    )
  ) {
    return notifyStorageFailure()
  }
  emit()
}

export function getComparison(): string[] {
  const value = parseJson<unknown>(COMPARE_KEY, [])
  return Array.isArray(value)
    ? [
        ...new Set(
          value.filter((pidn): pidn is string => typeof pidn === 'string' && pidn.length > 0),
        ),
      ].slice(0, 4)
    : []
}

export function isCompared(pidn: string): boolean {
  return getComparison().includes(pidn)
}

export function toggleComparison(pidn: string): { selected: boolean; full: boolean } {
  const current = getComparison()
  if (current.includes(pidn)) {
    if (!setStoredValue(COMPARE_KEY, JSON.stringify(current.filter((item) => item !== pidn)))) {
      notifyStorageFailure()
      return { selected: true, full: false }
    }
    emit()
    return { selected: false, full: false }
  }
  if (current.length >= 4) {
    return { selected: false, full: true }
  }
  if (!setStoredValue(COMPARE_KEY, JSON.stringify([...current, pidn]))) {
    notifyStorageFailure()
    return { selected: false, full: false }
  }
  emit()
  return { selected: true, full: false }
}

export function clearComparison(): void {
  removeStoredValue(COMPARE_KEY)
  emit()
}

export interface PortableWorkspace {
  version: 1
  exportedAt: string
  parcels: string[]
  projects: Array<{ key: string; name: string }>
  entities: Array<{ id: number; name: string }>
  /** Added after the first export format; older files simply omit it. */
  municipalities?: Array<{ name: string }>
  savedSearches: SavedSearch[]
  comparison: string[]
  triage: Record<string, TriageStatus>
  intelligenceProfile?: IntelligenceProfile
  intelligenceWork?: IntelligenceWorkItem[]
  siteInquiries?: SiteInquiry[]
}

/** Validate the entire portable format before any browser state changes. */
export function parseWorkspace(text: string): PortableWorkspace {
  const value: unknown = JSON.parse(text)
  if (!value || typeof value !== 'object') {
    throw new Error('Not a CountyIQ workspace file')
  }
  const w = value as PortableWorkspace
  const strings = (items: unknown): items is string[] =>
    Array.isArray(items) && items.every((item) => typeof item === 'string' && item.length > 0)
  if (
    w.version !== 1 ||
    (w.intelligenceProfile !== undefined && !isIntelligenceProfile(w.intelligenceProfile)) ||
    (w.intelligenceWork !== undefined && !isIntelligenceWork(w.intelligenceWork)) ||
    (w.siteInquiries !== undefined && !isSiteInquiries(w.siteInquiries)) ||
    !strings(w.parcels) ||
    !Array.isArray(w.projects) ||
    !w.projects.every(
      (p) => p && typeof p.key === 'string' && p.key.length > 0 && typeof p.name === 'string',
    ) ||
    !Array.isArray(w.entities) ||
    !w.entities.every(
      (e) => e && Number.isSafeInteger(e.id) && e.id > 0 && typeof e.name === 'string',
    ) ||
    (w.municipalities !== undefined &&
      (!Array.isArray(w.municipalities) ||
        !w.municipalities.every(
          (m) => m && typeof m.name === 'string' && m.name.trim().length > 0,
        ))) ||
    !Array.isArray(w.savedSearches) ||
    w.savedSearches.length > 20 ||
    !w.savedSearches.every(isSavedSearch) ||
    !strings(w.comparison) ||
    w.comparison.length > 4 ||
    !w.triage ||
    typeof w.triage !== 'object' ||
    Array.isArray(w.triage) ||
    !Object.values(w.triage).every((status) => status === 'reviewed' || status === 'dismissed')
  ) {
    throw new Error('Not a valid CountyIQ workspace file. Current browser data was kept.')
  }
  watchlistStorageEntries(w) // also enforce the per-watchlist caps
  return w
}

export function replaceWorkspace(workspace: PortableWorkspace): void {
  const valid = parseWorkspace(JSON.stringify(workspace))
  commitBrowserStorage({
    ...watchlistStorageEntries(valid),
    ...siteInquiryStorageEntries(valid.siteInquiries ?? getSiteInquiries()),
    ...intelligenceStorageEntries(
      valid.intelligenceProfile ?? getIntelligenceProfile(),
      valid.intelligenceWork ?? getIntelligenceWork(),
    ),
    [SAVED_SEARCH_KEY]: JSON.stringify(valid.savedSearches),
    [COMPARE_KEY]: JSON.stringify([...new Set(valid.comparison)]),
    [TRIAGE_KEY]: JSON.stringify(valid.triage),
  })
  window.dispatchEvent(new Event('countyiq-watchlist-changed'))
  emit()
}

export function downloadText(filename: string, text: string, type = 'text/plain'): void {
  const url = URL.createObjectURL(new Blob([text], { type }))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

export function toCsv(rows: Array<Array<string | number | boolean | null | undefined>>): string {
  return rows
    .map((row) =>
      row
        .map((value) => {
          let text = value == null ? '' : String(value)
          // Source names/addresses are untrusted text when opened in a spreadsheet.
          if (typeof value === 'string' && /^[\s]*[=+@-]|^[\t\r\n]/.test(text)) {
            text = `'${text}`
          }
          return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
        })
        .join(','),
    )
    .join('\n')
}

export function radarSearchName(
  view: RadarViewMode | 'movers',
  municipality: string,
  minScore: string,
): string {
  const location = municipality || 'All municipalities'
  if (view === 'movers') {
    return `${location} · movers ${minScore}+ points`
  }
  return `${location} · ${view === 'readiness' ? 'site screening' : view} ${minScore}+`
}

export interface RecentInvestigation {
  path: string
  label: string
  visitedAt: string
}
export function getRecentInvestigations(): RecentInvestigation[] {
  const value = parseJson<unknown>('countyiq_recent_investigations_v1', [])
  return Array.isArray(value)
    ? value
        .filter((item): item is RecentInvestigation =>
          Boolean(
            item &&
            typeof item.path === 'string' &&
            /^\/(property|project|entity|owner|municipalities)\/[A-Za-z0-9%:_.-]+$/.test(
              item.path,
            ) &&
            typeof item.label === 'string' &&
            typeof item.visitedAt === 'string',
          ),
        )
        .slice(0, 20)
    : []
}
export function recordInvestigation(path: string, label: string) {
  if (!/^\/(property|project|entity|owner|municipalities)\/[A-Za-z0-9%:_.-]+$/.test(path)) {
    return
  }
  const recent = getRecentInvestigations()
  if (recent[0]?.path === path) {
    return
  }
  const next = [
    { path, label: label.slice(0, 200), visitedAt: new Date().toISOString() },
    ...recent.filter((item) => item.path !== path),
  ].slice(0, 20)
  if (setStoredValue('countyiq_recent_investigations_v1', JSON.stringify(next))) {
    emit()
  }
}
