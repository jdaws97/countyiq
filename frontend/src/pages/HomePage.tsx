import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import IntelligenceEventCard from '../components/IntelligenceEventCard'
import Nav from '../components/Nav'
import SearchBar from '../components/SearchBar'
import { useCountyMeta } from '../lib/useCountyMeta'
import type { IntelligenceFeedResponse } from '../types/api'
import type { StatsData } from '../types/ops'

const START_POINTS = [
  {
    to: '/feed',
    label: 'Intelligence feed',
    description: 'See decisions, applications, ownership changes, and the evidence behind them.',
    color: 'var(--accent-gold)',
  },
  {
    to: '/radar',
    label: 'Development radar',
    description: 'Find parcels where multiple deterministic development signals converge.',
    color: 'var(--accent-green)',
  },
  {
    to: '/map',
    label: 'Map the context',
    description: 'Inspect parcels against zoning, infrastructure, flood, and land-use constraints.',
    color: 'var(--accent-blue)',
  },
  {
    to: '/watch',
    label: 'Watched intelligence',
    description: 'Return to the entities, projects, and parcels that matter to you.',
    color: 'var(--accent-cyan)',
  },
]

export default function HomePage() {
  const county = useCountyMeta()
  const [stats, setStats] = useState<StatsData | null>(null)
  const [feed, setFeed] = useState<IntelligenceFeedResponse | null>(null)
  const [feedError, setFeedError] = useState(false)

  useEffect(() => {
    fetch('/api/stats')
      .then((response) => {
        if (!response.ok) throw new Error(String(response.status))
        return response.json() as Promise<StatsData>
      })
      .then(setStats)
      .catch(() => setStats(null))

    fetch('/api/feed?limit=3&since_days=365&sort=priority')
      .then((response) => {
        if (!response.ok) throw new Error(String(response.status))
        return response.json() as Promise<IntelligenceFeedResponse>
      })
      .then((payload) => {
        setFeed(payload)
        setFeedError(false)
      })
      .catch(() => {
        setFeed(null)
        setFeedError(true)
      })
  }, [])

  return (
    <>
      <Nav />
      <main className="home-main">
        <section className="home-hero">
          <div>
            <div className="home-eyebrow">Local property &amp; development intelligence</div>
            <h1>Know what changed—and why it matters—before you start searching.</h1>
            <p>
              CountyIQ connects {county.county_name} municipal proceedings, parcel changes,
              projects, and ownership relationships into source-backed case files you can act on.
            </p>
            <div className="home-hero-actions">
              <Link to="/feed" className="button-primary">See what changed</Link>
              <Link to="/radar" className="button-secondary">Explore development radar</Link>
            </div>
          </div>
          <aside className="home-promise">
            <div className="home-promise-label">Every surfaced item answers</div>
            <ol>
              <li>What happened?</li>
              <li>Why could it matter?</li>
              <li>Who and which parcels are connected?</li>
              <li>What should I watch next?</li>
              <li>Where is the original evidence?</li>
            </ol>
            <div className="home-alpha-note">
              {county.product_stage} · Interpretation is labeled and never replaces the source record.
            </div>
          </aside>
        </section>

        <div className="home-search-block">
          <div className="home-search-label">Already have an address, owner, parcel, or place?</div>
          <SearchBar />
        </div>

        <section className="home-section">
          <div className="home-section-heading">
            <div>
              <div className="home-eyebrow">Prioritized without an LLM</div>
              <h2>What deserves attention now</h2>
            </div>
            <Link to="/feed">Open the full feed →</Link>
          </div>

          {!feed && !feedError && <div className="home-state">Loading current intelligence…</div>}
          {feedError && (
            <div className="home-state home-state-error">
              Current intelligence is unavailable. Search and source data remain accessible.
            </div>
          )}
          {feed && feed.events.length === 0 && (
            <div className="home-state">
              No current events meet the evidence threshold yet. CountyIQ will not fill an empty feed with generated content.
            </div>
          )}
          {feed && feed.events.length > 0 && (
            <div className="home-feed-preview">
              {feed.events.map((event) => <IntelligenceEventCard key={event.event_key} event={event} />)}
            </div>
          )}
        </section>

        <section className="home-section">
          <div className="home-section-heading">
            <div>
              <div className="home-eyebrow">One investigation loop</div>
              <h2>Find it, understand it, follow it</h2>
            </div>
          </div>
          <div className="home-start-grid">
            {START_POINTS.map((item) => (
              <Link key={item.to} to={item.to} className="home-start-card" style={{ borderTopColor: item.color }}>
                <strong>{item.label}</strong>
                <span>{item.description}</span>
              </Link>
            ))}
          </div>
        </section>

        <div className="home-coverage-strip">
          <span>{stats ? stats.parcel_count.toLocaleString() : '—'} parcels indexed</span>
          <span>{stats ? stats.municipality_count.toLocaleString() : '—'} municipalities</span>
          <span>{county.county_name}, {county.state}</span>
          <span>Source-backed alpha</span>
        </div>
      </main>

      <footer className="home-footer">
        <span>CountyIQ · Local property and development intelligence</span>
        <span>Verify decisions in the linked original record · Not for legal reliance</span>
      </footer>
    </>
  )
}
