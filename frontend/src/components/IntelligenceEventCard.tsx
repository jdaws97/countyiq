import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import Badge from './Badge'
import EvidencePanel, { CitedText } from './EvidencePanel'
import { useSourceViewer } from '../lib/useSourceViewer'
import { Button, ButtonLink } from './ui'
import { formatLabel, formatShortDate } from '../lib/format'
import { describeRecordDate } from '../lib/recordDates'
import type { TriageStatus } from '../lib/investigationState'
import { isProjectWatched, isWatched, toggleProjectWatch, toggleWatch } from '../lib/watchlist'
import type { EvidenceItem, IntelligenceEvent, RecordDate } from '../types/api'

function recordDates(details: Record<string, unknown> | undefined): RecordDate[] {
  const dates = details?.record_dates
  if (!Array.isArray(dates)) {
    return []
  }
  return dates.filter(
    (date): date is RecordDate =>
      Boolean(date) &&
      typeof date === 'object' &&
      typeof date.label === 'string' &&
      typeof date.status === 'string',
  )
}

function matchedProperties(details: Record<string, unknown> | undefined) {
  const properties = details?.matched_properties
  if (!Array.isArray(properties)) {
    return []
  }
  return properties.flatMap((property) => {
    if (!property || typeof property !== 'object' || typeof property.pidn !== 'string') {
      return []
    }
    return [
      {
        pidn: property.pidn,
        address: typeof property.address === 'string' ? property.address : null,
      },
    ]
  })
}

function eventColor(event: IntelligenceEvent): string {
  if (event.event_type === 'municipal_record') {
    return 'var(--accent-blue)'
  }
  if (event.event_type === 'denial' || event.event_type === 'delinquency_change') {
    return 'var(--accent-red)'
  }
  if (event.event_type === 'approval') {
    return 'var(--accent-green)'
  }
  if (event.event_type === 'continuance' || event.event_type === 'condition') {
    return 'var(--accent-gold)'
  }
  if (event.category === 'development') {
    return 'var(--accent-cyan)'
  }
  return 'var(--accent-blue)'
}

function eventTypeLabel(
  event: IntelligenceEvent,
  proceedingDetails: Record<string, unknown> | undefined,
) {
  if (event.event_type === 'municipal_record') {
    return 'Municipal record'
  }
  if (
    event.event_type === 'scoped_decision' &&
    typeof proceedingDetails?.decision_scope === 'string'
  ) {
    return `${formatLabel(proceedingDetails.decision_scope)} decision`
  }
  return formatLabel(event.event_type)
}

export default function IntelligenceEventCard({
  event,
  expandedByDefault = false,
  printEvidence = false,
  currentProjectKey,
  currentPidn,
  expanded: controlledExpanded,
  onExpandedChange,
  showTriage = false,
  triageStatus,
  isNew = false,
  onTriage,
}: {
  event: IntelligenceEvent
  expandedByDefault?: boolean
  printEvidence?: boolean
  currentProjectKey?: string
  currentPidn?: string
  expanded?: boolean
  onExpandedChange?: (expanded: boolean) => void
  showTriage?: boolean
  triageStatus?: TriageStatus
  isNew?: boolean
  onTriage?: (status: TriageStatus | null) => void
}) {
  const openSource = useSourceViewer()
  const [localExpanded, setLocalExpanded] = useState(expandedByDefault)
  const expanded = controlledExpanded ?? localExpanded
  const toggleExpanded = () => {
    setLocalExpanded(!expanded)
    onExpandedChange?.(!expanded)
  }
  const [, setWatchRevision] = useState(0)
  const [showAllParcels, setShowAllParcels] = useState(false)

  useEffect(() => {
    const refresh = () => setWatchRevision((value) => value + 1)
    window.addEventListener('countyiq-watchlist-changed', refresh)
    return () => window.removeEventListener('countyiq-watchlist-changed', refresh)
  }, [])

  const eventDate = event.event_date ? formatShortDate(event.event_date) : 'Event date unverified'
  const proceedingDetails = event.sources.find((source) =>
    [2, 3].includes(Number(source.details?.contract_version)),
  )?.details
  const explanationDetails = event.sources.find(
    (source) => Number(source.details?.explanation_version) === 1,
  )?.details
  const sourceDetails = explanationDetails ?? proceedingDetails
  const nextStep =
    typeof explanationDetails?.explanation_next_step === 'string'
      ? explanationDetails.explanation_next_step
      : null
  const sourcedDates = recordDates(sourceDetails).slice(0, 3)
  const relatedProperties = [
    ...new Map(
      matchedProperties(sourceDetails).map((property) => [property.pidn, property]),
    ).values(),
  ].filter((property) => property.pidn !== currentPidn)
  const conditions = Array.isArray(proceedingDetails?.conditions)
    ? proceedingDetails.conditions.flatMap((value, index) =>
        typeof value === 'string' && value.trim() ? [{ text: value, index }] : [],
      )
    : []
  const milestones = Array.isArray(proceedingDetails?.milestones)
    ? proceedingDetails.milestones.flatMap((value, index) =>
        value && typeof value === 'object' && typeof value.text === 'string' && value.text.trim()
          ? [{ text: value.text, kind: typeof value.kind === 'string' ? value.kind : null, index }]
          : [],
      )
    : []
  const sourceFor = (marker: string) =>
    event.sources.find(
      (source) =>
        Array.isArray(source.details?.supports) && source.details.supports.includes(marker),
    )
  const projectWatched = event.project ? isProjectWatched(event.project.key) : false
  const showProject = event.project && event.project.key !== currentProjectKey
  const sourceMatchedPidns = new Set(relatedProperties.map((property) => property.pidn))
  const remainingPidns = event.related_pidns.filter(
    (pidn) => pidn !== currentPidn && !sourceMatchedPidns.has(pidn),
  )
  const pidns = showAllParcels || printEvidence ? remainingPidns : remainingPidns.slice(0, 8)
  const entityLinks = event.entity_links ?? []
  const linkedEntityNames = new Set(entityLinks.map((entity) => entity.matched_name.toLowerCase()))
  const unresolvedEntities = event.related_entities.filter(
    (name) => !linkedEntityNames.has(name.toLowerCase()),
  )

  return (
    <article
      className={`intelligence-card${expanded ? ' intelligence-card-expanded' : ''}${triageStatus ? ` intelligence-card-${triageStatus}` : ''}`}
      style={{ '--event-accent': eventColor(event) } as React.CSSProperties}
    >
      <div className="intelligence-card-topline">
        <div className="intelligence-card-badges">
          {isNew && <Badge color="var(--accent-gold)">New since last visit</Badge>}
          <Badge color={eventColor(event)}>{eventTypeLabel(event, sourceDetails)}</Badge>
          {triageStatus && (
            <Badge
              color={triageStatus === 'reviewed' ? 'var(--accent-green)' : 'var(--text-muted)'}
            >
              {triageStatus}
            </Badge>
          )}
        </div>
        {event.event_date ? (
          <time dateTime={event.event_date}>{eventDate}</time>
        ) : (
          <span title={'First observed ' + formatShortDate(event.detected_at)}>{eventDate}</span>
        )}
      </div>

      <h2>{event.title}</h2>
      <p className="intelligence-card-summary">
        <CitedText text={event.what_happened} evidence={event.sources} />
      </p>

      {sourcedDates.length > 0 && (
        <div
          aria-label="Dates stated in the source"
          style={{
            display: 'grid',
            gap: 4,
            marginTop: 10,
            padding: '8px 10px',
            color: 'var(--text-secondary)',
            background: 'var(--bg-panel)',
            borderLeft: '2px solid var(--event-accent)',
            fontFamily: 'var(--font-mono)',
            fontSize: 12,
            lineHeight: 1.45,
          }}
        >
          {sourcedDates.map((recordDate, index) => (
            <div key={`${recordDate.source_id}-${recordDate.label}-${index}`}>
              <CitedText
                text={`${describeRecordDate(recordDate)} [Evidence:source:${recordDate.source_id}]`}
                evidence={event.sources}
              />
            </div>
          ))}
        </div>
      )}

      {relatedProperties.length > 0 && (
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: '5px 8px',
            marginTop: 10,
            fontFamily: 'var(--font-sans)',
            fontSize: 13,
          }}
        >
          <span style={{ color: 'var(--text-muted)' }}>Related properties:</span>
          {relatedProperties.map((property) => (
            <Link key={property.pidn} to={`/property/${property.pidn}`}>
              {property.address ?? property.pidn}
            </Link>
          ))}
        </div>
      )}

      <div className="intelligence-card-meta">
        {event.municipality && <span>{event.municipality}</span>}
        {sourceDetails?.record_status === 'scheduled' && (
          <span>Scheduled item · outcome unverified</span>
        )}
        {sourceDetails?.record_status === 'recommendation' && (
          <span>Recommendation · final decision unverified</span>
        )}
        {proceedingDetails?.discovery_eligible === false && <span>Property history</span>}
        {typeof proceedingDetails?.decision_authority === 'string' && (
          <span>{proceedingDetails.decision_authority}</span>
        )}
        {proceedingDetails?.identity_status === 'needs_review' && (
          <span>Source identity conflict · linking requires review</span>
        )}
        {proceedingDetails?.location_status === 'location_not_resolved' &&
          Array.isArray(proceedingDetails.parcel_references) &&
          proceedingDetails.parcel_references.length > 0 && <span>Parcel location unverified</span>}
      </div>

      <div className="intelligence-card-actions" data-print-hidden>
        {event.project && showProject && (
          <ButtonLink
            to={`/project/${encodeURIComponent(event.project.key)}`}
            aria-label={`Open project: ${event.project.name}`}
          >
            Open project →
          </ButtonLink>
        )}
        <Button tone="secondary" type="button" aria-expanded={expanded} onClick={toggleExpanded}>
          {expanded ? 'Less detail' : 'Read more'}
        </Button>
        {event.sources.length > 0 && (
          <Button tone="quiet" type="button" onClick={() => openSource(event.sources)}>
            View source{event.sources.length > 1 ? 's' : ''}
          </Button>
        )}
        {!event.project &&
          event.related_pidns.length === 1 &&
          event.related_pidns[0] !== currentPidn && (
            <Button tone="quiet" type="button" onClick={() => toggleWatch(event.related_pidns[0])}>
              {isWatched(event.related_pidns[0]) ? 'Watching property' : 'Watch property'}
            </Button>
          )}
        {event.project && (
          <Button tone="quiet" type="button" onClick={() => toggleProjectWatch(event.project!)}>
            {projectWatched ? 'Watching project' : 'Watch project'}
          </Button>
        )}
        {showTriage && (
          <>
            <Button
              tone="quiet"
              type="button"
              onClick={() => onTriage?.(triageStatus === 'reviewed' ? null : 'reviewed')}
            >
              {triageStatus === 'reviewed' ? 'Mark unreviewed' : '✓ Mark reviewed'}
            </Button>
            <Button
              tone="quiet"
              type="button"
              onClick={() => onTriage?.(triageStatus === 'dismissed' ? null : 'dismissed')}
            >
              {triageStatus === 'dismissed' ? 'Restore' : 'Dismiss'}
            </Button>
          </>
        )}
      </div>

      {(expanded || printEvidence) && (
        <div
          className="intelligence-card-details"
          hidden={!expanded}
          data-print-evidence={printEvidence || undefined}
        >
          {nextStep && (
            <p className="intelligence-next-step">
              <strong>What to check next: </strong>
              <CitedText text={nextStep} evidence={event.sources} />
            </p>
          )}
          {conditions.length > 0 && (
            <div className="recorded-event-facts">
              <h3>Stated conditions</h3>
              <p>Completion is not established by this record.</p>
              <ul>
                {conditions.map((item) => (
                  <li key={item.index}>
                    {item.text} <FactSource evidence={sourceFor(`condition:${item.index}`)} />
                  </li>
                ))}
              </ul>
            </div>
          )}
          {milestones.length > 0 && (
            <div className="recorded-event-facts">
              <h3>Stated milestones</h3>
              <p>A stated date does not establish that the action occurred.</p>
              <ul>
                {milestones.map((item) => (
                  <li key={item.index}>
                    {typeof item.kind === 'string' && item.kind !== 'other' && (
                      <strong>{formatLabel(item.kind)}: </strong>
                    )}
                    {item.text} <FactSource evidence={sourceFor(`milestone:${item.index}`)} />
                  </li>
                ))}
              </ul>
            </div>
          )}

          {event.project && showProject && (
            <RelatedGroup label="Related project">
              <Link
                to={`/project/${encodeURIComponent(event.project.key)}`}
                className="record-link"
              >
                {event.project.name} →
              </Link>
              <Button
                tone="quiet"
                type="button"
                onClick={() => {
                  toggleProjectWatch(event.project!)
                  setWatchRevision((value) => value + 1)
                }}
              >
                {projectWatched ? '★ Watching project' : '☆ Watch project'}
              </Button>
            </RelatedGroup>
          )}

          {(entityLinks.length > 0 || unresolvedEntities.length > 0) && (
            <RelatedGroup label="Organizations named in the record">
              {entityLinks.map((entity) => (
                <Link
                  key={entity.owner_id}
                  to={`/entity/${entity.owner_id}`}
                  className="record-link"
                >
                  {entity.name} →
                </Link>
              ))}
              {unresolvedEntities.map((entity) => (
                <span className="unresolved-record" key={entity}>
                  {entity} · ownership link not established
                </span>
              ))}
            </RelatedGroup>
          )}

          {pidns.length > 0 && (
            <RelatedGroup label="Related parcels">
              {pidns.map((pidn) => {
                const watched = isWatched(pidn)
                return (
                  <span className="parcel-record-link" key={pidn}>
                    <Link to={`/property/${pidn}`}>{pidn}</Link>
                    <button
                      aria-label={`${watched ? 'Unwatch' : 'Watch'} parcel ${pidn}`}
                      title={`${watched ? 'Unwatch' : 'Watch'} parcel ${pidn}`}
                      onClick={() => {
                        toggleWatch(pidn)
                        setWatchRevision((value) => value + 1)
                      }}
                    >
                      {watched ? '★' : '☆'}
                    </button>
                  </span>
                )
              })}
              {remainingPidns.length > 8 && !printEvidence && (
                <Button
                  tone="quiet"
                  type="button"
                  aria-expanded={showAllParcels}
                  onClick={() => setShowAllParcels((current) => !current)}
                >
                  {showAllParcels
                    ? 'Show fewer properties'
                    : `Show all ${remainingPidns.length} additional linked properties`}
                </Button>
              )}
            </RelatedGroup>
          )}

          {printEvidence && <EvidencePanel items={event.sources} />}
        </div>
      )}
    </article>
  )
}

function RelatedGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="related-group">
      <div className="record-label">{label}</div>
      <div className="related-group-items">{children}</div>
    </div>
  )
}

function FactSource({ evidence }: { evidence?: EvidenceItem }) {
  const openSource = useSourceViewer()
  return evidence ? (
    <button type="button" className="source-catalog-button" onClick={() => openSource([evidence])}>
      View source
    </button>
  ) : null
}
