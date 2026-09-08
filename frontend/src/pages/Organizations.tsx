import { Link, useSearchParams } from 'react-router-dom'

import type { OrganizationSummary } from '../components/CaseSearchMatches'
import PageShell from '../components/PageShell'
import { Button, EmptyState, PageHeader, StatusMessage } from '../components/ui'
import { useFetchJson } from '../lib/useFetchJson'
import './DirectoryPages.css'

const PAGE_SIZE = 50

export default function Organizations() {
  const [params, setParams] = useSearchParams()
  const query = params.get('q') || ''
  const offset = Math.max(0, Number(params.get('offset')) || 0)
  const { data, loading, error, reload } = useFetchJson<{
    organizations: OrganizationSummary[]
    has_more: boolean
  }>(
    `/api/directory/organizations?limit=${PAGE_SIZE}&offset=${offset}&q=${encodeURIComponent(query)}`,
  )

  function setPage(nextOffset: number) {
    const next = new URLSearchParams()
    if (query) {
      next.set('q', query)
    }
    if (nextOffset > 0) {
      next.set('offset', String(nextOffset))
    }
    setParams(next)
  }

  return (
    <PageShell maxWidth={1100}>
      <PageHeader
        title="Organizations"
        description="Browse recorded owner names and the properties linked to them."
      />
      <div className="directory-context" role="note">
        Names are grouped from county ownership records. A grouping helps you find holdings recorded
        under that name; it does not establish common control. Open a profile to review the linked
        records.
      </div>
      <form
        className="directory-search"
        role="search"
        onSubmit={(event) => {
          event.preventDefault()
          const nextQuery = String(new FormData(event.currentTarget).get('q') || '').trim()
          setParams(nextQuery ? { q: nextQuery } : {})
        }}
      >
        <label className="sr-only" htmlFor="organization-search">
          Organization name
        </label>
        <input
          key={query}
          id="organization-search"
          name="q"
          type="search"
          defaultValue={query}
          placeholder="Search a recorded owner name"
        />
        <Button type="submit">Search</Button>
      </form>
      {loading && <StatusMessage>Loading organizations…</StatusMessage>}
      {error && (
        <StatusMessage tone="error">
          Organizations could not be loaded.{' '}
          <Button tone="quiet" onClick={reload}>
            Try again
          </Button>
        </StatusMessage>
      )}
      {!loading && !error && !data?.organizations.length && (
        <EmptyState
          title={query ? 'No organizations match that name' : 'No organizations available'}
        >
          {query
            ? 'Try a shorter name or search for a property address.'
            : 'Please try again shortly.'}
        </EmptyState>
      )}
      <div className="organization-list" aria-label="Organization directory results">
        {data?.organizations.map((item) => (
          <Link key={item.owner_id} to={`/entity/${item.owner_id}`}>
            <strong>{item.canonical_name}</strong>
            <span>{item.municipality || 'Municipality unavailable'}</span>
            <span>{item.parcel_count.toLocaleString()} linked holdings</span>
          </Link>
        ))}
      </div>
      <div className="section-actions" aria-label="Organization directory pagination">
        {offset > 0 && (
          <Button onClick={() => setPage(Math.max(0, offset - PAGE_SIZE))}>Previous</Button>
        )}
        {data?.has_more && <Button onClick={() => setPage(offset + PAGE_SIZE)}>Next</Button>}
      </div>
    </PageShell>
  )
}
