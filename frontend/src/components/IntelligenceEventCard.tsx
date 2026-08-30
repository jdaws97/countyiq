import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import Badge from './Badge'
import { formatLabel, formatShortDate } from '../lib/format'
import {
  isProjectWatched,
  isWatched,
  toggleProjectWatch,
  toggleWatch,
} from '../lib/watchlist'
import type { IntelligenceEvent } from '../types/api'


function eventColor(event: IntelligenceEvent): string {
  if (event.event_type === 'denial' || event.event_type === 'delinquency_change') return 'var(--accent-red)'
  if (event.event_type === 'approval') return 'var(--accent-green)'
  if (event.event_type === 'continuance' || event.event_type === 'condition') return 'var(--accent-gold)'
  if (event.category === 'development') return 'var(--accent-cyan)'
  return 'var(--accent-blue)'
}


function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        fontFamily: 'var(--font-mono)',
        fontSize: 9,
        letterSpacing: 1.5,
        textTransform: 'uppercase',
        color: 'var(--text-muted)',
        marginBottom: 5,
      }}
    >
      {children}
    </div>
  )
}


function InsightBlock({ label, children, accent }: { label: string; children: string; accent?: string }) {
  return (
    <div
      style={{
        padding: '12px 14px',
        borderLeft: `2px solid ${accent ?? 'var(--border)'}`,
        background: 'color-mix(in srgb, var(--bg-panel) 72%, transparent)',
        borderRadius: 3,
      }}
    >
      <SectionLabel>{label}</SectionLabel>
      <div style={{ fontFamily: 'var(--font-sans)', fontSize: 14, lineHeight: 1.6, color: 'var(--text-secondary)' }}>
        {children}
      </div>
    </div>
  )
}


export default function IntelligenceEventCard({ event }: { event: IntelligenceEvent }) {
  const [, setWatchRevision] = useState(0)

  useEffect(() => {
    const refresh = () => setWatchRevision((value) => value + 1)
    window.addEventListener('countyiq-watchlist-changed', refresh)
    return () => window.removeEventListener('countyiq-watchlist-changed', refresh)
  }, [])

  const eventDate = formatShortDate(event.event_date ?? event.detected_at)
  const confidence = event.confidence == null ? null : Math.round(event.confidence * 100)
  const projectWatched = event.project ? isProjectWatched(event.project.key) : false
  const pidns = event.related_pidns.slice(0, 8)
  const secondaryTags = event.event_tags.filter((tag) => tag !== event.event_type).slice(0, 5)
  const entityLinks = event.entity_links ?? []
  const linkedEntityNames = new Set(entityLinks.map((entity) => entity.matched_name.toLowerCase()))
  const unresolvedEntities = event.related_entities.filter((name) => !linkedEntityNames.has(name.toLowerCase()))

  return (
    <article
      style={{
        background: 'var(--bg-card)',
        border: `1px solid color-mix(in srgb, ${eventColor(event)} 34%, var(--border))`,
        borderRadius: 8,
        padding: 20,
      }}
    >
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 12, alignItems: 'center' }}>
        <Badge color={eventColor(event)}>{formatLabel(event.event_type)}</Badge>
        <Badge color={event.category === 'development' ? 'var(--accent-cyan)' : 'var(--accent-blue)'}>
          {formatLabel(event.category)} intelligence
        </Badge>
        {secondaryTags.map((tag) => (
          <Badge key={tag} color="var(--text-muted)">{formatLabel(tag)}</Badge>
        ))}
        {event.interpretation.kind === 'llm' && (
          <Badge color="var(--accent-purple)">LLM extracted · source grounded</Badge>
        )}
        {(event.importance_reasons ?? []).slice(0, 2).map((reason) => (
          <Badge key={reason} color="var(--accent-gold)">{reason}</Badge>
        ))}
        {confidence !== null && <Badge color="var(--text-muted)">{confidence}% confidence</Badge>}
        {eventDate && <Badge color="var(--text-muted)">{eventDate}</Badge>}
      </div>

      <h2
        style={{
          fontFamily: 'var(--font-sans)',
          fontSize: 21,
          lineHeight: 1.25,
          fontWeight: 650,
          color: 'var(--text-primary)',
          marginBottom: 14,
        }}
      >
        {event.title}
      </h2>

      <div style={{ display: 'grid', gap: 10, marginBottom: 16 }}>
        <InsightBlock label="What happened" accent={eventColor(event)}>{event.what_happened}</InsightBlock>
        <InsightBlock label="Why it matters" accent="var(--accent-purple)">{event.why_it_matters}</InsightBlock>
        <InsightBlock label="What happens next" accent="var(--accent-gold)">{event.what_happens_next}</InsightBlock>
      </div>

      {event.project && (
        <div style={{ marginBottom: 14 }}>
          <SectionLabel>Related project</SectionLabel>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
            <Link
              to={`/project/${encodeURIComponent(event.project.key)}`}
              aria-label={`Open project case file for ${event.project.name}`}
              style={{ textDecoration: 'none' }}
            >
              <Badge color="var(--accent-cyan)">{event.project.name} →</Badge>
            </Link>
            <button
              onClick={() => {
                toggleProjectWatch(event.project!)
                setWatchRevision((value) => value + 1)
              }}
              style={watchButtonStyle(projectWatched)}
            >
              {projectWatched ? '★ Watching project' : '☆ Watch project'}
            </button>
          </div>
        </div>
      )}

      {(entityLinks.length > 0 || unresolvedEntities.length > 0) && (
        <div style={{ marginBottom: 14 }}>
          <SectionLabel>Related entities</SectionLabel>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {entityLinks.map((entity) => (
              <Link
                key={entity.owner_id}
                to={`/entity/${entity.owner_id}`}
                aria-label={`Open entity case file for ${entity.name}`}
                style={{ textDecoration: 'none' }}
              >
                <Badge color="var(--accent-green)">{entity.name} →</Badge>
              </Link>
            ))}
            {unresolvedEntities.map((entity) => (
              <Badge key={entity} color="var(--text-muted)">{entity} · unresolved</Badge>
            ))}
          </div>
        </div>
      )}

      {pidns.length > 0 && (
        <div style={{ marginBottom: 14 }}>
          <SectionLabel>Related parcels</SectionLabel>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
            {pidns.map((pidn) => {
              const watched = isWatched(pidn)
              return (
                <div key={pidn} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  <Link
                    to={`/property/${pidn}`}
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: 11,
                      color: 'var(--accent-blue)',
                      textDecoration: 'none',
                      padding: '4px 8px',
                      border: '1px solid var(--border)',
                      borderRadius: 4,
                    }}
                  >
                    {pidn}
                  </Link>
                  <button
                    aria-label={`${watched ? 'Unwatch' : 'Watch'} parcel ${pidn}`}
                    title={`${watched ? 'Unwatch' : 'Watch'} parcel ${pidn}`}
                    onClick={() => {
                      toggleWatch(pidn)
                      setWatchRevision((value) => value + 1)
                    }}
                    style={compactWatchButtonStyle(watched)}
                  >
                    {watched ? '★' : '☆'}
                  </button>
                </div>
              )
            })}
            {event.related_pidns.length > pidns.length && (
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}>
                +{event.related_pidns.length - pidns.length} more
              </span>
            )}
          </div>
        </div>
      )}

      <div>
        <SectionLabel>Source evidence</SectionLabel>
        <div style={{ display: 'grid', gap: 8 }}>
          {event.sources.map((source, index) => {
            const href = source.document_url ?? source.url
            return (
              <details key={`${event.event_key}-source-${index}`} style={{ borderTop: '1px solid var(--border)', paddingTop: 8 }}>
                <summary
                  style={{
                    cursor: 'pointer',
                    fontFamily: 'var(--font-mono)',
                    fontSize: 11,
                    color: 'var(--accent-cyan)',
                  }}
                >
                  {source.label}
                  {href ? ' · open evidence' : ''}
                </summary>
                <div style={{ padding: '10px 0 2px 16px' }}>
                  {source.excerpt && (
                    <blockquote
                      style={{
                        margin: '0 0 8px',
                        paddingLeft: 12,
                        borderLeft: '2px solid var(--border)',
                        fontFamily: 'var(--font-serif)',
                        fontSize: 13,
                        lineHeight: 1.6,
                        color: 'var(--text-secondary)',
                      }}
                    >
                      {source.excerpt}
                    </blockquote>
                  )}
                  {href && (
                    <a
                      href={href}
                      target="_blank"
                      rel="noreferrer"
                      style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--accent-blue)' }}
                    >
                      View original source ↗
                    </a>
                  )}
                </div>
              </details>
            )
          })}
        </div>
      </div>
    </article>
  )
}


function watchButtonStyle(watched: boolean): React.CSSProperties {
  return {
    fontFamily: 'var(--font-mono)',
    fontSize: 11,
    color: watched ? 'var(--accent-gold)' : 'var(--accent-blue)',
    background: 'transparent',
    border: `1px solid ${watched ? 'var(--accent-gold)' : 'var(--border)'}`,
    borderRadius: 4,
    padding: '5px 10px',
    cursor: 'pointer',
  }
}


function compactWatchButtonStyle(watched: boolean): React.CSSProperties {
  return {
    width: 28,
    height: 28,
    fontSize: 14,
    color: watched ? 'var(--accent-gold)' : 'var(--text-muted)',
    background: 'transparent',
    border: `1px solid ${watched ? 'var(--accent-gold)' : 'var(--border)'}`,
    borderRadius: 4,
    cursor: 'pointer',
  }
}
