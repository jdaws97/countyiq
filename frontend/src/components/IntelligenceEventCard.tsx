import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import Badge from './Badge'
import EvidencePanel from './EvidencePanel'
import { Button } from './ui'
import { formatLabel, formatShortDate } from '../lib/format'
import type { TriageStatus } from '../lib/investigationState'
import { isProjectWatched, isWatched, toggleProjectWatch, toggleWatch } from '../lib/watchlist'
import type { IntelligenceEvent } from '../types/api'

function eventColor(event: IntelligenceEvent): string {
  if (event.event_type === 'denial' || event.event_type === 'delinquency_change') return 'var(--accent-red)'
  if (event.event_type === 'approval') return 'var(--accent-green)'
  if (event.event_type === 'continuance' || event.event_type === 'condition') return 'var(--accent-gold)'
  if (event.category === 'development') return 'var(--accent-cyan)'
  return 'var(--accent-blue)'
}

export default function IntelligenceEventCard({
  event,
  expandedByDefault = false,
  showTriage = false,
  triageStatus,
  isNew = false,
  onTriage,
}: {
  event: IntelligenceEvent
  expandedByDefault?: boolean
  showTriage?: boolean
  triageStatus?: TriageStatus
  isNew?: boolean
  onTriage?: (status: TriageStatus | null) => void
}) {
  const [expanded, setExpanded] = useState(expandedByDefault)
  const [, setWatchRevision] = useState(0)

  useEffect(() => {
    const refresh = () => setWatchRevision((value) => value + 1)
    window.addEventListener('countyiq-watchlist-changed', refresh)
    return () => window.removeEventListener('countyiq-watchlist-changed', refresh)
  }, [])

  const eventDate = formatShortDate(event.event_date ?? event.detected_at)
  const confidence = event.interpretation.kind === 'llm' && event.confidence != null
    ? Math.round(event.confidence * 100)
    : null
  const projectWatched = event.project ? isProjectWatched(event.project.key) : false
  const pidns = event.related_pidns.slice(0, 8)
  const entityLinks = event.entity_links ?? []
  const linkedEntityNames = new Set(entityLinks.map((entity) => entity.matched_name.toLowerCase()))
  const unresolvedEntities = event.related_entities.filter((name) => !linkedEntityNames.has(name.toLowerCase()))

  return (
    <article
      className={`intelligence-card${expanded ? ' intelligence-card-expanded' : ''}${triageStatus ? ` intelligence-card-${triageStatus}` : ''}`}
      style={{ '--event-accent': eventColor(event) } as React.CSSProperties}
    >
      <div className="intelligence-card-topline">
        <div className="intelligence-card-badges">
          {isNew && <Badge color="var(--accent-gold)">New since last visit</Badge>}
          <Badge color={eventColor(event)}>{formatLabel(event.event_type)}</Badge>
          <Badge color={event.category === 'development' ? 'var(--accent-cyan)' : 'var(--accent-blue)'}>{formatLabel(event.category)}</Badge>
          {triageStatus && <Badge color={triageStatus === 'reviewed' ? 'var(--accent-green)' : 'var(--text-muted)'}>{triageStatus}</Badge>}
        </div>
        <time dateTime={event.event_date ?? event.detected_at}>{eventDate}</time>
      </div>

      <h2>{event.title}</h2>
      {/* Lead with the specific fact (amounts, dates); the generic significance
          sentence lives in the expanded details. */}
      <p className="intelligence-card-summary">{event.what_happened || event.why_it_matters}</p>

      <div className="intelligence-card-meta">
        {event.municipality && <span>{event.municipality}</span>}
        <span>{event.sources.length} evidence receipt{event.sources.length === 1 ? '' : 's'}</span>
        {confidence !== null && <span>{confidence}% confidence</span>}
        {event.interpretation.kind === 'deterministic' && <span>Recorded source change</span>}
        {event.interpretation.kind === 'llm' && <span>Source-grounded extraction</span>}
      </div>

      <div className="intelligence-card-actions" data-print-hidden>
        <Button tone="secondary" type="button" aria-expanded={expanded} onClick={() => setExpanded((value) => !value)}>
          {expanded ? 'Hide details' : 'Review details & evidence'}
        </Button>
        {showTriage && (
          <>
            <Button tone="quiet" type="button" onClick={() => onTriage?.(triageStatus === 'reviewed' ? null : 'reviewed')}>
              {triageStatus === 'reviewed' ? 'Mark unreviewed' : '✓ Mark reviewed'}
            </Button>
            <Button tone="quiet" type="button" onClick={() => onTriage?.(triageStatus === 'dismissed' ? null : 'dismissed')}>
              {triageStatus === 'dismissed' ? 'Restore' : 'Dismiss'}
            </Button>
          </>
        )}
      </div>

      {expanded && (
        <div className="intelligence-card-details">
          <div className="insight-grid">
            <InsightBlock label="What happened" accent={eventColor(event)}>{event.what_happened}</InsightBlock>
            <InsightBlock label="Why it matters" accent="var(--accent-purple)">{event.why_it_matters}</InsightBlock>
            <InsightBlock label="What happens next" accent="var(--accent-gold)">{event.what_happens_next}</InsightBlock>
          </div>

          {event.project && (
            <RelatedGroup label="Related project">
              <Link to={`/project/${encodeURIComponent(event.project.key)}`} className="record-link">{event.project.name} →</Link>
              <Button tone="quiet" type="button" onClick={() => { toggleProjectWatch(event.project!); setWatchRevision((value) => value + 1) }}>
                {projectWatched ? '★ Watching project' : '☆ Watch project'}
              </Button>
            </RelatedGroup>
          )}

          {(entityLinks.length > 0 || unresolvedEntities.length > 0) && (
            <RelatedGroup label="Related entities">
              {entityLinks.map((entity) => <Link key={entity.owner_id} to={`/entity/${entity.owner_id}`} className="record-link">{entity.name} →</Link>)}
              {unresolvedEntities.map((entity) => <span className="unresolved-record" key={entity}>{entity} · unresolved</span>)}
            </RelatedGroup>
          )}

          {pidns.length > 0 && (
            <RelatedGroup label="Related parcels">
              {pidns.map((pidn) => {
                const watched = isWatched(pidn)
                return (
                  <span className="parcel-record-link" key={pidn}>
                    <Link to={`/property/${pidn}`}>{pidn}</Link>
                    <button aria-label={`${watched ? 'Unwatch' : 'Watch'} parcel ${pidn}`} title={`${watched ? 'Unwatch' : 'Watch'} parcel ${pidn}`} onClick={() => { toggleWatch(pidn); setWatchRevision((value) => value + 1) }}>
                      {watched ? '★' : '☆'}
                    </button>
                  </span>
                )
              })}
              {event.related_pidns.length > pidns.length && <span className="unresolved-record">+{event.related_pidns.length - pidns.length} more</span>}
            </RelatedGroup>
          )}

          <EvidencePanel items={event.sources} title="Verify this event" intro="Inspect source facts, method, timing, caveats, and the original record before relying on this interpretation." />
        </div>
      )}
    </article>
  )
}

function InsightBlock({ label, children, accent }: { label: string; children: string; accent: string }) {
  return <div className="insight-block" style={{ '--insight-accent': accent } as React.CSSProperties}><div className="record-label">{label}</div><div>{children}</div></div>
}

function RelatedGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="related-group"><div className="record-label">{label}</div><div className="related-group-items">{children}</div></div>
}
