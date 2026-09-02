import type { RadarViewMode } from '../types/api'

const TRIAGE_KEY = 'countyiq_event_triage_v1'
const LAST_FEED_KEY = 'countyiq_last_feed_visit_v1'
const LAST_WATCH_KEY = 'countyiq_last_watch_visit_v1'
const SAVED_SEARCH_KEY = 'countyiq_saved_searches_v1'
const COMPARE_KEY = 'countyiq_compare_v1'

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
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function setStoredValue(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
  } catch {
    // Investigation tools remain usable for the current page without persistence.
  }
}

function removeStoredValue(key: string): void {
  try {
    localStorage.removeItem(key)
  } catch {
    // Storage can be unavailable in hardened/private browser contexts.
  }
}

function parseJson<T>(key: string, fallback: T): T {
  try {
    const raw = getStoredValue(key)
    return raw ? JSON.parse(raw) as T : fallback
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
  return parseJson<Record<string, TriageStatus>>(TRIAGE_KEY, {})
}

export function setEventTriage(eventKey: string, status: TriageStatus | null): void {
  const current = getEventTriage()
  if (status) current[eventKey] = status
  else delete current[eventKey]
  setStoredValue(TRIAGE_KEY, JSON.stringify(current))
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

export function getSavedSearches(): SavedSearch[] {
  return parseJson<SavedSearch[]>(SAVED_SEARCH_KEY, []).filter((item) => item && typeof item.path === 'string')
}

export function saveSearch(name: string, kind: SavedSearch['kind'], path: string): SavedSearch {
  const saved: SavedSearch = {
    id: `${kind}-${Date.now()}`,
    name,
    kind,
    path,
    createdAt: new Date().toISOString(),
  }
  setStoredValue(SAVED_SEARCH_KEY, JSON.stringify([saved, ...getSavedSearches()].slice(0, 20)))
  emit()
  return saved
}

export function removeSavedSearch(id: string): void {
  setStoredValue(SAVED_SEARCH_KEY, JSON.stringify(getSavedSearches().filter((item) => item.id !== id)))
  emit()
}

export function getComparison(): string[] {
  return parseJson<string[]>(COMPARE_KEY, []).filter((pidn) => typeof pidn === 'string').slice(0, 4)
}

export function isCompared(pidn: string): boolean {
  return getComparison().includes(pidn)
}

export function toggleComparison(pidn: string): { selected: boolean; full: boolean } {
  const current = getComparison()
  if (current.includes(pidn)) {
    setStoredValue(COMPARE_KEY, JSON.stringify(current.filter((item) => item !== pidn)))
    emit()
    return { selected: false, full: false }
  }
  if (current.length >= 4) return { selected: false, full: true }
  setStoredValue(COMPARE_KEY, JSON.stringify([...current, pidn]))
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
  savedSearches: SavedSearch[]
  comparison: string[]
  triage: Record<string, TriageStatus>
}

export function replaceInvestigationState(workspace: PortableWorkspace): void {
  setStoredValue(SAVED_SEARCH_KEY, JSON.stringify((workspace.savedSearches ?? []).slice(0, 20)))
  setStoredValue(COMPARE_KEY, JSON.stringify((workspace.comparison ?? []).slice(0, 4)))
  setStoredValue(TRIAGE_KEY, JSON.stringify(workspace.triage ?? {}))
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
  return rows.map((row) => row.map((value) => {
    const text = value == null ? '' : String(value)
    return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
  }).join(',')).join('\n')
}

export function radarSearchName(view: RadarViewMode | 'movers', municipality: string, minScore: string): string {
  const location = municipality || 'All municipalities'
  if (view === 'movers') return `${location} · movers ${minScore}+ points`
  return `${location} · ${view === 'readiness' ? 'site screening' : view} ${minScore}+`
}
