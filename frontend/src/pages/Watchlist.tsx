import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import Badge from '../components/Badge'
import IntelligenceEventCard from '../components/IntelligenceEventCard'
import PageShell from '../components/PageShell'
import Section from '../components/Section'
import { formatCurrencyCompact } from '../lib/format'
import { getPropertyClassLabel } from '../lib/propertyLabels'
import { useFetchJson } from '../lib/useFetchJson'
import {
  getEntityWatchlist,
  getProjectWatchlist,
  getWatchlist,
  toggleEntityWatch,
  toggleProjectWatch,
  toggleWatch,
  WATCHLIST_CAP,
} from '../lib/watchlist'
import type { IntelligenceFeedResponse, WatchlistSummaryResponse } from '../types/api'

export default function Watchlist() {
  const [watched, setWatched] = useState<string[]>(() => getWatchlist())
  const [watchedProjects, setWatchedProjects] = useState(() => getProjectWatchlist())
  const [watchedEntities, setWatchedEntities] = useState(() => getEntityWatchlist())

  useEffect(() => {
    const refresh = () => {
      setWatched(getWatchlist())
      setWatchedProjects(getProjectWatchlist())
      setWatchedEntities(getEntityWatchlist())
    }
    window.addEventListener('countyiq-watchlist-changed', refresh)
    return () => window.removeEventListener('countyiq-watchlist-changed', refresh)
  }, [])

  const url = watched.length > 0
    ? `/api/parcels/summary?pidns=${watched.map(encodeURIComponent).join(',')}`
    : null
  const { data, error, loading } = useFetchJson<WatchlistSummaryResponse>(url)
  const parcelEventsUrl = watched.length > 0
    ? `/api/feed?since_days=3650&limit=20&pidns=${encodeURIComponent(watched.join(','))}`
    : null
  const projectEventsUrl = watchedProjects.length > 0
    ? `/api/feed?since_days=3650&limit=30&project_keys=${encodeURIComponent(watchedProjects.map((project) => project.key).join(','))}`
    : null
  const entityEventsUrl = watchedEntities.length > 0
    ? `/api/feed?since_days=3650&limit=30&sort=latest&entity_ids=${watchedEntities.map((entity) => entity.id).join(',')}`
    : null
  const parcelEvents = useFetchJson<IntelligenceFeedResponse>(parcelEventsUrl)
  const projectEvents = useFetchJson<IntelligenceFeedResponse>(projectEventsUrl)
  const entityEvents = useFetchJson<IntelligenceFeedResponse>(entityEventsUrl)
  const parcels = data?.parcels ?? []
  const missing = data?.missing ?? []

  const unwatch = (pidn: string) => {
    toggleWatch(pidn)
    setWatched(getWatchlist())
  }

  const changedCount = parcels.filter((p) => p.changed_recently).length

  return (
    <PageShell maxWidth={1000}>
      <div style={{ animation: 'fadeUp 0.4s ease both', marginBottom: 32 }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, letterSpacing: 3, textTransform: 'uppercase', color: 'var(--accent-gold)', marginBottom: 8 }}>
          Watchlist
        </div>
        <h1 style={{ fontFamily: 'var(--font-sans)', fontSize: 28, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 8 }}>
          Watched Intelligence
        </h1>
        <div style={{ display: 'flex', gap: 8 }}>
          <Badge color="var(--accent-blue)">
            {watched.length}/{WATCHLIST_CAP} watched
          </Badge>
          <Badge color="var(--accent-cyan)">
            {watchedProjects.length}/{WATCHLIST_CAP} projects
          </Badge>
          <Badge color="var(--accent-green)">
            {watchedEntities.length}/{WATCHLIST_CAP} entities
          </Badge>
          {changedCount > 0 && (
            <Badge color="var(--accent-gold)">{changedCount} changed in last 30 days</Badge>
          )}
        </div>
      </div>

      {loading && (
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--text-muted)', textAlign: 'center', padding: '80px 0' }}>
          Loading watchlist...
        </div>
      )}

      {!loading && error && (
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--accent-red)', textAlign: 'center', padding: '80px 0' }}>
          {error}
        </div>
      )}

      {!loading && !error && watched.length === 0 && watchedProjects.length === 0 && watchedEntities.length === 0 && (
        <Section title="Nothing watched yet">
          <div style={{ fontFamily: 'var(--font-sans)', fontSize: 14, lineHeight: 1.7, color: 'var(--text-secondary)' }}>
            Open an intelligence event or property page and press <strong>Watch</strong>.
            Entities, projects, and parcels remain in this browser and their source-backed events appear here.
          </div>
        </Section>
      )}

      {watchedEntities.length > 0 && (
        <Section title={`Watched entities (${watchedEntities.length})`}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 14 }}>
            {watchedEntities.map((entity) => (
              <div key={entity.id} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <Link to={`/entity/${entity.id}`} style={{ textDecoration: 'none' }}>
                  <Badge color="var(--accent-green)">{entity.name} →</Badge>
                </Link>
                <button
                  onClick={() => toggleEntityWatch(entity)}
                  style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)', background: 'transparent', border: '1px solid var(--border)', borderRadius: 4, padding: '3px 7px', cursor: 'pointer' }}
                >
                  remove
                </button>
              </div>
            ))}
          </div>
          {entityEvents.loading && <LoadingLabel>Loading entity intelligence…</LoadingLabel>}
          {entityEvents.error && <ErrorLabel>{entityEvents.error}</ErrorLabel>}
          {!entityEvents.loading && !entityEvents.error && (entityEvents.data?.events.length ?? 0) === 0 && (
            <EmptyLabel>No events are linked to these entities yet.</EmptyLabel>
          )}
          {(entityEvents.data?.events.length ?? 0) > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {entityEvents.data!.events.map((event) => <IntelligenceEventCard key={event.event_key} event={event} />)}
            </div>
          )}
        </Section>
      )}

      {watchedProjects.length > 0 && (
        <Section title={`Watched projects (${watchedProjects.length})`}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 14 }}>
            {watchedProjects.map((project) => (
              <div key={project.key} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <Link to={`/project/${encodeURIComponent(project.key)}`} style={{ textDecoration: 'none' }}>
                  <Badge color="var(--accent-cyan)">{project.name} →</Badge>
                </Link>
                <button
                  onClick={() => toggleProjectWatch(project)}
                  style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)', background: 'transparent', border: '1px solid var(--border)', borderRadius: 4, padding: '3px 7px', cursor: 'pointer' }}
                >
                  remove
                </button>
              </div>
            ))}
          </div>
          {projectEvents.loading && <LoadingLabel>Loading project intelligence…</LoadingLabel>}
          {projectEvents.error && <ErrorLabel>{projectEvents.error}</ErrorLabel>}
          {!projectEvents.loading && !projectEvents.error && (projectEvents.data?.events.length ?? 0) === 0 && (
            <EmptyLabel>No project events are available yet.</EmptyLabel>
          )}
          {(projectEvents.data?.events.length ?? 0) > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {projectEvents.data!.events.map((event) => <IntelligenceEventCard key={event.event_key} event={event} />)}
            </div>
          )}
        </Section>
      )}

      {!loading && !error && parcels.length > 0 && (
        <Section title={`Parcels (${parcels.length})`}>
          <div style={{ border: '1px solid var(--border)', borderRadius: 6, overflow: 'hidden' }}>
            {parcels.map((p, i) => (
              <div
                key={p.pidn}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '2fr 1fr 1fr 1fr auto',
                  gap: 12,
                  alignItems: 'center',
                  padding: '12px 16px',
                  borderTop: i > 0 ? '1px solid var(--border)' : 'none',
                  background: p.changed_recently ? 'color-mix(in srgb, var(--accent-gold) 6%, transparent)' : 'transparent',
                }}
              >
                <div style={{ minWidth: 0 }}>
                  <Link
                    to={`/property/${p.pidn}`}
                    style={{ fontFamily: 'var(--font-sans)', fontSize: 14, fontWeight: 600, color: 'var(--accent-blue)', textDecoration: 'none' }}
                  >
                    {p.propadr ?? p.pidn}
                  </Link>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {p.owner_full ?? 'Owner not displayed'} · {p.municipality ?? '--'}
                  </div>
                </div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-secondary)' }}>
                  {p.aprtotal !== null ? formatCurrencyCompact(p.aprtotal, { allowBillions: true }) : '--'}
                  <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{getPropertyClassLabel(p.class) || p.class || '--'}</div>
                </div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: p.has_tax_delinquency ? 'var(--accent-red)' : 'var(--text-muted)' }}>
                  {p.has_tax_delinquency ? 'flagged' : 'current'}
                  <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>taxes</div>
                </div>
                <div>
                  {p.changed_recently ? (
                    <Badge color="var(--accent-gold)">changed {p.changed_at ? new Date(p.changed_at).toLocaleDateString() : ''}</Badge>
                  ) : (
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}>no recent change</span>
                  )}
                </div>
                <button
                  onClick={() => unwatch(p.pidn)}
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 11,
                    color: 'var(--text-muted)',
                    background: 'transparent',
                    border: '1px solid var(--border)',
                    borderRadius: 4,
                    padding: '4px 10px',
                    cursor: 'pointer',
                  }}
                >
                  Unwatch
                </button>
              </div>
            ))}
          </div>
        </Section>
      )}

      {!loading && missing.length > 0 && (
        <Section title={`No longer found (${missing.length})`}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)', display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {missing.map((pidn) => (
              <span key={pidn}>
                {pidn}
                <button
                  onClick={() => unwatch(pidn)}
                  style={{ marginLeft: 6, fontSize: 10, color: 'var(--text-muted)', background: 'transparent', border: 'none', cursor: 'pointer', textDecoration: 'underline' }}
                >
                  remove
                </button>
              </span>
            ))}
          </div>
        </Section>
      )}

      {watched.length > 0 && (
        <Section title="Recent intelligence for watched parcels">
          {parcelEvents.loading && <LoadingLabel>Loading parcel intelligence…</LoadingLabel>}
          {parcelEvents.error && <ErrorLabel>{parcelEvents.error}</ErrorLabel>}
          {!parcelEvents.loading && !parcelEvents.error && (parcelEvents.data?.events.length ?? 0) === 0 && (
            <EmptyLabel>No parcel events are available yet.</EmptyLabel>
          )}
          {(parcelEvents.data?.events.length ?? 0) > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {parcelEvents.data!.events.map((event) => <IntelligenceEventCard key={event.event_key} event={event} />)}
            </div>
          )}
        </Section>
      )}
    </PageShell>
  )
}


function LoadingLabel({ children }: { children: React.ReactNode }) {
  return <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)', padding: '18px 0' }}>{children}</div>
}


function ErrorLabel({ children }: { children: React.ReactNode }) {
  return <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--accent-red)', padding: '12px 0' }}>{children}</div>
}


function EmptyLabel({ children }: { children: React.ReactNode }) {
  return <div style={{ fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--text-secondary)', padding: '12px 0' }}>{children}</div>
}
