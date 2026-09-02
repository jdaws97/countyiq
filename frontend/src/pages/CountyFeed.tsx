import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import IntelligenceEventCard from '../components/IntelligenceEventCard'
import PageShell from '../components/PageShell'
import { Button, EmptyState, PageHeader, StatusMessage } from '../components/ui'
import {
  getEventTriage,
  getLastFeedVisit,
  saveSearch,
  setEventTriage,
  setLastFeedVisit,
  type TriageStatus,
} from '../lib/investigationState'
import { useCountyMeta } from '../lib/useCountyMeta'
import { watchBoostParams } from '../lib/watchlist'
import type { IntelligenceCategory, IntelligenceEvent, IntelligenceFeedResponse, MunicipalitySummary } from '../types/api'

const PAGE_SIZE = 30
const CATEGORIES = ['all', 'development', 'parcel'] as const
const EVENT_TYPES = ['all', 'application', 'approval', 'continuance', 'denial', 'condition', 'transfer', 'delinquency_change', 'value_change', 'structure_change'] as const
const TIME_WINDOWS = [30, 90, 365, 3650] as const
const SORT_MODES = ['priority', 'latest'] as const
const INBOX_MODES = ['inbox', 'all', 'reviewed', 'dismissed'] as const

type CategoryFilter = 'all' | IntelligenceCategory
type EventTypeFilter = (typeof EVENT_TYPES)[number]
type TimeWindow = (typeof TIME_WINDOWS)[number]
type SortMode = (typeof SORT_MODES)[number]
type InboxMode = (typeof INBOX_MODES)[number]

export default function CountyFeed() {
  const county = useCountyMeta()
  const [searchParams, setSearchParams] = useSearchParams()
  const [events, setEvents] = useState<IntelligenceEvent[]>([])
  const [category, setCategory] = useState<CategoryFilter>(() => parseChoice(searchParams.get('category'), CATEGORIES, 'all'))
  const [eventType, setEventType] = useState<EventTypeFilter>(() => parseChoice(searchParams.get('event'), EVENT_TYPES, 'all'))
  const [sinceDays, setSinceDays] = useState<TimeWindow>(() => parseNumberChoice(searchParams.get('days'), TIME_WINDOWS, 90))
  const [sortMode, setSortMode] = useState<SortMode>(() => parseChoice(searchParams.get('sort'), SORT_MODES, 'priority'))
  const [municipality, setMunicipality] = useState(() => searchParams.get('municipality') ?? '')
  const [municipalities, setMunicipalities] = useState<string[]>([])
  const [inboxMode, setInboxMode] = useState<InboxMode>('inbox')
  const [triage, setTriage] = useState(() => getEventTriage())
  const [previousVisit] = useState(() => getLastFeedVisit())
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [hasMore, setHasMore] = useState(false)
  const [saved, setSaved] = useState(false)
  const requestGeneration = useRef(0)
  const loadMoreController = useRef<AbortController | null>(null)
  const requestKey = `${category}|${eventType}|${sinceDays}|${sortMode}|${municipality}`
  const [resolvedKey, setResolvedKey] = useState<string | null>(null)
  const loading = resolvedKey !== requestKey

  useEffect(() => () => setLastFeedVisit(), [])

  useEffect(() => {
    const next = new URLSearchParams()
    if (category !== 'all') next.set('category', category)
    if (eventType !== 'all') next.set('event', eventType)
    if (sinceDays !== 90) next.set('days', String(sinceDays))
    if (sortMode !== 'priority') next.set('sort', sortMode)
    if (municipality) next.set('municipality', municipality)
    setSearchParams(next, { replace: true })
  }, [category, eventType, sinceDays, sortMode, municipality, setSearchParams])

  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/municipalities', { signal: controller.signal })
      .then((response) => (response.ok ? response.json() as Promise<MunicipalitySummary[]> : []))
      .then((rows) => setMunicipalities(rows.map((row) => row.name).sort()))
      .catch(() => { /* filter stays free-text-less */ })
    return () => controller.abort()
  }, [])

  useEffect(() => {
    const key = requestKey
    const generation = ++requestGeneration.current
    const controller = new AbortController()
    loadMoreController.current?.abort()
    fetchPage(0, category, eventType, sinceDays, sortMode, municipality, controller.signal)
      .then((result) => {
        if (controller.signal.aborted || generation !== requestGeneration.current) return
        setEvents(result.events)
        setHasMore(result.has_more)
        setError(null)
        setResolvedKey(key)
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted || generation !== requestGeneration.current) return
        setError(reason instanceof Error ? reason.message : 'Failed to load intelligence feed')
        setResolvedKey(key)
      })
    return () => controller.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestKey])

  const visibleEvents = useMemo(() => events.filter((event) => {
    const status = triage[event.event_key]
    if (inboxMode === 'inbox') return status !== 'reviewed' && status !== 'dismissed'
    if (inboxMode === 'all') return status !== 'dismissed'
    return status === inboxMode
  }), [events, inboxMode, triage])

  const newCount = events.filter((event) => previousVisit && new Date(event.detected_at) > new Date(previousVisit)).length
  const reviewedCount = events.filter((event) => triage[event.event_key] === 'reviewed').length

  const updateTriage = (eventKey: string, status: TriageStatus | null) => {
    setEventTriage(eventKey, status)
    setTriage(getEventTriage())
  }

  const loadMore = () => {
    if (loadingMore) return
    const generation = requestGeneration.current
    const offset = events.length
    const controller = new AbortController()
    loadMoreController.current?.abort()
    loadMoreController.current = controller
    setLoadingMore(true)
    fetchPage(offset, category, eventType, sinceDays, sortMode, municipality, controller.signal)
      .then((result) => {
        if (controller.signal.aborted || generation !== requestGeneration.current) return
        setEvents((current) => Array.from(
          new Map([...current, ...result.events].map((event) => [event.event_key, event])).values(),
        ))
        setHasMore(result.has_more)
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted && generation === requestGeneration.current) {
          setError(reason instanceof Error ? reason.message : 'Failed to load more intelligence')
        }
      })
      .finally(() => {
        if (generation === requestGeneration.current) setLoadingMore(false)
      })
  }

  const saveCurrentSearch = () => {
    const path = `/feed?${searchParams.toString()}`
    const label = `${category === 'all' ? 'All intelligence' : category} · ${sinceDays === 3650 ? 'all history' : `${sinceDays} days`} · ${sortMode}`
    saveSearch(label, 'feed', path)
    setSaved(true)
    window.setTimeout(() => setSaved(false), 1800)
  }

  return (
    <PageShell maxWidth={1040}>
      <PageHeader
        eyebrow="Evidence-backed intelligence"
        title={`${county.county_name} Intelligence Feed`}
        description="Triage meaningful parcel and development changes, then open the source receipts before relying on an interpretation."
        actions={<Button tone="quiet" onClick={saveCurrentSearch}>{saved ? 'Search saved' : 'Save this search'}</Button>}
      />

      <div className="feed-summary" aria-label="Feed summary">
        <SummaryStat label="In current result" value={events.length} />
        <SummaryStat label="New since last visit" value={newCount} accent />
        <SummaryStat label="Reviewed" value={reviewedCount} />
      </div>

      <div className="feed-toolbar" data-print-hidden>
        <label>Queue<select value={inboxMode} onChange={(event) => setInboxMode(event.target.value as InboxMode)}>{INBOX_MODES.map((mode) => <option key={mode} value={mode}>{mode === 'inbox' ? 'Needs review' : titleCase(mode)}</option>)}</select></label>
        <label>Intelligence<select value={category} onChange={(event) => setCategory(event.target.value as CategoryFilter)}>{CATEGORIES.map((value) => <option key={value} value={value}>{titleCase(value)}</option>)}</select></label>
        <label>Municipality<select value={municipality} onChange={(event) => setMunicipality(event.target.value)}><option value="">All municipalities</option>{municipalities.map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
        <label>Window<select value={sinceDays} onChange={(event) => setSinceDays(Number(event.target.value) as TimeWindow)}>{TIME_WINDOWS.map((days) => <option key={days} value={days}>{days === 3650 ? 'All history' : `${days} days`}</option>)}</select></label>
        <label>Order<select value={sortMode} onChange={(event) => setSortMode(event.target.value as SortMode)}>{SORT_MODES.map((value) => <option key={value} value={value}>{titleCase(value)}</option>)}</select></label>
        <details className="advanced-filters">
          <summary>Advanced filters</summary>
          <label>Event type<select value={eventType} onChange={(event) => setEventType(event.target.value as EventTypeFilter)}>{EVENT_TYPES.map((value) => <option key={value} value={value}>{titleCase(value)}</option>)}</select></label>
        </details>
      </div>

      {loading && <StatusMessage>Loading intelligence…</StatusMessage>}
      {!loading && error && <StatusMessage tone="error">Failed to load feed: {error}</StatusMessage>}
      {!loading && !error && visibleEvents.length === 0 && (
        <EmptyState title={events.length === 0 ? 'No matching intelligence' : 'Your review queue is clear'} actions={<Button tone="secondary" onClick={() => setInboxMode('all')}>Show all active events</Button>}>
          {events.length === 0 ? 'Try a longer time window or another intelligence type.' : 'Reviewed and dismissed items remain available from the Queue filter.'}
        </EmptyState>
      )}

      {!loading && visibleEvents.length > 0 && (
        <div className="feed-list">
          {visibleEvents.map((event) => (
            <IntelligenceEventCard
              key={event.event_key}
              event={event}
              showTriage
              triageStatus={triage[event.event_key]}
              isNew={Boolean(previousVisit && new Date(event.detected_at) > new Date(previousVisit))}
              onTriage={(status) => updateTriage(event.event_key, status)}
            />
          ))}
          {hasMore && <Button className="feed-load-more" onClick={loadMore} disabled={loadingMore}>{loadingMore ? 'Loading…' : 'Load more'}</Button>}
        </div>
      )}
    </PageShell>
  )
}

function SummaryStat({ label, value, accent = false }: { label: string; value: number; accent?: boolean }) {
  return <div className={`feed-summary-stat${accent ? ' feed-summary-stat-accent' : ''}`}><span>{label}</span><strong>{value}</strong></div>
}

function titleCase(value: string): string {
  return value.replace(/_/g, ' ').replace(/^./, (letter) => letter.toUpperCase())
}

function parseChoice<T extends string>(value: string | null, choices: readonly T[], fallback: T): T {
  return value && choices.includes(value as T) ? value as T : fallback
}

function parseNumberChoice<T extends number>(value: string | null, choices: readonly T[], fallback: T): T {
  const parsed = Number(value)
  return choices.includes(parsed as T) ? parsed as T : fallback
}

async function fetchPage(offset: number, category: CategoryFilter, eventType: EventTypeFilter, sinceDays: TimeWindow, sortMode: SortMode, municipality: string, signal?: AbortSignal): Promise<IntelligenceFeedResponse> {
  const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset), since_days: String(sinceDays), sort: sortMode })
  if (category !== 'all') params.set('category', category)
  if (eventType !== 'all') params.set('event_type', eventType)
  if (municipality) params.set('municipality', `${municipality}%`)
  for (const [key, value] of Object.entries(watchBoostParams())) params.set(key, value)
  const response = await fetch(`/api/feed?${params.toString()}`, { signal })
  if (!response.ok) throw new Error(`${response.status}`)
  return response.json() as Promise<IntelligenceFeedResponse>
}
