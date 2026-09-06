import { useEffect, type FormEvent } from 'react'
import { useSearchParams, Link, useNavigate } from 'react-router-dom'
import CaseSearchMatches from '../components/CaseSearchMatches'
import PageShell from '../components/PageShell'
import { useFetchJson } from '../lib/useFetchJson'
import type { SearchResponse } from '../types/api'

const TYPE_LABELS: Record<string, { label: string; color: string }> = {
  address: { label: 'Address', color: 'var(--accent-blue)' },
  tax_claim: { label: 'Tax Delinquent', color: 'var(--accent-red)' },
  license: { label: 'Liquor License', color: 'var(--accent-green)' },
  parcel: { label: 'Parcel', color: 'var(--accent-cyan)' },
}

const MATCH_LABELS: Record<string, string> = {
  parcel_id: 'Parcel ID',
  address: 'Address',
  owner: 'Owner',
  mapped_address: 'Mapped address',
  license: 'Premises',
}

const SEARCH_RESULT_LIMIT = 25

function matchStrength(score: number) {
  if (score >= 0.9) {
    return 'Exact'
  }
  if (score >= 0.65) {
    return 'Strong'
  }
  return 'Possible'
}

export default function SearchResults() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const query = searchParams.get('q') || ''
  const {
    data,
    error: requestError,
    loading,
    reload,
  } = useFetchJson<SearchResponse>(
    query.length >= 2
      ? '/api/search?q=' + encodeURIComponent(query) + '&limit=' + SEARCH_RESULT_LIMIT
      : null,
  )
  const results = data?.results ?? []
  const mode = data?.mode ?? 'fuzzy'
  const description = data?.description ?? ''
  const aggLabel = data?.label ?? ''
  const aggValue = data?.value ?? ''
  const error = requestError ? 'Search is temporarily unavailable. Please try again.' : ''

  useEffect(() => {
    if (data?.mode === 'redirect' && data.redirect_path) {
      navigate(data.redirect_path)
    }
  }, [data, navigate])

  const handleSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const nextQuery = String(new FormData(event.currentTarget).get('q') || '').trim()
    if (nextQuery.length >= 2) {
      if (nextQuery === query) {
        reload()
      } else {
        navigate(`/search?q=${encodeURIComponent(nextQuery)}`)
      }
    }
  }

  return (
    <PageShell maxWidth={1200}>
      {/* Header */}
      <div style={{ marginBottom: 32 }}>
        <Link
          to="/"
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            color: 'var(--text-muted)',
            textDecoration: 'none',
            letterSpacing: 1,
          }}
        >
          &larr; Back to Home
        </Link>
        <h1
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 24,
            fontWeight: 600,
            color: 'var(--text-primary)',
            marginTop: 12,
            marginBottom: 4,
          }}
        >
          Search Results
        </h1>
        <form
          onSubmit={handleSearch}
          role="search"
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: 8,
            margin: '18px 0 12px',
            maxWidth: 760,
          }}
        >
          <label className="sr-only" htmlFor="results-search">
            Search properties, projects, organizations and places
          </label>
          <input
            key={query}
            id="results-search"
            name="q"
            type="search"
            defaultValue={query}
            minLength={2}
            required
            autoFocus
            placeholder="Property, project, organization, or place"
            style={{
              flex: '1 1 320px',
              minWidth: 0,
              minHeight: 42,
              padding: '10px 13px',
              color: 'var(--text-primary)',
              background: 'var(--bg-panel)',
              border: '1px solid var(--border-active)',
              borderRadius: 6,
              fontSize: 15,
            }}
          />
          <button type="submit" className="ciq-button ciq-button-primary">
            Search
          </button>
        </form>
        <p
          style={{
            fontFamily: 'var(--font-sans)',
            fontSize: 14,
            color: 'var(--text-secondary)',
          }}
          aria-live="polite"
        >
          {loading
            ? 'Searching...'
            : error
              ? 'Search unavailable'
              : query.length < 2
                ? 'Enter at least two characters to search.'
                : mode === 'aggregate'
                  ? ''
                  : `${results.length === SEARCH_RESULT_LIMIT ? 'Top ' : ''}${results.length} property/place matches for "${query}"`}
        </p>
        {!loading && (mode === 'smart' || mode === 'aggregate') && description && (
          <p
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 12,
              color: 'var(--accent-gold)',
              background: 'rgba(212, 168, 67, 0.1)',
              border: '1px solid rgba(212, 168, 67, 0.2)',
              borderRadius: 4,
              padding: '6px 12px',
              marginTop: 8,
              display: 'inline-block',
            }}
          >
            AI: {description}
          </p>
        )}
      </div>

      <CaseSearchMatches query={query} />
      {/* Results */}
      {/* Aggregate result */}
      {!loading && mode === 'aggregate' && aggValue && (
        <div
          style={{
            textAlign: 'center',
            padding: '60px 0',
          }}
        >
          <div
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 10,
              letterSpacing: 2,
              textTransform: 'uppercase',
              color: 'var(--text-muted)',
              marginBottom: 12,
            }}
          >
            {aggLabel}
          </div>
          <div
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 56,
              fontWeight: 700,
              color: aggValue.startsWith('$') ? 'var(--accent-green)' : 'var(--accent-blue)',
              lineHeight: 1,
            }}
          >
            {aggValue}
          </div>
        </div>
      )}

      {!loading && error && (
        <div className="empty-state" role="alert">
          <div className="empty-state-mark" aria-hidden="true">
            !
          </div>
          <h2>Search could not be completed</h2>
          <p className="empty-state-copy">{error}</p>
          <button type="button" className="ciq-button ciq-button-secondary" onClick={reload}>
            Try again
          </button>
        </div>
      )}

      {query.length >= 2 && !loading && !error && results.length === 0 && mode !== 'aggregate' && (
        <div
          style={{
            color: 'var(--text-muted)',
            textAlign: 'center',
            padding: '60px 18px',
          }}
        >
          <strong
            style={{
              display: 'block',
              color: 'var(--text-primary)',
              fontSize: 18,
              marginBottom: 8,
            }}
          >
            No parcels or places found for "{query}"
          </strong>
          <span style={{ fontSize: 14, lineHeight: 1.6 }}>
            Try an owner name in either order, a street address with or without the ZIP code, or a
            full or partial parcel ID.
          </span>
        </div>
      )}

      {!loading && results.length > 0 && mode === 'smart' && (
        <div
          style={{
            border: '1px solid var(--border)',
            borderRadius: 8,
            overflow: 'hidden',
          }}
        >
          {results.map((r, idx) => {
            const link = r._link
            const entries = Object.entries(r).filter(
              ([k, v]) => v !== null && v !== '' && !k.startsWith('_'),
            )
            const content = (
              <div
                style={{
                  padding: '20px 24px',
                  background: idx % 2 === 0 ? 'var(--bg-panel)' : 'var(--bg-card)',
                  borderBottom: idx < results.length - 1 ? '1px solid var(--border)' : 'none',
                  transition: 'background 0.15s',
                  cursor: link ? 'pointer' : 'default',
                }}
                onMouseEnter={(e) => {
                  ;(e.currentTarget as HTMLDivElement).style.background = 'var(--bg-card-hover)'
                }}
                onMouseLeave={(e) => {
                  ;(e.currentTarget as HTMLDivElement).style.background =
                    idx % 2 === 0 ? 'var(--bg-panel)' : 'var(--bg-card)'
                }}
              >
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
                    gap: '10px 24px',
                  }}
                >
                  {entries.map(([k, v]) => (
                    <div key={k}>
                      <div
                        style={{
                          fontFamily: 'var(--font-mono)',
                          fontSize: 9,
                          letterSpacing: 1.5,
                          textTransform: 'uppercase' as const,
                          color: 'var(--text-muted)',
                          marginBottom: 2,
                        }}
                      >
                        {k}
                      </div>
                      <div
                        style={{
                          fontFamily:
                            String(v).startsWith('$') || /^\d/.test(String(v))
                              ? 'var(--font-mono)'
                              : 'var(--font-sans)',
                          fontSize: 14,
                          fontWeight: String(v).startsWith('$') ? 600 : 400,
                          color: String(v).startsWith('$')
                            ? 'var(--accent-green)'
                            : 'var(--text-primary)',
                        }}
                      >
                        {String(v)}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )
            return link ? (
              <Link
                key={idx}
                to={link}
                style={{ textDecoration: 'none', color: 'inherit', display: 'block' }}
              >
                {content}
              </Link>
            ) : (
              <div key={idx}>{content}</div>
            )
          })}
        </div>
      )}

      {!loading && results.length > 0 && mode === 'fuzzy' && (
        <div
          className="search-results-table"
          style={{
            border: '1px solid var(--border)',
            borderRadius: 8,
            overflow: 'hidden',
          }}
        >
          {/* Header row */}
          <div
            className="search-results-header"
            style={{
              padding: '12px 24px',
              background: 'var(--bg-panel)',
              borderBottom: '1px solid var(--border)',
            }}
          >
            {['Type', 'Result', 'Details', 'Match'].map((col, i) => (
              <div
                key={col}
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 10,
                  fontWeight: 600,
                  letterSpacing: 2,
                  textTransform: 'uppercase' as const,
                  color: 'var(--text-muted)',
                  textAlign: i >= 2 ? 'right' : 'left',
                }}
              >
                {col}
              </div>
            ))}
          </div>

          {/* Result rows */}
          {results.map((r, idx) => {
            const pidn = r.pidn
            const hasCoordinates = r.lat != null && r.lng != null
            const hasLink = Boolean(pidn) || hasCoordinates
            const linkTo = pidn
              ? `/property/${pidn}`
              : hasCoordinates
                ? `/map?lat=${r.lat}&lng=${r.lng}&zoom=17`
                : undefined
            const score = r.score ?? 0
            const matchKind = typeof r.match_kind === 'string' ? r.match_kind : ''
            const content = (
              <div
                className="search-result-row"
                style={{
                  padding: '14px 24px',
                  alignItems: 'center',
                  background: idx % 2 === 0 ? 'var(--bg-panel)' : 'var(--bg-card)',
                  borderBottom: idx < results.length - 1 ? '1px solid var(--border)' : 'none',
                  transition: 'background 0.15s',
                  cursor: hasLink ? 'pointer' : 'default',
                }}
                onMouseEnter={(e) => {
                  ;(e.currentTarget as HTMLDivElement).style.background = 'var(--bg-card-hover)'
                }}
                onMouseLeave={(e) => {
                  ;(e.currentTarget as HTMLDivElement).style.background =
                    idx % 2 === 0 ? 'var(--bg-panel)' : 'var(--bg-card)'
                }}
              >
                <div className="search-result-type">
                  {(() => {
                    const t = TYPE_LABELS[r.result_type || ''] || {
                      label: r.result_type || 'result',
                      color: 'var(--text-muted)',
                    }
                    return (
                      <span
                        style={{
                          padding: '2px 8px',
                          borderRadius: 3,
                          fontSize: 9,
                          letterSpacing: 1,
                          textTransform: 'uppercase' as const,
                          fontFamily: 'var(--font-mono)',
                          color: t.color,
                          background: `${t.color}15`,
                          border: `1px solid ${t.color}30`,
                        }}
                      >
                        {t.label}
                      </span>
                    )
                  })()}
                </div>
                <div
                  className="search-result-title"
                  style={{
                    fontFamily: 'var(--font-sans)',
                    fontSize: 14,
                    fontWeight: 500,
                    color: 'var(--text-primary)',
                  }}
                >
                  {r.title}
                </div>
                <div
                  className="search-result-details"
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 11,
                    color: 'var(--text-secondary)',
                  }}
                >
                  {r.subtitle}
                </div>
                <div
                  className="search-result-match"
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 12,
                    color: 'var(--text-muted)',
                  }}
                >
                  <span style={{ display: 'block', color: 'var(--text-secondary)' }}>
                    {MATCH_LABELS[matchKind] || matchStrength(score)}
                  </span>
                  <span style={{ display: 'block', marginTop: 2, fontSize: 10 }}>
                    {matchStrength(score)} match
                  </span>
                </div>
              </div>
            )
            return linkTo ? (
              <Link
                key={`${r.title}-${r.subtitle}-${idx}`}
                to={linkTo}
                style={{ textDecoration: 'none', color: 'inherit' }}
              >
                {content}
              </Link>
            ) : (
              <div key={`${r.title}-${r.subtitle}-${idx}`}>{content}</div>
            )
          })}
        </div>
      )}
    </PageShell>
  )
}
