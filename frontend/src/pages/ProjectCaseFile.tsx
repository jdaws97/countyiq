import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import Badge from '../components/Badge'
import IntelligenceEventCard from '../components/IntelligenceEventCard'
import NearbyParcels from '../components/NearbyParcels'
import PageShell from '../components/PageShell'
import ReportActions from '../components/ReportActions'
import Section from '../components/Section'
import { Button, StatusMessage } from '../components/ui'
import { downloadText, toCsv } from '../lib/investigationState'
import { openEvidenceReceipt } from '../lib/evidence'
import { formatLabel } from '../lib/format'
import { useFetchJson } from '../lib/useFetchJson'
import {
  isProjectWatched,
  toggleProjectWatch,
} from '../lib/watchlist'
import type { IntelligenceEntityLink, ProjectCaseResponse } from '../types/api'


export default function ProjectCaseFile() {
  const { key = '' } = useParams<{ key: string }>()
  const [expandedEvents, setExpandedEvents] = useState<Set<string>>(() => new Set())
  const expandEvent = (eventKey: string, expanded = true) => {
    setExpandedEvents((current) => {
      const next = new Set(current)
      if (expanded) next.add(eventKey)
      else next.delete(eventKey)
      return next
    })
  }
  const openRecord = (eventKey: string, evidenceId: string) => {
    expandEvent(eventKey)
    requestAnimationFrame(() => {
      openEvidenceReceipt(evidenceId)
      document.getElementById(evidenceId)?.scrollIntoView({ block: 'center' })
    })
  }
  const [, setWatchRevision] = useState(0)
  const url = key
    ? `/api/cases/projects/${encodeURIComponent(key)}`
    : null
  const { data, error, loading } = useFetchJson<ProjectCaseResponse>(url)
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
  const parcelReferences = useMemo(() => {
    const values = events.flatMap((event) => event.sources.flatMap((source) => {
      const structured = source.details.parcel_references
      if (Array.isArray(structured)) return structured.filter((value): value is string => typeof value === 'string' && Boolean(value.trim()))
      const legacy = source.details.parcel_reference
      return typeof legacy === 'string' && legacy.trim() ? [legacy] : []
    }))
    return Array.from(new Set(values))
  }, [events])
  const entities = useMemo(() => {
    const byId = new Map<number, IntelligenceEntityLink>()
    for (const event of events) {
      for (const entity of event.entity_links ?? []) byId.set(entity.owner_id, entity)
    }
    return Array.from(byId.values())
  }, [events])

  const exportCsv = () => {
    const scope = data?.has_more
      ? 'Partial export: additional events exist outside this view'
      : 'Loaded linked records; source coverage may be incomplete'
    const rows: Array<Array<string | number | null>> = [['Event date', 'Detected at', 'Type', 'Title', 'Municipality', 'Recorded action', 'Evidence receipts', 'Source documents', 'Export scope']]
    for (const event of events) rows.push([
      event.event_date, event.detected_at, event.event_type, event.title, event.municipality,
      event.what_happened, event.sources.length,
      Array.from(new Set(event.sources.map((source) => source.document_url || source.url).filter(Boolean))).join(' | '),
      scope,
    ])
    downloadText(`countyiq-project-${project.key || 'case-file'}.csv`, toCsv(rows), 'text/csv')
  }

  return (
    <PageShell maxWidth={1000}>
      <div style={{ marginBottom: 28 }}>
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
              data-print-hidden
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
          {events.length > 0 && <Button tone="quiet" data-print-hidden onClick={exportCsv}>Export CSV</Button>}
          <ReportActions label={`${project.name || 'Project'} case file`} />
        </div>
      </div>

      {loading && <StatusMessage>Loading project evidence…</StatusMessage>}
      {!loading && error && <StatusMessage tone="error">{error}</StatusMessage>}
      {!loading && !error && events.length === 0 && (
        <Section title="No linked evidence yet">
          <div style={{ fontFamily: 'var(--font-sans)', fontSize: 14, lineHeight: 1.7, color: 'var(--text-secondary)' }}>
            This project key is not linked to an intelligence event in the current county dataset.
          </div>
        </Section>
      )}

      {data?.summary && events.length > 0 && (
        <Section title="Current recorded status">
          <h2>{data.summary.status}</h2>
          {data.summary.as_of && <p>Latest dated activity: {data.summary.as_of}</p>}
          {data.summary.latest_change && <p>{data.summary.latest_change} <a onClick={() => expandEvent(data.summary.latest_event_key!)} href={`#project-event-${data.summary.latest_event_key}`}>Verify record →</a></p>}
          <p>{data.summary.caveat}</p>
          {data.summary.history_incomplete && <p role="status">Some history is undated or outside this view. Verify the full source history before relying on this status.</p>}
          {data.summary.decisions.length > 0 && <><h3>Recorded decisions and scope</h3><ul>{data.summary.decisions.map((item, i) => <li key={item.event_key + '-decision-' + i}><strong>{item.scope && formatLabel(item.scope) + ': '}{item.decision}</strong>{item.body && <> — {item.body}</>}{item.matter && <> · {item.matter.replace(/_/g, ' ')}</>} <a onClick={() => openRecord(item.event_key, item.evidence_id)} href={'#' + item.evidence_id}>Verify record ({item.record_date ?? 'undated'}) →</a></li>)}</ul></>}
          {data.summary.conditions.length > 0 && <><h3>Conditions to verify</h3><ul>{data.summary.conditions.map((item, i) => <li key={`${item.event_key}-${i}`}><strong>{item.text}</strong> — {item.status} <a onClick={() => openRecord(item.event_key, item.evidence_id)} href={'#' + item.evidence_id}>Source ({item.record_date ?? 'undated'}) →</a></li>)}</ul></>}
          {data.summary.milestones.length > 0 && <><h3>Stated milestones</h3><ul>{data.summary.milestones.map((item, i) => <li key={`${item.event_key}-${i}`}><strong>{item.kind && formatLabel(item.kind) + ': '}{item.text}</strong> — {item.status} <a onClick={() => openRecord(item.event_key, item.evidence_id)} href={'#' + item.evidence_id}>Source ({item.record_date ?? 'undated'}) →</a></li>)}</ul></>}
        </Section>
      )}

      {events.length > 0 && (entities.length > 0 || pidns.length > 0 || parcelReferences.length > 0) && (
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
                <Label>Linked parcels ({pidns.length})</Label>
                <p>These are matched parcel records, not a complete project boundary. Compare them with the source references below.</p>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {pidns.map((pidn) => (
                    <Link key={pidn} to={`/property/${pidn}`} style={{ textDecoration: 'none' }}>
                      <Badge color="var(--accent-blue)">{pidn} →</Badge>
                    </Link>
                  ))}
                </div>
              </div>
            )}
            {parcelReferences.length > 0 && (
              <div>
                <Label>Parcel references recorded in the source</Label>
                {pidns.length === 0 && <p>No parcel records have been linked to these references.</p>}
                <ul style={{ paddingLeft: 20, overflowWrap: 'anywhere' }}>
                  {parcelReferences.map((reference) => <li key={reference}>{reference}</li>)}
                </ul>
                <p>References may include unresolved or inconsistent identifiers. Verify them in the evidence timeline before relying on the linked parcel list.</p>
              </div>
            )}
          </div>
        </Section>
      )}

      {events.length > 0 && pidns.length > 0 && (
        <NearbyParcels projectKey={key} title="Parcels near this project" />
      )}

      {events.length > 0 && (
        <Section title={`Evidence timeline (${events.length})`}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {events.map((event) => <div key={event.event_key} id={`project-event-${event.event_key}`}><IntelligenceEventCard event={event} printEvidence expanded={expandedEvents.has(event.event_key)} onExpandedChange={(expanded) => expandEvent(event.event_key, expanded)} /></div>)}
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
