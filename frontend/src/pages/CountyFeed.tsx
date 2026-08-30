import { useEffect, useState } from 'react'

import IntelligenceEventCard from '../components/IntelligenceEventCard'
import PageShell from '../components/PageShell'
import Section from '../components/Section'
import { useCountyMeta } from '../lib/useCountyMeta'
import type {
  IntelligenceCategory,
  IntelligenceEvent,
  IntelligenceFeedResponse,
} from '../types/api'


const PAGE_SIZE = 30
const CATEGORIES = ['all', 'development', 'parcel'] as const
const EVENT_TYPES = [
  'all',
  'application',
  'approval',
  'continuance',
  'denial',
  'condition',
  'transfer',
  'delinquency_change',
  'value_change',
  'structure_change',
] as const
const TIME_WINDOWS = [30, 90, 365, 3650] as const
const SORT_MODES = ['priority', 'latest'] as const

type CategoryFilter = 'all' | IntelligenceCategory
type EventTypeFilter = (typeof EVENT_TYPES)[number]
type TimeWindow = (typeof TIME_WINDOWS)[number]
type SortMode = (typeof SORT_MODES)[number]


export default function CountyFeed() {
  const county = useCountyMeta()
  const [events, setEvents] = useState<IntelligenceEvent[]>([])
  const [category, setCategory] = useState<CategoryFilter>('all')
  const [eventType, setEventType] = useState<EventTypeFilter>('all')
  const [sinceDays, setSinceDays] = useState<TimeWindow>(90)
  const [sortMode, setSortMode] = useState<SortMode>('priority')
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [hasMore, setHasMore] = useState(false)
  const requestKey = `${category}|${eventType}|${sinceDays}|${sortMode}`
  const [resolvedKey, setResolvedKey] = useState<string | null>(null)
  const loading = resolvedKey !== requestKey

  useEffect(() => {
    const key = `${category}|${eventType}|${sinceDays}|${sortMode}`
    let cancelled = false
    fetchPage(0, category, eventType, sinceDays, sortMode)
      .then((result) => {
        if (cancelled) return
        setEvents(result.events)
        setHasMore(result.has_more)
        setError(null)
        setResolvedKey(key)
      })
      .catch((reason: unknown) => {
        if (cancelled) return
        setError(reason instanceof Error ? reason.message : 'Failed to load intelligence feed')
        setResolvedKey(key)
      })
    return () => {
      cancelled = true
    }
  }, [category, eventType, sinceDays, sortMode])

  const loadMore = () => {
    setLoadingMore(true)
    fetchPage(events.length, category, eventType, sinceDays, sortMode)
      .then((result) => {
        setEvents((current) => [...current, ...result.events])
        setHasMore(result.has_more)
      })
      .catch((reason: unknown) => {
        setError(reason instanceof Error ? reason.message : 'Failed to load more intelligence')
      })
      .finally(() => setLoadingMore(false))
  }

  const developmentCount = events.filter((event) => event.category === 'development').length
  const llmCount = events.filter((event) => event.interpretation.kind === 'llm').length

  return (
    <PageShell maxWidth={1040}>
      <header style={{ marginBottom: 26 }}>
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            letterSpacing: 3,
            textTransform: 'uppercase',
            color: 'var(--accent-gold)',
            marginBottom: 8,
          }}
        >
          Evidence-backed intelligence
        </div>
        <h1
          style={{
            fontFamily: 'var(--font-sans)',
            fontSize: 30,
            fontWeight: 700,
            color: 'var(--text-primary)',
            marginBottom: 6,
          }}
        >
          {county.county_name} Intelligence Feed
        </h1>
        <p style={{ fontFamily: 'var(--font-sans)', fontSize: 14, lineHeight: 1.6, color: 'var(--text-secondary)', maxWidth: 780 }}>
          Parcel changes detected from county records and development activity extracted from municipal documents.
          Deterministic priority, interpretation, next steps, and original evidence remain visibly separated.
        </p>
      </header>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(3, minmax(0, 1fr))',
          gap: 10,
          marginBottom: 22,
        }}
      >
        <SummaryStat label="Events shown" value={events.length} />
        <SummaryStat label="Development events" value={developmentCount} />
        <SummaryStat label="Source-grounded LLM events" value={llmCount} />
      </div>

      <FilterRow label="Order" options={SORT_MODES} value={sortMode} onChange={setSortMode} />
      <FilterRow label="Intelligence" options={CATEGORIES} value={category} onChange={setCategory} />
      <FilterRow label="Event" options={EVENT_TYPES} value={eventType} onChange={setEventType} />
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 24, alignItems: 'center' }}>
        <FilterLabel>Window</FilterLabel>
        {TIME_WINDOWS.map((days) => (
          <FilterButton key={days} selected={sinceDays === days} onClick={() => setSinceDays(days)}>
            {days === 3650 ? 'All history' : `${days} days`}
          </FilterButton>
        ))}
      </div>

      {loading && (
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--text-muted)', textAlign: 'center', padding: '70px 0' }}>
          Loading intelligence…
        </div>
      )}

      {!loading && error && (
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--accent-red)', padding: '30px 0' }}>
          Failed to load feed: {error}
        </div>
      )}

      {!loading && !error && events.length === 0 && (
        <Section title="No matching intelligence">
          <div style={{ fontFamily: 'var(--font-sans)', fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            No events match the current filters. Try a longer time window or another intelligence type.
          </div>
        </Section>
      )}

      {!loading && events.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {events.map((event) => <IntelligenceEventCard key={event.event_key} event={event} />)}
          {hasMore && (
            <button
              onClick={loadMore}
              disabled={loadingMore}
              style={{
                alignSelf: 'center',
                fontFamily: 'var(--font-mono)',
                fontSize: 12,
                letterSpacing: 1.4,
                textTransform: 'uppercase',
                padding: '10px 18px',
                borderRadius: 4,
                border: '1px solid var(--border)',
                background: 'transparent',
                color: 'var(--text-secondary)',
                cursor: loadingMore ? 'wait' : 'pointer',
                marginTop: 6,
              }}
            >
              {loadingMore ? 'Loading…' : 'Load more'}
            </button>
          )}
        </div>
      )}
    </PageShell>
  )
}


function SummaryStat({ label, value }: { label: string; value: number }) {
  return (
    <div style={{ border: '1px solid var(--border)', background: 'var(--bg-card)', borderRadius: 6, padding: '12px 14px' }}>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: 1.4, textTransform: 'uppercase', color: 'var(--text-muted)' }}>{label}</div>
      <div style={{ fontFamily: 'var(--font-sans)', fontSize: 22, color: 'var(--text-primary)', marginTop: 3 }}>{value}</div>
    </div>
  )
}


function FilterRow<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string
  options: readonly T[]
  value: T
  onChange: (next: T) => void
}) {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 12, alignItems: 'center' }}>
      <FilterLabel>{label}</FilterLabel>
      {options.map((option) => (
        <FilterButton key={option} selected={value === option} onClick={() => onChange(option)}>
          {option.replace(/_/g, ' ')}
        </FilterButton>
      ))}
    </div>
  )
}


function FilterLabel({ children }: { children: React.ReactNode }) {
  return (
    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: 1.5, textTransform: 'uppercase', color: 'var(--text-muted)', marginRight: 4 }}>
      {children}
    </span>
  )
}


function FilterButton({ selected, onClick, children }: { selected: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      style={{
        fontFamily: 'var(--font-mono)',
        fontSize: 11,
        letterSpacing: 1,
        textTransform: 'capitalize',
        padding: '6px 11px',
        borderRadius: 4,
        border: '1px solid var(--border)',
        background: selected ? 'var(--accent-gold)' : 'transparent',
        color: selected ? 'var(--bg-deep)' : 'var(--text-secondary)',
        cursor: 'pointer',
      }}
    >
      {children}
    </button>
  )
}


async function fetchPage(
  offset: number,
  category: CategoryFilter,
  eventType: EventTypeFilter,
  sinceDays: TimeWindow,
  sortMode: SortMode,
): Promise<IntelligenceFeedResponse> {
  const params = new URLSearchParams({
    limit: String(PAGE_SIZE),
    offset: String(offset),
    since_days: String(sinceDays),
    sort: sortMode,
  })
  if (category !== 'all') params.set('category', category)
  if (eventType !== 'all') params.set('event_type', eventType)

  const response = await fetch(`/api/feed?${params.toString()}`)
  if (!response.ok) throw new Error(`${response.status}`)
  return response.json() as Promise<IntelligenceFeedResponse>
}
