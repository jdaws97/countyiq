import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import PageShell from '../components/PageShell'
import { Button, EmptyState, PageHeader, StatusMessage } from '../components/ui'
import { useCountyMeta } from '../lib/useCountyMeta'
import { useFetchJson } from '../lib/useFetchJson'
import { getMunicipalityWatchlist } from '../lib/watchlist'
import type { MunicipalitySummary as Municipality } from '../types/api'
import './DirectoryPages.css'

export default function MunicipalityList() {
  const county = useCountyMeta()
  const [query, setQuery] = useState('')
  const [watchedNames, setWatchedNames] = useState(
    () => new Set(getMunicipalityWatchlist().map((item) => item.name)),
  )
  const { data, loading, error, reload } = useFetchJson<Municipality[]>('/api/municipalities')
  const municipalities = useMemo(
    () => [...(data ?? [])].sort((a, b) => a.name.localeCompare(b.name)),
    [data],
  )

  useEffect(() => {
    const refresh = () =>
      setWatchedNames(new Set(getMunicipalityWatchlist().map((item) => item.name)))
    window.addEventListener('countyiq-watchlist-changed', refresh)
    return () => window.removeEventListener('countyiq-watchlist-changed', refresh)
  }, [])

  const displayedMunicipalities = useMemo(() => {
    const normalize = (value: string) =>
      value
        .toLowerCase()
        .replace(/township/g, 'twp')
        .replace(/borough/g, 'boro')
        .replace(/[^a-z0-9]/g, '')
    const normalizedQuery = normalize(query)
    if (!normalizedQuery) {
      return municipalities
    }
    return municipalities.filter((municipality) =>
      normalize(municipality.name).includes(normalizedQuery),
    )
  }, [municipalities, query])

  return (
    <PageShell maxWidth={1100}>
      <PageHeader
        eyebrow={`${county.county_name} · ${county.state}`}
        title="Municipalities"
        description="Choose a municipality to review its recorded activity and profile. Coverage and source scope are shown on each profile."
        meta={!loading ? `${municipalities.length} jurisdictions` : undefined}
      />

      <div className="directory-toolbar">
        <label className="directory-filter-label" htmlFor="municipality-filter">
          Find a municipality
        </label>
        <div className="directory-filter-control">
          <input
            id="municipality-filter"
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Start typing a municipality name"
          />
          {query && (
            <Button tone="quiet" onClick={() => setQuery('')}>
              Clear
            </Button>
          )}
        </div>
      </div>

      {loading && <StatusMessage>Loading municipalities…</StatusMessage>}
      {error && (
        <StatusMessage tone="error">
          Municipalities could not be loaded.{' '}
          <Button tone="quiet" onClick={reload}>
            Try again
          </Button>
        </StatusMessage>
      )}
      {!loading && !error && displayedMunicipalities.length === 0 && (
        <EmptyState
          title="No municipalities match that name"
          actions={<Button onClick={() => setQuery('')}>Clear search</Button>}
        >
          Try a shorter name or check the spelling.
        </EmptyState>
      )}
      {!loading && !error && displayedMunicipalities.length > 0 && (
        <div className="municipality-directory" aria-label="Municipality directory">
          {displayedMunicipalities.map((municipality) => (
            <article className="municipality-directory-row" key={municipality.name}>
              <div>
                <h2>
                  {watchedNames.has(municipality.name) && (
                    <span className="directory-watch-mark" title="Watched municipality">
                      ★
                    </span>
                  )}
                  {municipality.name}
                </h2>
                <p>{municipality.muni_type || 'Municipality'}</p>
              </div>
              <div className="municipality-directory-actions">
                <Link to={`/feed?municipality=${encodeURIComponent(municipality.name)}`}>
                  View activity
                </Link>
                <Link to={`/municipalities/${encodeURIComponent(municipality.name)}`}>
                  Open profile
                </Link>
              </div>
            </article>
          ))}
        </div>
      )}
    </PageShell>
  )
}
