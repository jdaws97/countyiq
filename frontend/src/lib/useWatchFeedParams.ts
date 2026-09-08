import { useSyncExternalStore } from 'react'
import { watchBoostParams } from './watchlist'

function subscribe(onChange: () => void) {
  const events = ['countyiq-watchlist-changed', 'countyiq-watch-sync-changed', 'storage']
  events.forEach((event) => window.addEventListener(event, onChange))
  return () => events.forEach((event) => window.removeEventListener(event, onChange))
}

function snapshot(): string {
  return new URLSearchParams(watchBoostParams()).toString()
}

/** Keep followed activity current after local edits, account sync, or another tab. */
export function useWatchFeedParams(): string {
  return useSyncExternalStore(subscribe, snapshot, () => '')
}
