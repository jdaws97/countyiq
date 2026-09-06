import { Link, useSearchParams } from 'react-router-dom'
import PageShell from '../components/PageShell'
import { PageHeader, StatusMessage, EmptyState, Button } from '../components/ui'
import { useFetchJson } from '../lib/useFetchJson'
import type { OrganizationSummary } from '../components/CaseSearchMatches'
export default function Organizations() {
  const [params, setParams] = useSearchParams()
  const query = params.get('q') || ''
  const offset = Math.max(0, Number(params.get('offset')) || 0)
  const { data, loading, error } = useFetchJson<{
    organizations: OrganizationSummary[]
    has_more: boolean
  }>('/api/directory/organizations?limit=50&offset=' + offset + '&q=' + encodeURIComponent(query))
  return (
    <PageShell maxWidth={1100}>
      <PageHeader
        title="Organizations"
        description="Find organizations in county ownership records and open their linked properties and activity. Name groupings do not establish common control."
      />
      <form
        className="directory-search"
        role="search"
        onSubmit={(event) => {
          event.preventDefault()
          const q = String(new FormData(event.currentTarget).get('q') || '')
          setParams(q ? { q } : {})
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
          placeholder="Search organization names"
        />
        <Button type="submit">Search</Button>
      </form>
      {loading && <StatusMessage>Loading organizations…</StatusMessage>}
      {error && <StatusMessage tone="error">Organizations could not be loaded.</StatusMessage>}
      {!loading && !error && !data?.organizations.length && (
        <EmptyState title="No matching organizations">
          Try a shorter name or search for one of its properties.
        </EmptyState>
      )}
      <div className="organization-list">
        {data?.organizations.map((item) => (
          <Link key={item.owner_id} to={'/entity/' + item.owner_id}>
            <strong>{item.canonical_name}</strong>
            <span>
              {item.parcel_count} linked parcels · {item.municipality || 'County records'}
            </span>
            <small>
              {item.verification_status === 'verified'
                ? 'Identity reviewed'
                : 'Record grouping; relationships need verification'}
            </small>
          </Link>
        ))}
      </div>
      <div className="section-actions">
        {offset > 0 && (
          <Button onClick={() => setParams({ q: query, offset: String(Math.max(0, offset - 50)) })}>
            Previous
          </Button>
        )}
        {data?.has_more && (
          <Button onClick={() => setParams({ q: query, offset: String(offset + 50) })}>Next</Button>
        )}
      </div>
    </PageShell>
  )
}
