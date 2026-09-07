import { Link } from 'react-router-dom'
import { useFetchJson } from '../lib/useFetchJson'
import { watchBoostParams } from '../lib/watchlist'
import { getRecentInvestigations, getSavedSearches } from '../lib/investigationState'
import { upcomingActivityDates } from '../lib/activityDates'
import { describeRecordDate } from '../lib/recordDates'
import { activityLabel } from '../lib/investigation'
import { formatShortDate } from '../lib/format'
import { useCountyMeta } from '../lib/useCountyMeta'
import type { IntelligenceFeedResponse, PropertyReport } from '../types/api'
import ParcelContextMap from './ParcelContextMap'
import './WorkspaceOverview.css'

export default function WorkspaceOverview({ watches }: { watches: number }) {
  const county = useCountyMeta()
  const params = new URLSearchParams({
    since_days: '90',
    limit: '30',
    sort: 'priority',
    ...watchBoostParams(),
  })
  const feed = useFetchJson<IntelligenceFeedResponse>(`/api/feed?${params}`)
  const events = feed.data?.events ?? []
  const featured = events.find((event) => event.related_pidns.length === 1) ?? events[0]
  const property = useFetchJson<PropertyReport>(
    featured?.related_pidns.length === 1 ? `/api/parcels/${featured.related_pidns[0]}` : null,
  )
  const dates = upcomingActivityDates(events).slice(0, 3)
  const recent = getRecentInvestigations().slice(0, 3)
  const saved = getSavedSearches().slice(0, 3)
  const more = events.filter((event) => event.event_key !== featured?.event_key).slice(0, 4)
  const today = new Intl.DateTimeFormat('en-US', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  }).format(new Date())
  return (
    <div className="workspace-overview">
      <header className="overview-heading">
        <div>
          <p>
            {county.county_name}, {county.state} <span> / </span> {today}
          </p>
          <h1>
            Local development,
            <br />
            <em>in view.</em>
          </h1>
          <div>Understand the records. Find your next investigation.</div>
        </div>
        <Link className="overview-follow-link" to="/watch">
          <span className="overview-follow-icon" aria-hidden="true">
            ◎
          </span>
          <span>
            <strong>{watches ? `${watches} following` : 'Your watchlist'}</strong>
            <small>
              {watches ? 'Return to the places you follow' : 'Keep interesting places close'}
            </small>
          </span>
          <span aria-hidden="true">↗</span>
        </Link>
      </header>
      {feed.loading && (
        <div className="overview-loading" role="status">
          Bringing the latest reviewed records into view…
        </div>
      )}
      {feed.error && (
        <div className="overview-loading" role="alert">
          Activity could not be loaded. <button onClick={feed.reload}>Try again</button>
        </div>
      )}
      {!feed.loading && !feed.error && !featured && (
        <div className="overview-loading">
          <h2>Start with a place you know.</h2>
          <p>
            No activity is available in this period. You can still explore property records and
            municipal coverage.
          </p>
          <Link to="/search">Find a property →</Link>
        </div>
      )}
      {featured && (
        <div className="overview-main-grid">
          <section className="overview-feature">
            <div className="overview-section-heading">
              <span>IN THE RECORDS</span>
              <Link to="/feed">All activity ↗</Link>
            </div>
            <div className="overview-feature-body">
              <div className="overview-feature-copy">
                <span className="overview-record-label">{activityLabel(featured)}</span>
                <h2>{featured.title}</h2>
                <p>
                  {featured.municipality} <span>·</span>{' '}
                  {formatShortDate(featured.event_date) ?? 'Date unverified'}
                </p>
                <Link
                  className="overview-primary-action"
                  to={`/feed?record=${encodeURIComponent(featured.event_key)}`}
                >
                  Open investigation <span aria-hidden="true">→</span>
                </Link>
              </div>
              <div className="overview-feature-map">
                {property.data ? (
                  <ParcelContextMap report={property.data} />
                ) : (
                  <div className="overview-map-placeholder">
                    <span aria-hidden="true">◎</span>
                    <p>
                      {property.loading
                        ? 'Finding the property…'
                        : featured.municipality || 'County records'}
                    </p>
                  </div>
                )}
              </div>
            </div>
            <div className="overview-feature-footer">
              <span>
                <i />
                Source-backed account
              </span>
              <span>Read the full context and original documents</span>
            </div>
          </section>
          <aside className="overview-horizon">
            <div className="overview-section-heading">
              <span>DATES TO FOLLOW</span>
              <span aria-hidden="true">◷</span>
            </div>
            {dates.length ? (
              dates.map(({ event, date }) => (
                <Link
                  className="overview-date"
                  key={`${event.event_key}-${date.date}-${date.label}`}
                  to={`/feed?record=${encodeURIComponent(event.event_key)}`}
                >
                  <span className="overview-calendar">
                    <strong>{date.date?.slice(8, 10)}</strong>
                    <span>{formatShortDate(date.date)?.slice(0, 3)}</span>
                  </span>
                  <span>
                    <strong>{event.title}</strong>
                    <span>{event.municipality}</span>
                    <small>{describeRecordDate(date)}</small>
                  </span>
                  <span aria-hidden="true">↗</span>
                </Link>
              ))
            ) : (
              <div className="overview-no-dates">
                <h3>Keep an eye on what comes next.</h3>
                <p>
                  No upcoming dates are stated in these activity results. Open a municipality to
                  check its records and coverage.
                </p>
                <Link to="/municipalities">Explore municipalities →</Link>
              </div>
            )}
            <p className="overview-horizon-note">
              Dates stated in the loaded records. Proposed dates still need confirmation.
            </p>
          </aside>
        </div>
      )}
      <div className="overview-lower-grid">
        <section className="overview-more">
          <div className="overview-section-heading">
            <h2>Worth a closer look</h2>
            <Link to="/feed">Browse activity →</Link>
          </div>
          <p className="overview-section-note">From the last 90 days of available records.</p>
          {more.map((event, index) => (
            <Link
              className="overview-activity-row"
              key={event.event_key}
              to={`/feed?record=${encodeURIComponent(event.event_key)}`}
            >
              <span className="overview-row-number">{String(index + 1).padStart(2, '0')}</span>
              <span>
                <span className="overview-row-meta">
                  {activityLabel(event)} <i>·</i> {event.municipality}
                </span>
                <strong>{event.title}</strong>
              </span>
              <span className="overview-row-arrow" aria-hidden="true">
                ↗
              </span>
            </Link>
          ))}
        </section>
        <aside className="overview-return">
          <div className="overview-section-heading">
            <h2>{recent.length ? 'Pick up where you left off' : 'Start somewhere familiar'}</h2>
          </div>
          {recent.length ? (
            recent.map((item) => (
              <Link key={item.path} className="overview-recent" to={item.path}>
                <span aria-hidden="true">↶</span>
                <strong>{item.label}</strong>
                <span aria-hidden="true">→</span>
              </Link>
            ))
          ) : (
            <>
              <p>
                Search an address, owner or public plan number to see the records behind a place.
              </p>
              <Link className="overview-research-link" to="/search">
                Find a property <span>→</span>
              </Link>
            </>
          )}
          <div className="overview-research-links">
            <Link to="/radar">
              <span>
                Screen properties<small>Land, zoning & ownership</small>
              </span>
              <span aria-hidden="true">↗</span>
            </Link>
            <Link to="/municipalities">
              <span>
                Explore municipalities<small>Local activity & source coverage</small>
              </span>
              <span aria-hidden="true">↗</span>
            </Link>
          </div>
          {saved.length > 0 && (
            <div className="overview-saved">
              <h3>Saved searches</h3>
              {saved.map((item) => (
                <Link key={item.id} to={item.path}>
                  {item.name} →
                </Link>
              ))}
            </div>
          )}
        </aside>
      </div>
      <footer className="overview-coverage">
        Built from public property and municipal records. Coverage varies by place.
        <Link to="/municipalities">Check coverage ↗</Link>
      </footer>
    </div>
  )
}
