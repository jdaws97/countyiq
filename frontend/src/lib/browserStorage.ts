// Account scope is established only after a verified session response.
// Never restore the previous account identity from browser storage on startup.
let activeAccount: string | null = null
export function setWorkspaceAccount(userId: string | null) {
  activeAccount = userId
}
export function workspaceStorageKey(key: string): string {
  return activeAccount &&
    /^countyiq_(watchlist|project_watchlist|entity_watchlist|municipality_watchlist|saved_searches|compare|event_triage|last_feed_visit|last_watch_visit|recent_investigations|intelligence_profile|intelligence_work|site_inquiries)_v1$/.test(
      key,
    )
    ? 'countyiq_account:' + activeAccount + ':' + key
    : key
}
export function investigationStorageEntries(
  savedSearches: unknown[],
  comparison: string[],
  recent: unknown[],
) {
  return {
    countyiq_saved_searches_v1: JSON.stringify(savedSearches),
    countyiq_compare_v1: JSON.stringify(comparison),
    countyiq_recent_investigations_v1: JSON.stringify(recent),
  }
}

/** Commit related browser keys together, restoring prior values on a failed write. */
export function commitBrowserStorage(updates: Record<string, string>): void {
  updates = Object.fromEntries(
    Object.entries(updates).map(([key, value]) => [workspaceStorageKey(key), value]),
  )
  const previous = Object.fromEntries(
    Object.keys(updates).map((key) => [key, localStorage.getItem(key)]),
  )
  const written: string[] = []
  try {
    for (const [key, value] of Object.entries(updates)) {
      localStorage.setItem(key, value)
      written.push(key)
    }
  } catch {
    try {
      // Remove the replacement values first so quota is available for rollback.
      for (const key of written) {
        localStorage.removeItem(key)
      }
      for (const key of written) {
        const value = previous[key]
        if (value !== null) {
          localStorage.setItem(key, value)
        }
      }
    } catch {
      throw new Error(
        'Browser storage failed and the previous workspace could not be fully restored. Keep your exported backup.',
      )
    }
    throw new Error('Browser storage is full or unavailable. Your previous workspace was kept.')
  }
}
