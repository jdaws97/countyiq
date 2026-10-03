import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { Button, ButtonLink, StatusMessage } from '../ui'
import { useFetchJson } from '../../lib/useFetchJson'
import type { SearchResponse } from '../../types/api'

export default function SiteSearch() {
  const [query, setQuery] = useState('')
  const [submitted, setSubmitted] = useState('')
  const result = useFetchJson<SearchResponse>(
    submitted ? `/api/search?q=${encodeURIComponent(submitted)}&limit=15` : null,
  )
  const matches = result.data?.results.filter((item) => item.pidn) ?? []
  const redirectPidn = result.data?.redirect_path?.match(/^\/property\/([A-Za-z0-9_-]+)$/)?.[1]
  const queryChanged = submitted !== '' && query.trim() !== submitted
  function submit(event: FormEvent) {
    event.preventDefault()
    const next = query.trim()
    if (next.length < 2) {
      return
    }
    setSubmitted(next)
    if (next === submitted) {
      result.reload()
    }
  }
  return (
    <section className="site-property-finder" aria-labelledby="identify-site-heading">
      <h2 id="identify-site-heading">Search the county property records</h2>
      <form className="site-search" onSubmit={submit} role="search">
        <label htmlFor="site-query">Address, owner or parcel ID</label>
        <div>
          <input
            id="site-query"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            maxLength={160}
            minLength={2}
            required
            autoFocus
            placeholder="Enter the client’s candidate property"
          />
          <Button type="submit" tone="primary">
            Find property
          </Button>
        </div>
      </form>
      <p className="site-search-guidance">
        Choose the exact property. Similar addresses and owner names can refer to different parcels.{' '}
        You can also identify it on the <Link to="/map">map</Link>.
      </p>
      {result.loading && <StatusMessage>Finding properties…</StatusMessage>}
      {result.error && (
        <StatusMessage tone="error">
          Property search is unavailable. Retry before starting the inquiry.
        </StatusMessage>
      )}
      {result.data && (
        <div className="site-search-results-heading">
          <h3>Results for “{submitted}”</h3>
          {queryChanged && (
            <p role="status">
              The search text changed. Select Find property to update these results.
            </p>
          )}
        </div>
      )}
      {redirectPidn && (
        <ButtonLink to={`/sites/new?pidn=${encodeURIComponent(redirectPidn)}`}>
          Review parcel {redirectPidn}
        </ButtonLink>
      )}
      <div className="site-search-results">
        {matches.map((item, index) => (
          <Link
            key={`${item.pidn}:${index}`}
            className="site-search-result"
            to={`/sites/new?pidn=${encodeURIComponent(item.pidn!)}`}
          >
            <div>
              <strong>{item.title || item.pidn}</strong>
              <span>{item.subtitle}</span>
            </div>
            <span className="site-search-result-id">
              Parcel {item.pidn}
              <span>Confirm site →</span>
            </span>
          </Link>
        ))}
      </div>
      {result.data && !matches.length && !redirectPidn && (
        <StatusMessage>
          No matching parcel was found. Try the PIDN or open the <Link to="/map">map</Link> to
          identify the site.
        </StatusMessage>
      )}
    </section>
  )
}
