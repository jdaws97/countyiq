import { useCallback, useEffect, useState } from 'react'

interface FetchState<T> {
  key: string | null
  version: number
  data?: T
  error?: string
}

/**
 * Minimal JSON-fetching hook for CountyIQ pages.
 *
 * - Pass null to skip fetching (e.g. empty watchlist).
 * - Cancellation-safe: a stale response never overwrites a newer request.
 * - `loading` is derived from the URL and reload version instead of set in
 *   the effect, which is what the react-hooks/set-state-in-effect rule wants —
 *   migrate the hand-rolled page fetches onto this hook to clear those errors.
 */
export function useFetchJson<T>(url: string | null): {
  data: T | null
  error: string | null
  loading: boolean
  reload: () => void
} {
  const [state, setState] = useState<FetchState<T>>({ key: null, version: 0 })
  const [version, setVersion] = useState(0)
  const reload = useCallback(() => setVersion((current) => current + 1), [])

  useEffect(() => {
    if (!url) {
      return
    }
    let cancelled = false
    const controller = new AbortController()
    fetch(url, { signal: controller.signal })
      .then((r) => {
        if (!r.ok) {
          throw new Error(`Request failed (${r.status})`)
        }
        return r.json() as Promise<T>
      })
      .then((data) => {
        if (!cancelled) {
          setState({ key: url, version, data })
        }
      })
      .catch((err: unknown) => {
        if (cancelled) {
          return
        }
        console.error('useFetchJson failed for', url, err)
        if (!cancelled) {
          setState({ key: url, version, error: 'Request failed' })
        }
      })
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [url, version])

  const fresh = state.key === url && state.version === version
  return {
    data: fresh && state.data !== undefined ? state.data : null,
    error: fresh && state.error !== undefined ? state.error : null,
    loading: url !== null && !fresh,
    reload,
  }
}
