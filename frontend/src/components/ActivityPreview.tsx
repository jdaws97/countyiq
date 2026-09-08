import { Link } from 'react-router-dom'
import IntelligenceEventCard from './IntelligenceEventCard'
import { useFetchJson } from '../lib/useFetchJson'
import { watchBoostParams } from '../lib/watchlist'
import type { IntelligenceFeedResponse } from '../types/api'
import './ActivityPreview.css'

export default function ActivityPreview() {
  const params = new URLSearchParams({
    since_days: '90',
    limit: '3',
    sort: 'priority',
    ...watchBoostParams(),
  })
  const { data, loading, error, reload } = useFetchJson<IntelligenceFeedResponse>(
    `/api/feed?${params}`,
  )
  return (
    <section className="activity-preview" aria-labelledby="workspace-activity-heading">
      <div className="activity-preview-heading">
        <h2 id="workspace-activity-heading">Recent local activity</h2>
        <Link to="/feed">Browse all activity →</Link>
      </div>
      <p className="activity-scope-note">
        From reviewed municipal and property records. Coverage varies by municipality.
      </p>
      {loading && <p role="status">Loading recent activity…</p>}
      {error && (
        <p role="status">
          Activity could not be loaded.{' '}
          <button className="source-catalog-button" onClick={reload}>
            Try again
          </button>
        </p>
      )}
      {!loading && !error && !data?.events.length && (
        <p>
          No activity is available in the reviewed records for this period.{' '}
          <Link to="/municipalities">Explore municipal coverage</Link>.
        </p>
      )}
      <div className="feed-list">
        {data?.events.map((event) => (
          <IntelligenceEventCard key={event.event_key} event={event} />
        ))}
      </div>
    </section>
  )
}
