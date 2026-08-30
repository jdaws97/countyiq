/**
 * Client-side watchlist — localStorage, no auth.
 *
 * Deliberately an MVP: validates the retention loop ("tell me when a parcel
 * I care about changes") before committing to Clerk + server-side watchlists.
 * The 50-item cap bounds localStorage and batch-query size until server-backed
 * watchlists and account-specific plan limits exist.
 */

const STORAGE_KEY = 'countyiq_watchlist_v1'
const PROJECT_STORAGE_KEY = 'countyiq_project_watchlist_v1'
const ENTITY_STORAGE_KEY = 'countyiq_entity_watchlist_v1'
export const WATCHLIST_CAP = 50

export interface WatchedProject {
  key: string
  name: string
}

export interface WatchedEntity {
  id: number
  name: string
}

function read(): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter((p): p is string => typeof p === 'string')
  } catch {
    return []
  }
}

function write(pidns: string[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(pidns.slice(0, WATCHLIST_CAP)))
    window.dispatchEvent(new Event('countyiq-watchlist-changed'))
  } catch {
    // Storage full/unavailable (private browsing) — watching just won't persist.
  }
}

function readProjects(): WatchedProject[] {
  try {
    const raw = localStorage.getItem(PROJECT_STORAGE_KEY)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter((project): project is WatchedProject => (
      typeof project === 'object'
      && project !== null
      && typeof (project as WatchedProject).key === 'string'
      && typeof (project as WatchedProject).name === 'string'
    ))
  } catch {
    return []
  }
}

function writeProjects(projects: WatchedProject[]): void {
  try {
    localStorage.setItem(PROJECT_STORAGE_KEY, JSON.stringify(projects.slice(0, WATCHLIST_CAP)))
    window.dispatchEvent(new Event('countyiq-watchlist-changed'))
  } catch {
    // Storage full/unavailable (private browsing) — watching just won't persist.
  }
}

function readEntities(): WatchedEntity[] {
  try {
    const raw = localStorage.getItem(ENTITY_STORAGE_KEY)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter((entity): entity is WatchedEntity => (
      typeof entity === 'object'
      && entity !== null
      && Number.isInteger((entity as WatchedEntity).id)
      && typeof (entity as WatchedEntity).name === 'string'
    ))
  } catch {
    return []
  }
}

function writeEntities(entities: WatchedEntity[]): void {
  try {
    localStorage.setItem(ENTITY_STORAGE_KEY, JSON.stringify(entities.slice(0, WATCHLIST_CAP)))
    window.dispatchEvent(new Event('countyiq-watchlist-changed'))
  } catch {
    // Storage full/unavailable (private browsing) — watching just won't persist.
  }
}

export function getWatchlist(): string[] {
  return read()
}

export function isWatched(pidn: string): boolean {
  return read().includes(pidn)
}

export function toggleWatch(pidn: string): boolean {
  const current = read()
  if (current.includes(pidn)) {
    write(current.filter((p) => p !== pidn))
    return false
  }
  write([pidn, ...current])
  return true
}

export function getProjectWatchlist(): WatchedProject[] {
  return readProjects()
}

export function isProjectWatched(projectKey: string): boolean {
  return readProjects().some((project) => project.key === projectKey)
}

export function toggleProjectWatch(project: WatchedProject): boolean {
  const current = readProjects()
  if (current.some((item) => item.key === project.key)) {
    writeProjects(current.filter((item) => item.key !== project.key))
    return false
  }
  writeProjects([project, ...current])
  return true
}

export function getEntityWatchlist(): WatchedEntity[] {
  return readEntities()
}

export function isEntityWatched(entityId: number): boolean {
  return readEntities().some((entity) => entity.id === entityId)
}

export function toggleEntityWatch(entity: WatchedEntity): boolean {
  const current = readEntities()
  if (current.some((item) => item.id === entity.id)) {
    writeEntities(current.filter((item) => item.id !== entity.id))
    return false
  }
  writeEntities([entity, ...current])
  return true
}
