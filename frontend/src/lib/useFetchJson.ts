import { useEffect, useState } from 'react'

interface FetchState<T> {
  key: string | null
  data?: T
  error?: string
}

/**
 * Minimal JSON-fetching hook for CountyIQ pages.
 *
 * - Pass null to skip fetching (e.g. empty watchlist).
 * - Cancellation-safe: a stale response never overwrites a newer request.
 * - `loading` is DERIVED (state.key !== url) instead of set synchronously in
 *   the effect, which is what the react-hooks/set-state-in-effect rule wants —
 *   migrate the hand-rolled page fetches onto this hook to clear those errors.
 */
export function useFetchJson<T>(url: string | null): {
  data: T | null
  error: string | null
  loading: boolean
} {
  const [state, setState] = useState<FetchState<T>>({ key: null })

  useEffect(() => {
    if (!url) return
    let cancelled = false
    fetch(url)
      .then((r) => {
        if (!r.ok) throw new Error(`Request failed (${r.status})`)
        return r.json() as Promise<T>
      })
      .then((data) => {
        if (!cancelled) setState({ key: url, data })
      })
      .catch((err: unknown) => {
        console.error('useFetchJson failed for', url, err)
        if (!cancelled) setState({ key: url, error: 'Request failed' })
      })
    return () => {
      cancelled = true
    }
  }, [url])

  const fresh = state.key === url
  return {
    data: fresh && state.data !== undefined ? state.data : null,
    error: fresh && state.error !== undefined ? state.error : null,
    loading: url !== null && !fresh,
  }
}
