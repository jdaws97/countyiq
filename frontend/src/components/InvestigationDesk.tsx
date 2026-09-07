import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import type { IntelligenceEvent, PropertyReport } from '../types/api'
import EvidencePanel, { CitedText } from './EvidencePanel'
import { SourceContent } from './SourceViewer'
import ParcelContextMap from './ParcelContextMap'
import { formatCurrency, formatLabel, formatShortDate } from '../lib/format'
import { describeRecordDate } from '../lib/recordDates'
import { activityLabel, investigationDetails, supportingSource } from '../lib/investigation'
import { sourceTitle } from '../lib/customerEvidence'
import { useFetchJson } from '../lib/useFetchJson'
import { useSourceViewer } from '../lib/useSourceViewer'
import type { TriageStatus } from '../lib/investigationState'
import {
  getMunicipalityWatchlist,
  isProjectWatched,
  isWatched,
  toggleMunicipalityWatch,
  toggleProjectWatch,
  toggleWatch,
} from '../lib/watchlist'
import './InvestigationDesk.css'

export default function InvestigationDesk({
  events,
  triage,
  onTriage,
  footer,
}: {
  events: IntelligenceEvent[]
  triage?: Record<string, TriageStatus>
  onTriage?: (eventKey: string, status: TriageStatus | null) => void
  footer?: React.ReactNode
}) {
  const [params, setParams] = useSearchParams()
  const requested = params.get('record')
  const selected = requested ? events.find((event) => event.event_key === requested) : events[0]
  const detailHeading = useRef<HTMLHeadingElement>(null)
  const desk = useRef<HTMLDivElement>(null)
  const listScroll = useRef<number | null>(null)
  const previousSelection = useRef<string | null>(null)
  useEffect(() => {
    if (requested) {
      detailHeading.current?.focus({ preventScroll: true })
    }
    if (window.matchMedia('(max-width: 900px)').matches) {
      if (requested) {
        desk.current
          ?.querySelector('.investigation-reading-pane')
          ?.scrollIntoView({ block: 'start' })
      } else if (previousSelection.current) {
        if (listScroll.current != null) {
          window.scrollTo({ top: listScroll.current })
        } else {
          desk.current?.scrollIntoView({ block: 'start' })
        }
      }
    }
    previousSelection.current = requested
  }, [requested])
  const select = (event: IntelligenceEvent | null) => {
    if (event && !requested) {
      listScroll.current = window.scrollY
    }
    setParams(
      (current) => {
        const next = new URLSearchParams(current)
        if (event) {
          next.set('record', event.event_key)
        } else {
          next.delete('record')
        }
        return next
      },
      { preventScrollReset: true },
    )
  }
  return (
    <div
      ref={desk}
      className={`investigation-desk${requested ? ' investigation-desk-selected' : ''}`}
    >
      <section className="investigation-queue" aria-label="Activity queue">
        <div className="investigation-queue-heading">
          <span>In this view</span>
          <span>{events.length} records</span>
        </div>
        {events.map((event) => (
          <button
            key={event.event_key}
            className={`investigation-queue-item${selected?.event_key === event.event_key ? ' is-selected' : ''}`}
            aria-pressed={selected?.event_key === event.event_key}
            onClick={() => select(event)}
          >
            <span className="queue-item-meta">
              <span>{activityLabel(event)}</span>
              <time>{formatShortDate(event.event_date) ?? 'Date unverified'}</time>
            </span>
            <strong>{event.title}</strong>
            <span className="queue-item-place">
              <span>
                {event.municipality || 'County records'}
                {triage?.[event.event_key] === 'reviewed' ? ' · Read' : ''}
              </span>
              <span aria-hidden="true">↗</span>
            </span>
          </button>
        ))}
        {footer && <div className="investigation-queue-footer">{footer}</div>}
      </section>
      <div className="investigation-reading-pane">
        <button className="investigation-back" onClick={() => select(null)}>
          ← Back to activity
        </button>
        {selected ? (
          <InvestigationDetail
            key={selected.event_key}
            event={selected}
            headingRef={detailHeading}
            triageStatus={triage?.[selected.event_key]}
            onTriage={onTriage ? (status) => onTriage(selected.event_key, status) : undefined}
          />
        ) : (
          <div className="investigation-missing" role="status">
            <h2>This record is outside the loaded results.</h2>
            <p>
              It may be outside the current filters, farther down the results, or no longer
              available.
            </p>
            <button onClick={() => select(null)}>Return to these results</button>
          </div>
        )}
      </div>
    </div>
  )
}

export function FollowActivity({ event }: { event: IntelligenceEvent }) {
  const [, refresh] = useState(0)
  useEffect(() => {
    const update = () => refresh((value) => value + 1)
    window.addEventListener('countyiq-watchlist-changed', update)
    return () => window.removeEventListener('countyiq-watchlist-changed', update)
  }, [])
  const property = event.related_pidns.length === 1 ? event.related_pidns[0] : null
  const watched = event.project
    ? isProjectWatched(event.project.key)
    : property
      ? isWatched(property)
      : getMunicipalityWatchlist().some((item) => item.name === event.municipality)
  const subject = event.project ? 'project' : property ? 'property' : 'municipality'
  if (!event.project && !property && !event.municipality) {
    return null
  }
  return (
    <button
      className={`investigation-follow${watched ? ' is-following' : ''}`}
      aria-pressed={watched}
      onClick={() => {
        if (event.project) {
          toggleProjectWatch(event.project)
        } else if (property) {
          toggleWatch(property)
        } else if (event.municipality) {
          toggleMunicipalityWatch({ name: event.municipality })
        }
      }}
    >
      {watched ? '✓ Following' : '+ Follow'} {subject}
    </button>
  )
}

export function InvestigationDetail({
  event,
  headingRef,
  triageStatus,
  onTriage,
  showContext = true,
  showFollow = true,
}: {
  event: IntelligenceEvent
  headingRef?: React.Ref<HTMLHeadingElement>
  triageStatus?: TriageStatus
  onTriage?: (status: TriageStatus | null) => void
  showContext?: boolean
  showFollow?: boolean
}) {
  const [tab, setTab] = useState<'overview' | 'sources'>('overview')
  const [sourceIndex, setSourceIndex] = useState(0)
  const openSource = useSourceViewer()
  const detail = investigationDetails(event)
  const singlePidn = event.related_pidns.length === 1 ? event.related_pidns[0] : null
  const property = useFetchJson<PropertyReport>(
    showContext && singlePidn ? `/api/parcels/${encodeURIComponent(singlePidn)}` : null,
  )
  const source = event.sources[sourceIndex]
  return (
    <article
      className={`investigation-detail${showContext ? '' : ' investigation-detail-standalone'}`}
    >
      <div className="investigation-detail-topline">
        <span className="investigation-status">{activityLabel(event)}</span>
        <span>{event.municipality}</span>
        {showFollow && <FollowActivity event={event} />}
      </div>
      <h2 ref={headingRef} tabIndex={-1}>
        {event.title}
      </h2>
      <p className="investigation-byline">
        Record dated {formatShortDate(event.event_date) ?? 'date unverified'}
        <span>·</span>
        {event.sources.length} supporting {event.sources.length === 1 ? 'source' : 'sources'}
      </p>
      <div className="investigation-tabs" aria-label="Investigation view">
        <button aria-pressed={tab === 'overview'} onClick={() => setTab('overview')}>
          Overview
        </button>
        <button aria-pressed={tab === 'sources'} onClick={() => setTab('sources')}>
          Source documents <span>{event.sources.length}</span>
        </button>
      </div>
      <div className="investigation-overview" hidden={tab !== 'overview'}>
        <section className="investigation-account">
          <h3>What the record says</h3>
          <p className="investigation-summary">
            <CitedText text={event.what_happened} evidence={event.sources} />
          </p>
          {detail.dates.length > 0 && (
            <div className="investigation-dates">
              {detail.dates.map((date, index) => (
                <p key={index}>
                  <span className="investigation-date-icon" aria-hidden="true">
                    ◷
                  </span>
                  <CitedText
                    text={`${describeRecordDate(date)} [Evidence:source:${date.source_id}]`}
                    evidence={event.sources}
                  />
                </p>
              ))}
            </div>
          )}
          {detail.nextStep && (
            <div className="investigation-next">
              <span>YOUR NEXT CHECK</span>
              <p>
                <CitedText text={detail.nextStep} evidence={event.sources} />
              </p>
            </div>
          )}
          {detail.conditions.length > 0 && (
            <section className="investigation-nuance">
              <h3>Conditions in this record</h3>
              <p>Completion has not been established.</p>
              <ul>
                {detail.conditions.map((condition) => (
                  <li key={condition.index}>
                    {condition.text}{' '}
                    {supportingSource(event, `condition:${condition.index}`) && (
                      <button
                        className="source-catalog-button"
                        onClick={() =>
                          openSource([supportingSource(event, `condition:${condition.index}`)!])
                        }
                      >
                        Source ↗
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          )}
          {detail.milestones.length > 0 && (
            <section className="investigation-nuance">
              <h3>Stated milestones</h3>
              <p>A stated date does not establish that the action occurred.</p>
              <ul>
                {detail.milestones.map((milestone) => (
                  <li key={milestone.index}>
                    {milestone.kind && milestone.kind !== 'other' && (
                      <strong>{formatLabel(milestone.kind)}: </strong>
                    )}
                    {milestone.text}{' '}
                    {supportingSource(event, `milestone:${milestone.index}`) && (
                      <button
                        className="source-catalog-button"
                        onClick={() =>
                          openSource([supportingSource(event, `milestone:${milestone.index}`)!])
                        }
                      >
                        Source ↗
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          )}
          <div className="investigation-verification">
            <span className="verification-mark" aria-hidden="true">
              ↗
            </span>
            <div>
              <strong>Read the source for yourself.</strong>
              <p>Check the wording, scope and dates in the original record.</p>
            </div>
            <button onClick={() => setTab('sources')}>View sources →</button>
          </div>
          {onTriage && (
            <div className="investigation-review-actions">
              <button onClick={() => onTriage(triageStatus === 'reviewed' ? null : 'reviewed')}>
                {triageStatus === 'reviewed' ? '✓ Read · mark unread' : 'Mark as read'}
              </button>
              <button onClick={() => onTriage(triageStatus === 'dismissed' ? null : 'dismissed')}>
                {triageStatus === 'dismissed' ? 'Restore to activity' : 'Hide from activity'}
              </button>
            </div>
          )}
        </section>
        {showContext && (
          <aside className="investigation-context" aria-label="Connected context">
            {property.data ? (
              <>
                <ParcelContextMap report={property.data} />
                <div className="investigation-property">
                  <span>LINKED PROPERTY</span>
                  <Link to={`/property/${singlePidn}`}>
                    {property.data.parcel.propadr || singlePidn} ↗
                  </Link>
                  <p>{property.data.parcel.owner_full || 'Owner unavailable'}</p>
                  <dl>
                    <div>
                      <dt>Land area</dt>
                      <dd>
                        {property.data.parcel.acres == null
                          ? 'Unknown'
                          : `${Number(property.data.parcel.acres).toLocaleString()} acres`}
                      </dd>
                    </div>
                    <div>
                      <dt>Current zoning</dt>
                      <dd>{property.data.zoning?.name ?? 'Not available'}</dd>
                    </div>
                    <div>
                      <dt>Assessed value</dt>
                      <dd>{formatCurrency(property.data.parcel.aprtotal)}</dd>
                    </div>
                  </dl>
                </div>
              </>
            ) : singlePidn ? (
              <p>
                {property.loading
                  ? 'Loading the linked property…'
                  : 'Property context is unavailable.'}{' '}
                <Link to={`/property/${singlePidn}`}>Open property →</Link>
              </p>
            ) : (
              <div className="investigation-place">
                <span>LOCATION CONTEXT</span>
                <h3>{event.municipality || 'County records'}</h3>
                <p>
                  {event.related_pidns.length
                    ? `${event.related_pidns.length} linked parcels; these links do not establish a complete project boundary.`
                    : 'A specific property has not been linked to this record.'}
                </p>
                {event.related_pidns.map((pidn) => (
                  <Link key={pidn} to={`/property/${pidn}`}>
                    Parcel {pidn} ↗
                  </Link>
                ))}
              </div>
            )}
            {(event.entity_links?.length ?? 0) > 0 && (
              <div className="investigation-connections">
                <h3>Organizations named</h3>
                {event.entity_links.map((entity) => (
                  <Link key={entity.owner_id} to={`/entity/${entity.owner_id}`}>
                    {entity.name} ↗
                  </Link>
                ))}
              </div>
            )}
            {event.project && (
              <Link
                className="investigation-context-link"
                to={`/project/${encodeURIComponent(event.project.key)}`}
              >
                View project history →
              </Link>
            )}
            {event.municipality && (
              <Link
                className="investigation-context-link"
                to={`/municipalities/${encodeURIComponent(event.municipality)}`}
              >
                Explore {event.municipality} →
              </Link>
            )}
          </aside>
        )}
      </div>
      <section
        className="investigation-sources"
        aria-label="Supporting documents"
        hidden={tab !== 'sources'}
      >
        <p className="investigation-source-intro">
          The public records behind this account. Select a source to read its wording and open the
          original.
        </p>
        {event.sources.length > 1 && (
          <label>
            Choose a supporting source
            <select
              value={sourceIndex}
              onChange={(change) => setSourceIndex(Number(change.target.value))}
            >
              {event.sources.map((item, index) => (
                <option key={`${item.evidence_id}-${index}`} value={index}>
                  {index + 1}. {sourceTitle(item)}
                </option>
              ))}
            </select>
          </label>
        )}
        {source ? (
          <>
            <h3>{sourceTitle(source)}</h3>
            <SourceContent item={source} />
          </>
        ) : (
          <p>No supporting source is currently available.</p>
        )}
      </section>
      <div className="investigation-print-sources">
        <EvidencePanel items={event.sources} />
      </div>
    </article>
  )
}
