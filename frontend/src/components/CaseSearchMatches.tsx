import { Link } from 'react-router-dom'
import { useFetchJson } from '../lib/useFetchJson'
import { formatShortDate } from '../lib/format'
import { activityLabel } from '../lib/investigation'
import type { IntelligenceFeedResponse, MunicipalitySummary } from '../types/api'

export type OrganizationSummary = {
  owner_id: number
  canonical_name: string
  entity_type: string
  parcel_count: number
  municipality: string | null
  verification_status: string | null
}
type ProjectSummary = {
  key: string
  name: string
  municipality: string | null
  latest_date: string | null
  latest_activity: string
}

function placeKey(value: string): string {
  return value
    .toLowerCase()
    .replace(/township/g, 'twp')
    .replace(/borough/g, 'boro')
    .replace(/[^a-z0-9]/g, '')
}

export default function CaseSearchMatches({ query }: { query: string }) {
  const organizations = useFetchJson<{ organizations: OrganizationSummary[] }>(
    query.length >= 2
      ? '/api/directory/organizations?limit=6&q=' + encodeURIComponent(query)
      : null,
  )
  const projects = useFetchJson<{ projects: ProjectSummary[] }>(
    query.length >= 2 ? '/api/directory/projects?limit=6&q=' + encodeURIComponent(query) : null,
  )
  const records = useFetchJson<IntelligenceFeedResponse>(
    query.length >= 2
      ? `/api/feed?q=${encodeURIComponent(query)}&since_days=3650&limit=3&sort=latest`
      : null,
  )
  const municipalities = useFetchJson<MunicipalitySummary[]>(
    query.length >= 2 ? '/api/municipalities' : null,
  )
  const places = (municipalities.data ?? [])
    .filter((item) => placeKey(item.name).includes(placeKey(query)))
    .slice(0, 6)
  const pending =
    organizations.loading || projects.loading || records.loading || municipalities.loading
  const failed = organizations.error || projects.error || records.error || municipalities.error

  return (
    <section className="case-search-matches" aria-label="Matching records and places">
      {pending && <p role="status">Searching records and places…</p>}
      {failed && (
        <p role="status">Some records or places could not be searched. Try the search again.</p>
      )}
      {places.length > 0 && (
        <div>
          <h2>Municipalities</h2>
          {places.map((item) => (
            <Link key={item.name} to={`/municipalities/${encodeURIComponent(item.name)}`}>
              <strong>{item.name}</strong>
              <span>Activity, upcoming dates and source coverage</span>
            </Link>
          ))}
        </div>
      )}
      {!!projects.data?.projects.length && (
        <div>
          <h2>Projects</h2>
          {projects.data.projects.map((item) => (
            <Link key={item.key} to={'/project/' + encodeURIComponent(item.key)}>
              <strong>{item.name}</strong>
              <span>
                {item.municipality} · {formatShortDate(item.latest_date) ?? 'Date unverified'}
              </span>
            </Link>
          ))}
        </div>
      )}
      {!!records.data?.events.length && (
        <div className="case-record-matches">
          <h2>Matching activity & source passages</h2>
          <div className="feed-list">
            {records.data.events.map((event) => (
              <Link
                key={event.event_key}
                to={`/feed?q=${encodeURIComponent(query)}&days=3650&sort=latest&record=${encodeURIComponent(event.event_key)}`}
              >
                <span>
                  {activityLabel(event)} · {event.municipality} ·{' '}
                  {formatShortDate(event.event_date)}
                </span>
                <strong>{event.title}</strong>
                <span>Open investigation →</span>
              </Link>
            ))}
          </div>
          {records.data.has_more && (
            <Link to={`/feed?q=${encodeURIComponent(query)}&days=3650`}>
              View all matching activity →
            </Link>
          )}
        </div>
      )}
      {!!organizations.data?.organizations.length && (
        <div>
          <h2>Organizations</h2>
          {organizations.data.organizations.map((item) => (
            <Link key={item.owner_id} to={'/entity/' + item.owner_id}>
              <strong>{item.canonical_name}</strong>
              <span>
                {item.parcel_count} linked properties · {item.municipality || 'County records'}
              </span>
            </Link>
          ))}
        </div>
      )}
    </section>
  )
}
