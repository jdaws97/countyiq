import { useEffect, useState } from 'react'
import NarrativeCard from '../components/NarrativeCard'
import PageShell from '../components/PageShell'
import Section from '../components/Section'
import { formatShortDate } from '../lib/format'
import type { CountyFeedNarrative, CountyFeedResponse } from '../types/api'

const NARRATIVE_TYPES = ['all', 'corridor', 'distress', 'municipal', 'portfolio'] as const
type NarrativeTypeFilter = (typeof NARRATIVE_TYPES)[number]

// A curated subset of Pass 4's trajectory vocabulary. Scan-specific trajectories
// (e.g. "concentrating" for distress, "expanding" for portfolio) are excluded
// so the filter bar stays compact; users can still see them on individual cards.
const TRAJECTORIES = ['all', 'accelerating', 'steady', 'stalling', 'declining'] as const
type TrajectoryFilter = (typeof TRAJECTORIES)[number]

const PAGE_SIZE = 50

export default function CountyFeed() {
  const [narratives, setNarratives] = useState<CountyFeedNarrative[]>([])
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [typeFilter, setTypeFilter] = useState<NarrativeTypeFilter>('all')
  const [trajectoryFilter, setTrajectoryFilter] = useState<TrajectoryFilter>('all')
  const [hasMore, setHasMore] = useState(false)

  useEffect(() => {
    setLoading(true)
    setHasMore(false)
    fetchPage(0, typeFilter, trajectoryFilter)
      .then(({ narratives, hasMore }) => {
        setNarratives(narratives)
        setHasMore(hasMore)
        setError(null)
      })
      .catch((e) => setError(e.message ?? 'Failed to load feed'))
      .finally(() => setLoading(false))
  }, [typeFilter, trajectoryFilter])

  const loadMore = () => {
    setLoadingMore(true)
    fetchPage(narratives.length, typeFilter, trajectoryFilter)
      .then(({ narratives: next, hasMore }) => {
        setNarratives((prev) => [...prev, ...next])
        setHasMore(hasMore)
      })
      .catch((e) => setError(e.message ?? 'Failed to load more'))
      .finally(() => setLoadingMore(false))
  }

  // API returns narratives sorted newest first, so index 0 is the most recent.
  const mostRecent = narratives[0]?.generated_at ?? null

  return (
    <PageShell maxWidth={960}>
      <div style={{ marginBottom: 24 }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, letterSpacing: 3, textTransform: 'uppercase', color: 'var(--accent-gold)', marginBottom: 8 }}>
          Pass 4 Intelligence
        </div>
        <h1 style={{ fontFamily: 'var(--font-sans)', fontSize: 28, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>
          County Feed
        </h1>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--text-secondary)' }}>
          Corridor, distress, municipal, and portfolio narratives across York County.
          {mostRecent && <span> Last narrative generated {formatShortDate(mostRecent)}.</span>}
        </div>
      </div>

      <FilterRow label="Type" options={NARRATIVE_TYPES} value={typeFilter} onChange={setTypeFilter} />
      <FilterRow label="Trajectory" options={TRAJECTORIES} value={trajectoryFilter} onChange={setTrajectoryFilter} />

      {loading && (
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--text-muted)', textAlign: 'center', padding: '60px 0' }}>
          Loading feed...
        </div>
      )}

      {error && !loading && (
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--accent-red)' }}>
          Failed to load feed: {error}
        </div>
      )}

      {!loading && !error && narratives.length === 0 && (
        <Section title="No narratives yet">
          <div style={{ fontFamily: 'var(--font-sans)', fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            No Pass 4 narratives match these filters yet. They are produced weekly after the
            signal-validation pass completes.
          </div>
        </Section>
      )}

      {!loading && narratives.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {narratives.map((n) => (
            <NarrativeCard
              key={n.narrative_id}
              narrative={n}
              showAffectedPidns
              titleAs="h2"
            />
          ))}

          {hasMore && (
            <button
              onClick={loadMore}
              disabled={loadingMore}
              style={{
                alignSelf: 'center',
                fontFamily: 'var(--font-mono)',
                fontSize: 12,
                letterSpacing: 1.5,
                textTransform: 'uppercase',
                padding: '10px 18px',
                borderRadius: 4,
                border: '1px solid var(--border)',
                background: 'transparent',
                color: 'var(--text-secondary)',
                cursor: loadingMore ? 'wait' : 'pointer',
                marginTop: 8,
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
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 16, alignItems: 'center' }}>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: 1.5, textTransform: 'uppercase', color: 'var(--text-muted)', marginRight: 4 }}>
        {label}
      </span>
      {options.map((t) => (
        <button
          key={t}
          onClick={() => onChange(t)}
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            letterSpacing: 1.5,
            textTransform: 'uppercase',
            padding: '6px 12px',
            borderRadius: 4,
            border: '1px solid var(--border)',
            background: value === t ? 'var(--accent-gold)' : 'transparent',
            color: value === t ? 'var(--bg-deep)' : 'var(--text-secondary)',
            cursor: 'pointer',
          }}
        >
          {t}
        </button>
      ))}
    </div>
  )
}

async function fetchPage(
  offset: number,
  typeFilter: NarrativeTypeFilter,
  trajectoryFilter: TrajectoryFilter,
): Promise<{ narratives: CountyFeedNarrative[]; hasMore: boolean }> {
  const params = new URLSearchParams()
  if (typeFilter !== 'all') params.set('narrative_type', typeFilter)
  if (trajectoryFilter !== 'all') params.set('trajectory', trajectoryFilter)
  params.set('limit', String(PAGE_SIZE))
  params.set('offset', String(offset))

  const r = await fetch(`/api/feed?${params.toString()}`)
  if (!r.ok) throw new Error(`${r.status}`)
  const data = (await r.json()) as CountyFeedResponse
  const narratives = data.narratives ?? []
  return { narratives, hasMore: narratives.length === PAGE_SIZE }
}
