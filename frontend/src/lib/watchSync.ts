import {
  commitBrowserStorage,
  investigationStorageEntries,
  setWorkspaceAccount,
} from './browserStorage'
import {
  getWatchlist,
  getProjectWatchlist,
  getEntityWatchlist,
  getMunicipalityWatchlist,
  watchlistStorageEntries,
} from './watchlist'
import {
  getSavedSearches,
  getComparison,
  getRecentInvestigations,
  type SavedSearch,
  type RecentInvestigation,
} from './investigationState'
import type { IntelligenceEvent } from '../types/api'

export type AccountSession = {
  authenticated: boolean
  configured: boolean
  sync_enabled?: boolean
  user?: { id: string; email: string }
  workspace_id?: string
  login_url: string
  logout_url?: string
}
export type ServerWatchItem = {
  kind: 'parcel' | 'project' | 'entity' | 'municipality'
  subject_key: string
  label: string
}
type Snapshot = {
  version: number
  items: ServerWatchItem[]
  saved_searches: SavedSearch[]
  comparison: string[]
  recent_investigations: RecentInvestigation[]
}
export type WatchInbox = {
  notifications: { id: number; event: IntelligenceEvent }[]
  has_more: boolean
  next_before_id: number | null
  summary: string
}
let account: AccountSession | null = null
let hydrated = false
let busy = false
let refreshing = false
let applying = false
let revision = 0
let generation = 0
let message = ''
let inbox: WatchInbox | null = null
let inboxCursor: number | null = null
let inboxRevision = 0
let initialized = false
let conflict = false
function metadataKey() {
  return 'countyiq_account_sync:' + account?.user?.id
}
function metadata(): { version: number; dirty: boolean; requiresReview?: boolean } | null {
  try {
    const v = JSON.parse(localStorage.getItem(metadataKey()) ?? 'null')
    return v && Number.isInteger(v.version) && v.version >= 0 ? v : null
  } catch {
    return null
  }
}
function persist(version: number, dirty: boolean) {
  commitBrowserStorage({
    [metadataKey()]: JSON.stringify({
      version,
      dirty,
      requiresReview: metadata()?.requiresReview === true,
    }),
  })
}
function notify() {
  window.dispatchEvent(new Event('countyiq-watch-sync-changed'))
}
export function watchSyncState() {
  return {
    account,
    initialized,
    hydrated,
    connected: Boolean(account?.authenticated && account?.workspace_id && account?.sync_enabled),
    message,
    inbox,
    conflict,
    olderInbox: inboxCursor !== null,
  }
}

class SessionExpired extends Error {}
class WorkspaceConflict extends Error {}
async function request<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const response = await fetch('/api' + path, {
    method,
    credentials: 'same-origin',
    headers: {
      ...(method !== 'GET' ? { 'X-CountyIQ-Workspace': '1' } : {}),
      ...(path.startsWith('/watchspaces') && account?.user?.id
        ? { 'X-CountyIQ-User': account.user.id }
        : {}),
      ...(body ? { 'Content-Type': 'application/json' } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (response.status === 401) {
    throw new SessionExpired('Sign in again to access your saved workspace.')
  }
  if (response.status === 409) {
    throw new WorkspaceConflict(
      'Another device changed your workspace. Your local edits are kept. Export them or load your saved account copy.',
    )
  }
  if (!response.ok) {
    throw new Error('Your saved workspace is unavailable. Local changes are kept for retry.')
  }
  return response.status === 204 ? (undefined as T) : response.json()
}
function localWatchItems(): ServerWatchItem[] {
  return [
    ...getWatchlist().map((subject_key) => ({
      kind: 'parcel' as const,
      subject_key,
      label: subject_key,
    })),
    ...getProjectWatchlist().map((p) => ({
      kind: 'project' as const,
      subject_key: p.key,
      label: p.name,
    })),
    ...getEntityWatchlist().map((e) => ({
      kind: 'entity' as const,
      subject_key: String(e.id),
      label: e.name,
    })),
    ...getMunicipalityWatchlist().map((m) => ({
      kind: 'municipality' as const,
      subject_key: m.name,
      label: m.name,
    })),
  ]
}
function emitApplied() {
  applying = true
  try {
    window.dispatchEvent(new Event('countyiq-watchlist-changed'))
    window.dispatchEvent(new Event('countyiq-investigation-changed'))
  } finally {
    applying = false
  }
}
function apply(snapshot: Snapshot) {
  const watches = watchlistStorageEntries({
    parcels: snapshot.items.filter((i) => i.kind === 'parcel').map((i) => i.subject_key),
    projects: snapshot.items
      .filter((i) => i.kind === 'project')
      .map((i) => ({ key: i.subject_key, name: i.label })),
    entities: snapshot.items
      .filter((i) => i.kind === 'entity')
      .map((i) => ({ id: Number(i.subject_key), name: i.label })),
    municipalities: snapshot.items
      .filter((i) => i.kind === 'municipality')
      .map((i) => ({ name: i.subject_key })),
  })
  commitBrowserStorage({
    ...watches,
    ...investigationStorageEntries(
      snapshot.saved_searches,
      snapshot.comparison,
      snapshot.recent_investigations,
    ),
    [metadataKey()]: JSON.stringify({ version: snapshot.version, dirty: false }),
  })
  hydrated = true
  emitApplied()
}
function expire() {
  generation++
  hydrated = false
  account = account
    ? { ...account, authenticated: false, user: undefined, workspace_id: undefined }
    : null
  setWorkspaceAccount(null)
  inbox = null
  inboxCursor = null
  inboxRevision++
  emitApplied()
}
export async function refreshAccount() {
  if (refreshing) {
    return
  }
  refreshing = true
  const startGeneration = generation
  try {
    let next = await request<AccountSession>('/session')
    if (next.authenticated && !next.workspace_id) {
      next = await request<AccountSession>('/session', 'POST', {})
    }
    if (generation !== startGeneration) {
      return
    }
    const switched = account?.user?.id !== next.user?.id
    account = next
    if (switched) {
      generation++
      hydrated = false
      inbox = null
      inboxCursor = null
      inboxRevision++
      conflict = false
      setWorkspaceAccount(next.authenticated ? (next.user?.id ?? null) : null)
      emitApplied()
    }
    initialized = true
    notify()
    if (next.authenticated && next.sync_enabled) {
      await syncWatches()
    }
  } catch (error) {
    if (generation !== startGeneration) {
      return
    }
    if (error instanceof WorkspaceConflict) {
      conflict = true
    }
    if (error instanceof SessionExpired) {
      expire()
    }
    initialized = true
    message = error instanceof Error ? error.message : 'Sign-in is unavailable.'
    notify()
  } finally {
    refreshing = false
  }
}
export async function syncWatches() {
  if (!watchSyncState().connected || busy || conflict) {
    return
  }
  busy = true
  const startRevision = revision,
    startGeneration = generation
  try {
    const current = metadata()
    if (current?.requiresReview) {
      conflict = true
      message =
        'Local edits need review before syncing. Export them or load your saved account copy.'
      return
    }
    const remote = current?.dirty
      ? await request<Snapshot>('/watchspaces/current', 'PUT', {
          version: current.version,
          items: localWatchItems(),
          saved_searches: getSavedSearches(),
          comparison: getComparison(),
          recent_investigations: getRecentInvestigations(),
        })
      : await request<Snapshot>('/watchspaces/current')
    if (generation !== startGeneration) {
      return
    }
    if (metadata()?.requiresReview) {
      conflict = true
      message =
        'Local edits need review before syncing. Export them or load your saved account copy.'
      return
    }
    if (current?.dirty) {
      persist(remote.version, revision !== startRevision)
      hydrated = true
    } else if (revision === startRevision && !metadata()?.dirty) {
      apply(remote)
    }
    const currentInboxRevision = inboxRevision
    const nextInbox = await request<WatchInbox>(inboxPath(inboxCursor))
    if (generation !== startGeneration) {
      return
    }
    if (inboxRevision === currentInboxRevision) {
      inbox = nextInbox
    }
    message = metadata()?.dirty ? 'Saving further changes…' : 'Saved to your account.'
    const newest =
      inboxRevision === currentInboxRevision && inboxCursor === null
        ? (nextInbox.notifications[0]?.id ?? 0)
        : 0
    const key = 'countyiq_last_notified:' + account?.user?.id
    if (
      newest > Number(localStorage.getItem(key) ?? 0) &&
      localStorage.getItem('countyiq_browser_alerts') === 'true' &&
      'Notification' in window &&
      Notification.permission === 'granted'
    ) {
      new Notification('CountyIQ watched changes', {
        body: nextInbox.summary,
        tag: 'countyiq-watches',
      })
      localStorage.setItem(key, String(newest))
    }
  } catch (error) {
    if (generation !== startGeneration) {
      return
    }
    if (error instanceof WorkspaceConflict) {
      conflict = true
    }
    if (error instanceof SessionExpired) {
      expire()
    }
    message = error instanceof Error ? error.message : 'Unable to sync saved work.'
  } finally {
    busy = false
    notify()
  }
}
async function replaceSavedWorkspace(clear: boolean) {
  if (!watchSyncState().connected || busy) {
    return
  }
  busy = true
  const currentGeneration = generation,
    currentRevision = revision
  try {
    if (clear) {
      await request('/watchspaces/current', 'DELETE')
      if (generation !== currentGeneration) {
        return
      }
      inbox = null
      inboxCursor = null
      inboxRevision++
      // Until the post-delete version is known, never upload the old local copy.
      conflict = true
      message =
        'Your saved workspace was cleared. Load the saved copy to finish updating this browser.'
      commitBrowserStorage({
        [metadataKey()]: JSON.stringify({
          version: metadata()?.version ?? 0,
          dirty: true,
          requiresReview: true,
        }),
      })
    }
    const remote = await request<Snapshot>('/watchspaces/current')
    if (generation !== currentGeneration) {
      return
    }
    if (revision !== currentRevision) {
      commitBrowserStorage({
        [metadataKey()]: JSON.stringify({
          version: remote.version,
          dirty: true,
          requiresReview: true,
        }),
      })
      conflict = true
      message =
        'Local edits changed while the saved workspace was loading. Your edits are kept; export them or load the saved copy again.'
      return
    }
    apply(remote)
    revision++
    conflict = false
    message = clear
      ? 'Cleared your saved account workspace.'
      : 'Loaded your saved account workspace.'
  } finally {
    busy = false
    notify()
  }
}
export async function loadServerWatches() {
  await replaceSavedWorkspace(false)
}
export async function clearAccountWorkspace() {
  await replaceSavedWorkspace(true)
}
export function signOut() {
  const destination = account?.logout_url ?? '/'
  expire()
  notify()
  window.location.assign(destination)
}
function inboxPath(cursor: number | null) {
  return '/watchspaces/notifications' + (cursor === null ? '' : '?before_id=' + cursor)
}
async function showInbox(cursor: number | null) {
  const currentGeneration = generation,
    currentRevision = ++inboxRevision
  const result = await request<WatchInbox>(inboxPath(cursor))
  if (currentGeneration !== generation || currentRevision !== inboxRevision) {
    return
  }
  inboxRevision++
  inboxCursor = cursor
  inbox = result
  notify()
}
export async function olderWatchChanges() {
  if (!inbox?.has_more || !inbox.next_before_id) {
    return
  }
  await showInbox(inbox.next_before_id)
}
export async function latestWatchChanges() {
  await showInbox(null)
}
export async function acknowledgeWatchChanges() {
  if (!inbox?.notifications.length) {
    return
  }
  const currentGeneration = generation,
    currentRevision = inboxRevision
  await request('/watchspaces/notifications/read', 'POST', {
    notification_ids: inbox.notifications.map((item) => item.id),
  })
  if (generation !== currentGeneration || inboxRevision !== currentRevision) {
    return
  }
  await showInbox(inboxCursor)
}
export async function enableBrowserAlerts() {
  if (!('Notification' in window)) {
    throw new Error('Browser notifications are unavailable here.')
  }
  const permission = await Notification.requestPermission()
  localStorage.setItem('countyiq_browser_alerts', String(permission === 'granted'))
  if (permission !== 'granted') {
    throw new Error('Browser notifications were not enabled.')
  }
}
export function startWatchSync() {
  const changed = () => {
    if (applying || !watchSyncState().connected) {
      return
    }
    revision++
    const current = metadata()
    if (!current) {
      try {
        commitBrowserStorage({
          [metadataKey()]: JSON.stringify({ version: 0, dirty: true, requiresReview: true }),
        })
        conflict = true
        message =
          'Local edits need review before syncing. Export them or load your saved account copy.'
      } catch {
        message = 'Local storage could not retain this change.'
      }
      notify()
      return
    }
    try {
      persist(current.version, true)
      void syncWatches()
    } catch {
      message = 'Local storage could not retain this change.'
      notify()
    }
  }
  const storageChanged = (event: StorageEvent) => {
    if (
      event.key?.startsWith('countyiq_account:' + account?.user?.id + ':') ||
      event.key === metadataKey()
    ) {
      revision++
      emitApplied()
      void syncWatches()
    }
  }
  window.addEventListener('countyiq-watchlist-changed', changed)
  window.addEventListener('countyiq-investigation-changed', changed)
  window.addEventListener('storage', storageChanged)
  window.addEventListener('online', refreshAccount)
  void refreshAccount()
  const timer = window.setInterval(() => {
    if (document.visibilityState === 'visible') {
      void refreshAccount()
    }
  }, 30000)
  return () => {
    window.clearInterval(timer)
    window.removeEventListener('countyiq-watchlist-changed', changed)
    window.removeEventListener('countyiq-investigation-changed', changed)
    window.removeEventListener('storage', storageChanged)
    window.removeEventListener('online', refreshAccount)
  }
}
