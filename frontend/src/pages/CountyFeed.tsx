import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import InvestigationDesk from '../components/InvestigationDesk'
import '../components/ActivityWorkspace.css'
import PageShell from '../components/PageShell'
import { CoverageSummary } from '../components/MunicipalEvidence'
import { useFetchJson } from '../lib/useFetchJson'
import '../components/ActivityPreview.css'
import { Button, ButtonLink, EmptyState, PageHeader, StatusMessage } from '../components/ui'
import {
  getEventTriage,
  getLastFeedVisit,
  saveSearch,
  setEventTriage,
  setLastFeedVisit,
  type TriageStatus,
} from '../lib/investigationState'
import { useCountyMeta } from '../lib/useCountyMeta'
import { useWatchFeedParams } from '../lib/useWatchFeedParams'
import type {
  IntelligenceCategory,
  IntelligenceEvent,
  IntelligenceFeedResponse,
  MunicipalitySummary,
  MunicipalEvidenceResponse,
} from '../types/api'

const PAGE_SIZE = 30
const CATEGORIES = ['all', 'development', 'parcel'] as const
const EVENT_TYPES = [
  'all',
  'application',
  'hearing',
  'revision',
  'continuance',
  'approval',
  'denial',
  'condition',
  'upcoming_decision',
  'policy_action',
  'update',
  'recommendation',
  'withdrawn',
  'removed',
  'scoped_decision',
  'transfer',
  'delinquency_change',
  'value_change',
  'structure_change',
  'municipal_record',
] as const
const MATTER_CATEGORIES = [
  'all',
  'development',
  'minor_property',
  'landuse_policy',
  'public_works',
  'context_only',
] as const
const TIME_WINDOWS = [30, 90, 365, 3650] as const
const SORT_MODES = ['priority', 'latest'] as const
const INBOX_MODES = ['inbox', 'all', 'reviewed', 'dismissed'] as const

type CategoryFilter = 'all' | IntelligenceCategory
type EventTypeFilter = (typeof EVENT_TYPES)[number]
type MatterCategory = (typeof MATTER_CATEGORIES)[number]
type TimeWindow = (typeof TIME_WINDOWS)[number]
type SortMode = (typeof SORT_MODES)[number]
type InboxMode = (typeof INBOX_MODES)[number]

export default function CountyFeed() {
  const county = useCountyMeta()
  const [searchParams, setSearchParams] = useSearchParams()
  const [events, setEvents] = useState<IntelligenceEvent[]>([])
  const watchParams = useWatchFeedParams()
  const following = searchParams.get('scope') === 'following'
  const category: CategoryFilter = parseChoice(searchParams.get('category'), CATEGORIES, 'all')
  const eventType: EventTypeFilter = parseChoice(searchParams.get('event'), EVENT_TYPES, 'all')
  const matterCategory: MatterCategory = parseChoice(
    searchParams.get('matter'),
    MATTER_CATEGORIES,
    'all',
  )
  const sinceDays: TimeWindow = parseNumberChoice(searchParams.get('days'), TIME_WINDOWS, 90)
  const sortMode: SortMode = parseChoice(searchParams.get('sort'), SORT_MODES, 'priority')
  const municipality = searchParams.get('municipality') ?? ''
  const textQuery = searchParams.get('q') ?? ''
  const coverage = useFetchJson<MunicipalEvidenceResponse>(
    municipality
      ? `/api/municipalities/${encodeURIComponent(municipality)}/evidence?limit=1`
      : null,
  )
  const [municipalities, setMunicipalities] = useState<string[]>([])
  const [inboxMode, setInboxMode] = useState<InboxMode>('all')
  const [triage, setTriage] = useState(() => getEventTriage())
  const [previousVisit] = useState(() => getLastFeedVisit())
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [hasMore, setHasMore] = useState(false)
  const [saved, setSaved] = useState(false)
  const requestGeneration = useRef(0)
  const loadMoreController = useRef<AbortController | null>(null)
  const requestKey = `${category}|${eventType}|${sinceDays}|${sortMode}|${municipality}|${matterCategory}|${textQuery}|${following}|${watchParams}`
  const [resolvedKey, setResolvedKey] = useState<string | null>(null)
  const loading = resolvedKey !== requestKey

  useEffect(() => () => setLastFeedVisit(), [])

  const updateFilter = (key: string, value: string, defaultValue = 'all') => {
    setSearchParams(
      (current) => {
        const next = new URLSearchParams(current)
        next.delete('record')
        if (value === defaultValue) {
          next.delete(key)
        } else {
          next.set(key, value)
        }
        return next
      },
      { replace: true },
    )
  }

  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/municipalities', { signal: controller.signal })
      .then((response) => (response.ok ? (response.json() as Promise<MunicipalitySummary[]>) : []))
      .then((rows) => setMunicipalities(rows.map((row) => row.name).sort()))
      .catch(() => {
        /* filter stays free-text-less */
      })
    return () => controller.abort()
  }, [])

  useEffect(() => {
    const key = requestKey
    const generation = ++requestGeneration.current
    const controller = new AbortController()
    loadMoreController.current?.abort()
    fetchPage(
      0,
      category,
      eventType,
      sinceDays,
      sortMode,
      municipality,
      matterCategory,
      textQuery,
      following,
      watchParams,
      controller.signal,
    )
      .then((result) => {
        if (controller.signal.aborted || generation !== requestGeneration.current) {
          return
        }
        setEvents(result.events)
        setHasMore(result.has_more)
        setError(null)
        setResolvedKey(key)
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted || generation !== requestGeneration.current) {
          return
        }
        setEvents([])
        setHasMore(false)
        setError(reason instanceof Error ? reason.message : 'Failed to load intelligence feed')
        setResolvedKey(key)
      })
    return () => {
      controller.abort()
      loadMoreController.current?.abort()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestKey])

  const visibleEvents = useMemo(
    () =>
      events.filter((event) => {
        const status = triage[event.event_key]
        if (inboxMode === 'inbox') {
          return status !== 'reviewed' && status !== 'dismissed'
        }
        if (inboxMode === 'all') {
          return status !== 'dismissed'
        }
        return status === inboxMode
      }),
    [events, inboxMode, triage],
  )

  const newCount = events.filter(
    (event) => previousVisit && new Date(event.detected_at) > new Date(previousVisit),
  ).length
  const reviewedCount = events.filter((event) => triage[event.event_key] === 'reviewed').length

  const updateTriage = (eventKey: string, status: TriageStatus | null) => {
    setEventTriage(eventKey, status)
    setTriage(getEventTriage())
  }

  const loadMore = () => {
    if (loadingMore) {
      return
    }
    const generation = requestGeneration.current
    const offset = events.length
    const controller = new AbortController()
    loadMoreController.current?.abort()
    loadMoreController.current = controller
    setLoadingMore(true)
    fetchPage(
      offset,
      category,
      eventType,
      sinceDays,
      sortMode,
      municipality,
      matterCategory,
      textQuery,
      following,
      watchParams,
      controller.signal,
    )
      .then((result) => {
        if (controller.signal.aborted || generation !== requestGeneration.current) {
          return
        }
        setEvents((current) =>
          Array.from(
            new Map(
              [...current, ...result.events].map((event) => [event.event_key, event]),
            ).values(),
          ),
        )
        setHasMore(result.has_more)
        setError(null)
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted && generation === requestGeneration.current) {
          setError(reason instanceof Error ? reason.message : 'Failed to load more intelligence')
        }
      })
      .finally(() => {
        if (loadMoreController.current === controller) {
          setLoadingMore(false)
        }
      })
  }

  const saveCurrentSearch = () => {
    const path = `/feed?${searchParams.toString()}`
    const label = `${category === 'all' ? 'All intelligence' : category} · ${sinceDays === 3650 ? 'all history' : `${sinceDays} days`} · ${sortMode}`
    setSaved(Boolean(saveSearch(label, 'feed', path)))
    window.setTimeout(() => setSaved(false), 1800)
  }

  return (
    <PageShell wide className="activity-workspace-page">
      <PageHeader
        eyebrow={county.county_name}
        title="Activity workspace"
        description="Choose a record. Get the context. Decide what to follow."
        actions={
          <Button tone="quiet" onClick={saveCurrentSearch}>
            {saved ? 'Search saved' : 'Save this search'}
          </Button>
        }
      />

      <div className="section-actions feed-scope" aria-label="Activity scope">
        <Button
          tone={following ? 'primary' : 'quiet'}
          aria-pressed={following}
          onClick={() => updateFilter('scope', 'following', 'county')}
        >
          Following
        </Button>
        <Button
          tone={following ? 'quiet' : 'primary'}
          aria-pressed={!following}
          onClick={() => updateFilter('scope', 'county', 'county')}
        >
          Explore county
        </Button>
      </div>
      {following && (
        <p className="activity-scope-note">
          Records matching any property, project, organization or municipality you follow.
        </p>
      )}
      <form
        className="feed-record-search"
        onSubmit={(event) => {
          event.preventDefault()
          updateFilter('q', String(new FormData(event.currentTarget).get('q') ?? '').trim(), '')
        }}
      >
        <label className="sr-only" htmlFor="feed-record-query">
          Search activity and public plan numbers
        </label>
        <input
          key={textQuery}
          id="feed-record-query"
          name="q"
          defaultValue={textQuery}
          maxLength={160}
          placeholder="Search a matter, address or public plan number"
        />
        <Button type="submit" tone="secondary">
          Search activity
        </Button>
      </form>
      <details className="activity-filter-drawer">
        <summary>
          Filter activity{' '}
          <span>
            {municipality || 'All municipalities'} ·{' '}
            {eventType === 'all' ? 'All activity' : titleCase(eventType)} ·{' '}
            {sinceDays === 3650 ? 'All history' : `${sinceDays} days`}
          </span>
        </summary>
        <div className="feed-toolbar" data-print-hidden>
          <label>
            Municipality
            <select
              value={municipality}
              onChange={(event) => updateFilter('municipality', event.target.value, '')}
            >
              <option value="">All municipalities</option>
              {municipality && !municipalities.includes(municipality) && (
                <option value={municipality}>{municipality}</option>
              )}
              {municipalities.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
          <label>
            Activity
            <select
              value={eventType}
              onChange={(event) => updateFilter('event', event.target.value)}
            >
              {EVENT_TYPES.map((value) => (
                <option key={value} value={value}>
                  {value === 'all'
                    ? 'All activity'
                    : value === 'municipal_record'
                      ? 'Other municipal records'
                      : titleCase(value)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Record period
            <select
              value={sinceDays}
              onChange={(event) => updateFilter('days', event.target.value, '90')}
            >
              {TIME_WINDOWS.map((days) => (
                <option key={days} value={days}>
                  {days === 3650 ? 'All history' : `Last ${days} days`}
                </option>
              ))}
            </select>
          </label>
          <label>
            Sort by
            <select
              value={sortMode}
              onChange={(event) => updateFilter('sort', event.target.value, 'priority')}
            >
              <option value="priority">Relevance & followed places</option>
              <option value="latest">Newest record date</option>
            </select>
          </label>
          <details className="advanced-filters">
            <summary>More filters</summary>
            <div className="advanced-filter-fields">
              <label>
                Reading status
                <select
                  value={inboxMode}
                  onChange={(event) => setInboxMode(event.target.value as InboxMode)}
                >
                  {INBOX_MODES.map((mode) => (
                    <option key={mode} value={mode}>
                      {mode === 'inbox'
                        ? 'Unread'
                        : mode === 'all'
                          ? 'All visible'
                          : mode === 'reviewed'
                            ? 'Read'
                            : 'Hidden'}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Record family
                <select
                  value={category}
                  onChange={(event) => updateFilter('category', event.target.value)}
                >
                  {CATEGORIES.map((value) => (
                    <option key={value} value={value}>
                      {value === 'all'
                        ? 'All records'
                        : value === 'development'
                          ? 'Municipal activity'
                          : 'Property record changes'}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Topic
                <select
                  value={matterCategory}
                  onChange={(event) => updateFilter('matter', event.target.value)}
                >
                  {MATTER_CATEGORIES.map((value) => (
                    <option key={value} value={value}>
                      {matterLabel(value)}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </details>
          {(searchParams.size > 0 || inboxMode !== 'all') && (
            <Button
              tone="quiet"
              className="feed-reset"
              onClick={() => {
                setSearchParams({})
                setInboxMode('all')
              }}
            >
              Reset filters
            </Button>
          )}
        </div>
      </details>
      <div className="activity-coverage-line">
        {coverage.data?.coverage ? (
          <CoverageSummary coverage={coverage.data.coverage} />
        ) : (
          <p className="activity-scope-note">
            Showing published records in this scope. Coverage varies by municipality; missing
            activity does not mean nothing happened.{' '}
            <ButtonLink
              to={
                municipality
                  ? `/municipalities/${encodeURIComponent(municipality)}`
                  : '/municipalities'
              }
              tone="quiet"
            >
              Explore coverage
            </ButtonLink>
          </p>
        )}
      </div>
      {!loading && events.length > 0 && (
        <p className="feed-result-summary">
          {visibleEvents.length} visible in loaded results{hasMore ? ' · more available' : ''}
          {newCount > 0 ? ` · ${newCount} added since your last visit` : ''}
          {reviewedCount > 0 ? ` · ${reviewedCount} marked read` : ''}
        </p>
      )}

      {loading && <StatusMessage>Loading intelligence…</StatusMessage>}
      {!loading && error && (
        <StatusMessage tone="error">Failed to load feed: {error}</StatusMessage>
      )}
      {!loading && !error && visibleEvents.length === 0 && (
        <EmptyState
          title={
            events.length === 0
              ? 'No published activity matches these filters'
              : hasMore
                ? 'No matching events in the loaded results'
                : 'No unread activity in these results'
          }
          actions={
            events.length === 0 ? (
              <>
                <ButtonLink to="/radar">Explore properties on Radar</ButtonLink>
                {searchParams.size > 0 ? (
                  <Button tone="quiet" onClick={() => setSearchParams({})}>
                    Reset filters
                  </Button>
                ) : (
                  <ButtonLink to="/search" tone="quiet">
                    Find a property
                  </ButtonLink>
                )}
              </>
            ) : (
              <Button tone="secondary" onClick={() => setInboxMode('all')}>
                Show all visible activity
              </Button>
            )
          }
        >
          {events.length === 0
            ? 'Activity appears when source records change and are ready to review. Coverage varies by municipality. You can still investigate properties and save the places you want to follow.'
            : hasMore
              ? 'Load more activity to continue. Read and hidden items remain available under More filters.'
              : 'Read and hidden items remain available under More filters.'}
        </EmptyState>
      )}

      {!loading && visibleEvents.length > 0 && (
        <InvestigationDesk
          events={visibleEvents}
          triage={triage}
          onTriage={updateTriage}
          footer={
            hasMore ? (
              <Button onClick={loadMore} disabled={loadingMore}>
                {loadingMore ? 'Loading…' : 'Load more records'}
              </Button>
            ) : undefined
          }
        />
      )}
      {!loading && !visibleEvents.length && hasMore && (
        <Button onClick={loadMore} disabled={loadingMore}>
          Load more records
        </Button>
      )}
    </PageShell>
  )
}

function matterLabel(value: MatterCategory): string {
  const labels: Record<MatterCategory, string> = {
    all: 'Development discovery',
    development: 'Development applications',
    minor_property: 'Minor property work',
    landuse_policy: 'Zoning & land-use policy',
    public_works: 'Infrastructure & public works',
    context_only: 'Other municipal business',
  }
  return labels[value]
}

function titleCase(value: string): string {
  return value.replace(/_/g, ' ').replace(/^./, (letter) => letter.toUpperCase())
}

function parseChoice<T extends string>(
  value: string | null,
  choices: readonly T[],
  fallback: T,
): T {
  return value && choices.includes(value as T) ? (value as T) : fallback
}

function parseNumberChoice<T extends number>(
  value: string | null,
  choices: readonly T[],
  fallback: T,
): T {
  const parsed = Number(value)
  return choices.includes(parsed as T) ? (parsed as T) : fallback
}

async function fetchPage(
  offset: number,
  category: CategoryFilter,
  eventType: EventTypeFilter,
  sinceDays: TimeWindow,
  sortMode: SortMode,
  municipality: string,
  matterCategory: MatterCategory,
  textQuery: string,
  following: boolean,
  watchParams: string,
  signal?: AbortSignal,
): Promise<IntelligenceFeedResponse> {
  const params = new URLSearchParams({
    limit: String(PAGE_SIZE),
    offset: String(offset),
    since_days: String(sinceDays),
    sort: sortMode,
  })
  if (textQuery) {
    params.set('q', textQuery)
  }
  if (category !== 'all') {
    params.set('category', category)
  }
  if (eventType !== 'all') {
    params.set('event_type', eventType)
  }
  if (municipality) {
    params.set('municipality', municipality)
  }
  if (matterCategory !== 'all') {
    params.set('matter_category', matterCategory)
  }
  if (following) {
    params.set('watched_only', 'true')
  }
  for (const [key, value] of new URLSearchParams(watchParams)) {
    params.set(key, value)
  }
  const response = await fetch(`/api/feed?${params.toString()}`, { signal })
  if (!response.ok) {
    throw new Error(`${response.status}`)
  }
  return response.json() as Promise<IntelligenceFeedResponse>
}
