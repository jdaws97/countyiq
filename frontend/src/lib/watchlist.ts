import { commitBrowserStorage, workspaceStorageKey } from './browserStorage'

/** Guest watches stay in the browser; verified accounts use an isolated cache. */

const STORAGE_KEY = 'countyiq_watchlist_v1'
const PROJECT_STORAGE_KEY = 'countyiq_project_watchlist_v1'
const ENTITY_STORAGE_KEY = 'countyiq_entity_watchlist_v1'
const MUNICIPALITY_STORAGE_KEY = 'countyiq_municipality_watchlist_v1'
export const WATCHLIST_CAP = 50

export interface WatchedProject {
  key: string
  name: string
}

export interface WatchedEntity {
  id: number
  name: string
}

export interface WatchedMunicipality {
  name: string
}

function read(): string[] {
  try {
    const raw = localStorage.getItem(workspaceStorageKey(STORAGE_KEY))
    if (!raw) {
      return []
    }
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) {
      return []
    }
    return parsed.filter((p): p is string => typeof p === 'string')
  } catch {
    return []
  }
}

function writeWatchlist(key: string, value: unknown): boolean {
  try {
    commitBrowserStorage({ [key]: JSON.stringify(value) })
    window.dispatchEvent(new Event('countyiq-watchlist-changed'))
    return true
  } catch {
    window.alert('Could not save this change. Browser storage is full or unavailable.')
    return false
  }
}

function write(pidns: string[]): boolean {
  return writeWatchlist(STORAGE_KEY, pidns)
}

function readProjects(): WatchedProject[] {
  try {
    const raw = localStorage.getItem(workspaceStorageKey(PROJECT_STORAGE_KEY))
    if (!raw) {
      return []
    }
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) {
      return []
    }
    return parsed.filter(
      (project): project is WatchedProject =>
        typeof project === 'object' &&
        project !== null &&
        typeof (project as WatchedProject).key === 'string' &&
        typeof (project as WatchedProject).name === 'string',
    )
  } catch {
    return []
  }
}

function writeProjects(projects: WatchedProject[]): boolean {
  return writeWatchlist(PROJECT_STORAGE_KEY, projects)
}

function readEntities(): WatchedEntity[] {
  try {
    const raw = localStorage.getItem(workspaceStorageKey(ENTITY_STORAGE_KEY))
    if (!raw) {
      return []
    }
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) {
      return []
    }
    return parsed.filter(
      (entity): entity is WatchedEntity =>
        typeof entity === 'object' &&
        entity !== null &&
        Number.isInteger((entity as WatchedEntity).id) &&
        typeof (entity as WatchedEntity).name === 'string',
    )
  } catch {
    return []
  }
}

function writeEntities(entities: WatchedEntity[]): boolean {
  return writeWatchlist(ENTITY_STORAGE_KEY, entities)
}

function readMunicipalities(): WatchedMunicipality[] {
  try {
    const raw = localStorage.getItem(workspaceStorageKey(MUNICIPALITY_STORAGE_KEY))
    if (!raw) {
      return []
    }
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) {
      return []
    }
    return parsed.filter(
      (municipality): municipality is WatchedMunicipality =>
        typeof municipality === 'object' &&
        municipality !== null &&
        typeof (municipality as WatchedMunicipality).name === 'string' &&
        (municipality as WatchedMunicipality).name.trim().length > 0,
    )
  } catch {
    return []
  }
}

function writeMunicipalities(municipalities: WatchedMunicipality[]): boolean {
  return writeWatchlist(MUNICIPALITY_STORAGE_KEY, municipalities)
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
    return !write(current.filter((p) => p !== pidn))
  }
  if (current.length >= WATCHLIST_CAP) {
    window.alert(
      `Parcel watchlist is limited to ${WATCHLIST_CAP} items. Remove one before adding another.`,
    )
    return false
  }
  return write([pidn, ...current])
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
    return !writeProjects(current.filter((item) => item.key !== project.key))
  }
  if (current.length >= WATCHLIST_CAP) {
    window.alert(
      `Project watchlist is limited to ${WATCHLIST_CAP} items. Remove one before adding another.`,
    )
    return false
  }
  return writeProjects([project, ...current])
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
    return !writeEntities(current.filter((item) => item.id !== entity.id))
  }
  if (current.length >= WATCHLIST_CAP) {
    window.alert(
      `Entity watchlist is limited to ${WATCHLIST_CAP} items. Remove one before adding another.`,
    )
    return false
  }
  return writeEntities([entity, ...current])
}

export function getMunicipalityWatchlist(): WatchedMunicipality[] {
  return readMunicipalities()
}

export function isMunicipalityWatched(name: string): boolean {
  return readMunicipalities().some((municipality) => municipality.name === name)
}

export function toggleMunicipalityWatch(municipality: WatchedMunicipality): boolean {
  const current = readMunicipalities()
  if (current.some((item) => item.name === municipality.name)) {
    return !writeMunicipalities(current.filter((item) => item.name !== municipality.name))
  }
  if (current.length >= WATCHLIST_CAP) {
    window.alert(
      `Municipality watchlist is limited to ${WATCHLIST_CAP} items. Remove one before adding another.`,
    )
    return false
  }
  return writeMunicipalities([municipality, ...current])
}

export function watchlistStorageEntries({
  parcels,
  projects,
  entities,
  municipalities = [],
}: {
  parcels: string[]
  projects: WatchedProject[]
  entities: WatchedEntity[]
  municipalities?: WatchedMunicipality[]
}): Record<string, string> {
  const nextParcels = Array.from(new Set(parcels.filter((pidn) => typeof pidn === 'string')))
  const nextProjects = Array.from(
    new Map(
      projects
        .filter(
          (project) =>
            project && typeof project.key === 'string' && typeof project.name === 'string',
        )
        .map((project) => [project.key, project]),
    ).values(),
  )
  const nextEntities = Array.from(
    new Map(
      entities
        .filter(
          (entity) => entity && Number.isInteger(entity.id) && typeof entity.name === 'string',
        )
        .map((entity) => [entity.id, entity]),
    ).values(),
  )
  const nextMunicipalities = Array.from(
    new Map(
      municipalities
        .filter(
          (municipality) =>
            municipality &&
            typeof municipality.name === 'string' &&
            municipality.name.trim().length > 0,
        )
        .map((municipality) => [municipality.name, { name: municipality.name }]),
    ).values(),
  )
  if (
    nextParcels.length > WATCHLIST_CAP ||
    nextProjects.length > WATCHLIST_CAP ||
    nextEntities.length > WATCHLIST_CAP ||
    nextMunicipalities.length > WATCHLIST_CAP
  ) {
    throw new Error(`Workspace exceeds the ${WATCHLIST_CAP}-item limit for a watchlist.`)
  }
  return {
    [STORAGE_KEY]: JSON.stringify(nextParcels),
    [PROJECT_STORAGE_KEY]: JSON.stringify(nextProjects),
    [ENTITY_STORAGE_KEY]: JSON.stringify(nextEntities),
    [MUNICIPALITY_STORAGE_KEY]: JSON.stringify(nextMunicipalities),
  }
}

/** Query params that rank locally watched subjects first without filtering the feed. */
export function watchBoostParams(): Record<string, string> {
  const params: Record<string, string> = {}
  const pidns = getWatchlist()
  if (pidns.length) {
    params.boost_pidns = pidns.join(',')
  }
  const projects = getProjectWatchlist().map((project) => project.key)
  if (projects.length) {
    params.boost_project_keys = projects.join(',')
  }
  const entities = getEntityWatchlist().map((entity) => String(entity.id))
  if (entities.length) {
    params.boost_entity_ids = entities.join(',')
  }
  const municipalities = getMunicipalityWatchlist().map((municipality) => municipality.name)
  if (municipalities.length) {
    params.boost_municipalities = municipalities.join(',')
  }
  return params
}
