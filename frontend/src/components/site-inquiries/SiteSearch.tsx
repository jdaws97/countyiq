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
    <section className="site-section" aria-labelledby="identify-site-heading">
      <h2 id="identify-site-heading">Identify the site</h2>
      <form className="site-search" onSubmit={submit} role="search">
        <label htmlFor="site-query">Address, owner or parcel ID</label>
        <div>
          <input
            id="site-query"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            maxLength={200}
            minLength={2}
            required
            placeholder="Enter the client’s candidate property"
          />
          <Button type="submit" tone="primary">
            Find property
          </Button>
        </div>
      </form>
      <p>
        Choose the exact property. Similar addresses and owner names can refer to different parcels.
      </p>
      {result.loading && <StatusMessage>Finding properties…</StatusMessage>}
      {result.error && (
        <StatusMessage tone="error">
          Property search is unavailable. Retry before starting the inquiry.
        </StatusMessage>
      )}
      {redirectPidn && (
        <ButtonLink to={`/sites?pidn=${encodeURIComponent(redirectPidn)}`}>
          Review parcel {redirectPidn}
        </ButtonLink>
      )}
      <div className="site-inquiry-list">
        {matches.map((item, index) => (
          <Link
            key={`${item.pidn}:${index}`}
            className="site-inquiry-card"
            to={`/sites?pidn=${encodeURIComponent(item.pidn!)}`}
          >
            <strong>{item.title || item.pidn}</strong>
            <span>{item.subtitle}</span>
            <small>PIDN {item.pidn} · Confirm identity</small>
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
