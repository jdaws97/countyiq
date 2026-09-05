import { useEffect, useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'

import BackButton from '../components/BackButton'
import Badge from '../components/Badge'
import IntelligenceEventCard from '../components/IntelligenceEventCard'
import PageShell from '../components/PageShell'
import Section from '../components/Section'
import { ButtonLink } from '../components/ui'
import { formatCurrencyCompact, formatLabel, formatShortDate } from '../lib/format'
import { isMunicipalityWatched, toggleMunicipalityWatch } from '../lib/watchlist'
import type { IntelligenceFeedResponse, MunicipalityPipelineMatter, MunicipalityProfile } from '../types/api'

function formatCompactCurrencyOrZero(value: number | null | undefined): string {
  if (value == null) return '--'
  if (value === 0) return '$0'
  return formatCurrencyCompact(value, { allowBillions: true })
}

export default function MunicipalityDetail() {
  const { name } = useParams<{ name: string }>()
  const navigate = useNavigate()
  const [municipality, setMunicipality] = useState<MunicipalityProfile | null>(null)
  const [feed, setFeed] = useState<IntelligenceFeedResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [, setWatchRevision] = useState(0)

  useEffect(() => {
    const refresh = () => setWatchRevision((value) => value + 1)
    window.addEventListener('countyiq-watchlist-changed', refresh)
    return () => window.removeEventListener('countyiq-watchlist-changed', refresh)
  }, [])

  useEffect(() => {
    if (!name) return
    const muniName = name
    let cancelled = false

    async function load() {
      setLoading(true)
      setError(null)
      try {
        const response = await fetch(`/api/municipalities/${encodeURIComponent(muniName)}`)
        if (!response.ok) throw new Error(`Municipality request failed (${response.status})`)
        const data: MunicipalityProfile = await response.json()
        if (cancelled) return
        setMunicipality(data)
        const feedParams = new URLSearchParams({ municipality: data.name, since_days: '365', sort: 'priority', limit: '6' })
        const feedResponse = await fetch(`/api/feed?${feedParams}`)
        if (!cancelled && feedResponse.ok) setFeed(await feedResponse.json() as IntelligenceFeedResponse)
      } catch (loadError) {
        console.error('Failed to load municipality profile', loadError)
        if (!cancelled) {
          setMunicipality(null)
          setError('Unable to load municipality profile.')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    void load()
    return () => { cancelled = true }
  }, [name])

  if (loading) return <PageShell><div className="status-message">Loading municipality…</div></PageShell>
  if (error) return <PageShell><div className="error-box" role="alert">{error}</div></PageShell>
  if (!municipality) return <PageShell><div className="error-box" role="alert">Municipality not found: {name}</div></PageShell>

  const delinquency = municipality.delinquency
  const stats = municipality.stats
  const pipeline = municipality.development_pipeline ?? null
  const radarTop = municipality.radar_top ?? []
  const events = feed?.events ?? []
  const watched = isMunicipalityWatched(municipality.name)

  return (
    <PageShell maxWidth={1100}>
      <BackButton onClick={() => navigate(-1)} />

      <div style={{ marginBottom: 28 }}>
        <div className="record-eyebrow">Municipality</div>
        <h1 className="page-title">{municipality.name}</h1>
        <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
          {municipality.muni_type && <Badge color="var(--accent-blue)">{municipality.muni_type}</Badge>}
          {municipality.county && <Badge color="var(--accent-purple)">{municipality.county} County</Badge>}
          <button
            type="button"
            className="watch-button"
            aria-pressed={watched}
            onClick={() => toggleMunicipalityWatch({ name: municipality.name })}
          >
            {watched ? '★ Watching municipality' : '☆ Watch municipality'}
          </button>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: 14, marginBottom: 28 }}>
        <StatCard label="Parcels" value={stats.parcel_count.toLocaleString()} color="var(--accent-blue)" />
        <StatCard label="Assessed value" value={formatCompactCurrencyOrZero(stats.total_assessed)} color="var(--accent-green)" />
        <StatCard label="Planning matters, 12 mo" value={pipeline ? pipeline.total_matters.toLocaleString() : '--'} color="var(--accent-cyan)" />
        <StatCard label="Opportunity parcels" value={radarTop.length ? `${radarTop.length}+` : '0'} color="var(--accent-gold)" />
        <StatCard label="Delinquent parcels" value={delinquency.delinquent_parcels.toLocaleString()} color={delinquency.delinquent_parcels > 0 ? 'var(--accent-red)' : 'var(--accent-green)'} />
      </div>

      <Section title="Planning pipeline">
        {!pipeline && (
          <div className="status-message">Municipal proceedings are not available for derived display under the current source policy.</div>
        )}
        {pipeline && pipeline.total_matters === 0 && (
          <div className="status-message">No source-backed planning, zoning, or governing-body matters were extracted for this municipality in the last {pipeline.window_days} days. CountyIQ does not fill an empty pipeline with generated content.</div>
        )}
        {pipeline && pipeline.total_matters > 0 && (
          <>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
              {pipeline.by_event_type.map((row) => (
                <Link key={row.event_type} to={`/feed?category=development&event=${encodeURIComponent(row.event_type)}&days=365`} className="record-link">
                  {formatLabel(row.event_type)} · {row.count}
                </Link>
              ))}
            </div>
            {(pipeline.policy?.length ?? 0) > 0 && (
              <MatterList label="Municipality-wide policy actions (ordinances, plans, sewer, incentives)" matters={pipeline.policy!} />
            )}
            {pipeline.upcoming.length > 0 && (
              <MatterList label="Upcoming or recently heard" matters={pipeline.upcoming} />
            )}
            <MatterList label="Recent matters" matters={pipeline.recent} />
          </>
        )}
      </Section>

      <Section title="Top opportunity parcels">
        {radarTop.length === 0 ? (
          <div className="status-message">No eligible opportunity parcels are scored in this municipality yet.</div>
        ) : (
          <div className="data-table">
            <div className="data-table-head" style={{ gridTemplateColumns: '64px 72px 1fr 70px minmax(200px, 1fr)' }}>
              <div>Score</div><div>Change</div><div>Address</div><div className="cell-right">Acres</div><div style={{ paddingLeft: 12 }}>Why it ranked</div>
            </div>
            {radarTop.map((row) => (
              <div key={row.pidn} className="data-table-row" style={{ gridTemplateColumns: '64px 72px 1fr 70px minmax(200px, 1fr)', padding: '10px 16px' }}>
                <div><span className="score-pill" style={{ '--score-color': row.opportunity_score >= 60 ? 'var(--accent-green)' : row.opportunity_score >= 40 ? 'var(--accent-gold)' : 'var(--accent-ink)' } as React.CSSProperties}>{row.opportunity_score}</span></div>
                <div>{row.is_new ? <span style={{ color: 'var(--accent-gold)', fontWeight: 600 }}>New</span> : row.opportunity_delta ? <span style={{ color: row.opportunity_delta > 0 ? 'var(--accent-green)' : 'var(--accent-red)', fontWeight: 600 }}>{row.opportunity_delta > 0 ? '▲' : '▼'} {Math.abs(row.opportunity_delta)}</span> : <span className="cell-muted">—</span>}</div>
                <div><Link to={`/property/${row.pidn}`} className="cell-strong">{row.propadr || row.pidn}</Link></div>
                <div className="cell-right">{row.acres != null ? row.acres.toFixed(1) : '--'}</div>
                <div className="cell-muted" style={{ paddingLeft: 12 }}>{row.top_signal || '--'}</div>
              </div>
            ))}
          </div>
        )}
        <div className="section-actions" style={{ marginTop: 12 }}>
          <ButtonLink to={`/radar?view=opportunity&municipality=${encodeURIComponent(municipality.name)}`} tone="secondary">Open radar for {municipality.name}</ButtonLink>
          <ButtonLink to={`/radar?view=movers&municipality=${encodeURIComponent(municipality.name)}`} tone="quiet">Movers</ButtonLink>
        </div>
      </Section>

      <Section title="Recent intelligence">
        {events.length === 0 ? (
          <div className="status-message">No feed events reference this municipality in the last year.</div>
        ) : (
          <div className="home-feed-preview">
            {events.map((event) => <IntelligenceEventCard key={event.event_key} event={event} />)}
          </div>
        )}
        <div className="section-actions" style={{ marginTop: 12 }}>
          <ButtonLink to={`/feed?municipality=${encodeURIComponent(municipality.name)}&days=365`} tone="quiet">Open the feed for {municipality.name}</ButtonLink>
        </div>
      </Section>

      <Section title="Tax status">
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: 14 }}>
          <StatCard label="Total delinquent" value={formatCompactCurrencyOrZero(delinquency.total_delinquent)} color="var(--accent-gold)" />
          <StatCard label="Oldest delinquency" value={delinquency.oldest_delinquent_year?.toString() || 'None'} color="var(--text-primary)" />
          <StatCard label="Delinquent years" value={delinquency.delinquent_years.toLocaleString()} color="var(--text-primary)" />
        </div>
        <div style={{ marginTop: 10, fontSize: 13, color: 'var(--text-muted)' }}>
          Aggregates only. Parcel-level delinquency changes appear as evidence-backed feed events; exact balances and claimant names are not displayed.
        </div>
      </Section>
    </PageShell>
  )
}

function MatterList({ label, matters }: { label: string; matters: MunicipalityPipelineMatter[] }) {
  const rows = matters
  if (rows.length === 0) return null
  return (
    <div style={{ marginBottom: 16 }}>
      <div className="record-label" style={{ marginBottom: 8 }}>{label}</div>
      <div style={{ border: '1px solid var(--border)', borderRadius: 6, overflow: 'hidden' }}>
        {rows.map((matter, index) => (
          <div key={matter.event_key} style={{ display: 'flex', gap: 12, alignItems: 'center', padding: '10px 14px', borderTop: index > 0 ? '1px solid var(--border)' : 'none' }}>
            <Badge color="var(--accent-cyan)">{formatLabel(matter.event_type)}</Badge>
            <div style={{ flex: 1, minWidth: 0 }}>
              {matter.project_key
                ? <Link to={`/project/${encodeURIComponent(matter.project_key)}`} className="cell-strong">{matter.project_name || matter.title}</Link>
                : <span className="cell-strong">{matter.title}</span>}
              {matter.related_pidns.length > 0 && (
                <div className="cell-muted" style={{ marginTop: 2 }}>
                  {matter.related_pidns.slice(0, 3).map((pidn) => <Link key={pidn} to={`/property/${pidn}`} style={{ marginRight: 8 }}>{pidn}</Link>)}
                  {matter.related_pidns.length > 3 && <span>+{matter.related_pidns.length - 3} more</span>}
                </div>
              )}
            </div>
            <time className="cell-muted" dateTime={matter.event_date ?? undefined}>{matter.event_date ? formatShortDate(matter.event_date) : '--'}</time>
          </div>
        ))}
      </div>
    </div>
  )
}

function StatCard({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)', borderRadius: 6, padding: '14px 18px' }}>
      <div className="field-label" style={{ marginBottom: 6 }}>{label}</div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 22, fontWeight: 700, color }}>{value}</div>
    </div>
  )
}
