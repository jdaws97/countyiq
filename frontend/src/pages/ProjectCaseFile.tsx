import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import Badge from '../components/Badge'
import IntelligenceEventCard from '../components/IntelligenceEventCard'
import PageShell from '../components/PageShell'
import Section from '../components/Section'
import { useFetchJson } from '../lib/useFetchJson'
import {
  isProjectWatched,
  toggleProjectWatch,
} from '../lib/watchlist'
import type { IntelligenceEntityLink, IntelligenceFeedResponse } from '../types/api'


export default function ProjectCaseFile() {
  const { key = '' } = useParams<{ key: string }>()
  const [, setWatchRevision] = useState(0)
  const url = key
    ? `/api/feed?since_days=3650&limit=100&sort=latest&project_keys=${encodeURIComponent(key)}`
    : null
  const { data, error, loading } = useFetchJson<IntelligenceFeedResponse>(url)
  const events = useMemo(() => data?.events ?? [], [data])
  const project = events.find((event) => event.project)?.project ?? { key, name: key }
  const watched = Boolean(key) && isProjectWatched(key)

  useEffect(() => {
    const refresh = () => setWatchRevision((value) => value + 1)
    window.addEventListener('countyiq-watchlist-changed', refresh)
    return () => window.removeEventListener('countyiq-watchlist-changed', refresh)
  }, [])

  const municipalities = useMemo(
    () => Array.from(new Set(events.map((event) => event.municipality).filter((value): value is string => Boolean(value)))),
    [events],
  )
  const pidns = useMemo(
    () => Array.from(new Set(events.flatMap((event) => event.related_pidns))),
    [events],
  )
  const entities = useMemo(() => {
    const byId = new Map<number, IntelligenceEntityLink>()
    for (const event of events) {
      for (const entity of event.entity_links ?? []) byId.set(entity.owner_id, entity)
    }
    return Array.from(byId.values())
  }, [events])

  return (
    <PageShell maxWidth={1000}>
      <div style={{ animation: 'fadeUp 0.4s ease both', marginBottom: 28 }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, letterSpacing: 3, textTransform: 'uppercase', color: 'var(--accent-cyan)', marginBottom: 8 }}>
          Project case file
        </div>
        <h1 style={{ fontFamily: 'var(--font-sans)', fontSize: 32, lineHeight: 1.15, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 10 }}>
          {project.name || 'Project'}
        </h1>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
          <Badge color="var(--accent-cyan)">{events.length} source-backed event{events.length === 1 ? '' : 's'}</Badge>
          {municipalities.map((municipality) => (
            <Badge key={municipality} color="var(--text-muted)">{municipality}</Badge>
          ))}
          {key && (
            <button
              onClick={() => {
                toggleProjectWatch(project)
                setWatchRevision((value) => value + 1)
              }}
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                color: watched ? 'var(--accent-gold)' : 'var(--text-secondary)',
                background: 'transparent',
                border: `1px solid ${watched ? 'var(--accent-gold)' : 'var(--border)'}`,
                borderRadius: 5,
                padding: '5px 10px',
                cursor: 'pointer',
              }}
            >
              {watched ? '★ Watching project' : '☆ Watch project'}
            </button>
          )}
        </div>
      </div>

      {loading && <Status color="var(--text-muted)">Loading project evidence…</Status>}
      {!loading && error && <Status color="var(--accent-red)">{error}</Status>}
      {!loading && !error && events.length === 0 && (
        <Section title="No linked evidence yet">
          <div style={{ fontFamily: 'var(--font-sans)', fontSize: 14, lineHeight: 1.7, color: 'var(--text-secondary)' }}>
            This project key is not linked to an intelligence event in the current county dataset.
          </div>
        </Section>
      )}

      {events.length > 0 && (entities.length > 0 || pidns.length > 0) && (
        <Section title="Connected record">
          <div style={{ display: 'grid', gap: 14 }}>
            {entities.length > 0 && (
              <div>
                <Label>Entities</Label>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {entities.map((entity) => (
                    <Link key={entity.owner_id} to={`/entity/${entity.owner_id}`} style={{ textDecoration: 'none' }}>
                      <Badge color="var(--accent-green)">{entity.name} →</Badge>
                    </Link>
                  ))}
                </div>
              </div>
            )}
            {pidns.length > 0 && (
              <div>
                <Label>Parcels</Label>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {pidns.slice(0, 20).map((pidn) => (
                    <Link key={pidn} to={`/property/${pidn}`} style={{ textDecoration: 'none' }}>
                      <Badge color="var(--accent-blue)">{pidn} →</Badge>
                    </Link>
                  ))}
                  {pidns.length > 20 && <Badge color="var(--text-muted)">+{pidns.length - 20} more</Badge>}
                </div>
              </div>
            )}
          </div>
        </Section>
      )}

      {events.length > 0 && (
        <Section title={`Evidence timeline (${events.length})`}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {events.map((event) => <IntelligenceEventCard key={event.event_key} event={event} />)}
          </div>
        </Section>
      )}
    </PageShell>
  )
}


function Label({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: 1.5, textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 6 }}>
      {children}
    </div>
  )
}


function Status({ children, color }: { children: React.ReactNode; color: string }) {
  return <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color, textAlign: 'center', padding: '80px 0' }}>{children}</div>
}
