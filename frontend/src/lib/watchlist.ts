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
    localStorage.setItem(STORAGE_KEY, JSON.stringify(pidns))
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
    localStorage.setItem(PROJECT_STORAGE_KEY, JSON.stringify(projects))
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
    localStorage.setItem(ENTITY_STORAGE_KEY, JSON.stringify(entities))
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
  if (current.length >= WATCHLIST_CAP) {
    window.alert(`Parcel watchlist is limited to ${WATCHLIST_CAP} items. Remove one before adding another.`)
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
  if (current.length >= WATCHLIST_CAP) {
    window.alert(`Project watchlist is limited to ${WATCHLIST_CAP} items. Remove one before adding another.`)
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
  if (current.length >= WATCHLIST_CAP) {
    window.alert(`Entity watchlist is limited to ${WATCHLIST_CAP} items. Remove one before adding another.`)
    return false
  }
  writeEntities([entity, ...current])
  return true
}

export function replaceWatchlists({
  parcels,
  projects,
  entities,
}: {
  parcels: string[]
  projects: WatchedProject[]
  entities: WatchedEntity[]
}): void {
  const nextParcels = Array.from(new Set(parcels.filter((pidn) => typeof pidn === 'string')))
  const nextProjects = Array.from(new Map(
    projects
      .filter((project) => project && typeof project.key === 'string' && typeof project.name === 'string')
      .map((project) => [project.key, project]),
  ).values())
  const nextEntities = Array.from(new Map(
    entities
      .filter((entity) => entity && Number.isInteger(entity.id) && typeof entity.name === 'string')
      .map((entity) => [entity.id, entity]),
  ).values())
  if (nextParcels.length > WATCHLIST_CAP || nextProjects.length > WATCHLIST_CAP || nextEntities.length > WATCHLIST_CAP) {
    throw new Error(`Workspace exceeds the ${WATCHLIST_CAP}-item limit for a watchlist.`)
  }
  write(nextParcels)
  writeProjects(nextProjects)
  writeEntities(nextEntities)
}

/** Query params that rank locally watched subjects first without filtering the feed. */
export function watchBoostParams(): Record<string, string> {
  const params: Record<string, string> = {}
  const pidns = getWatchlist()
  if (pidns.length) params.boost_pidns = pidns.join(',')
  const projects = getProjectWatchlist().map((project) => project.key)
  if (projects.length) params.boost_project_keys = projects.join(',')
  const entities = getEntityWatchlist().map((entity) => String(entity.id))
  if (entities.length) params.boost_entity_ids = entities.join(',')
  return params
}
