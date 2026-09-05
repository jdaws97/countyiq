import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import BackButton from '../components/BackButton'
import PageShell from '../components/PageShell'
import { Button, ButtonLink } from '../components/ui'
import { formatCurrencyCompact, formatShortDate } from '../lib/format'
import { getComparison, radarSearchName, saveSearch, toggleComparison } from '../lib/investigationState'
import type {
  RadarMoversDirection,
  RadarMoversResponse,
  RadarMunicipalitiesResponse,
  RadarParcel,
  RadarParcelListResponse,
  RadarViewMode,
  ReasonSignal,
} from '../types/api'

type RadarTab = RadarViewMode | 'movers'

const TABS: { key: RadarTab; label: string }[] = [
  { key: 'opportunity', label: 'Opportunity' },
  { key: 'momentum', label: 'Momentum' },
  { key: 'movers', label: 'Movers' },
  { key: 'readiness', label: 'Site Screening' },
]

const PARCEL_CLASSES = [
  { value: '', label: 'All classes' },
  { value: 'R', label: 'Residential' },
  { value: 'C', label: 'Commercial' },
  { value: 'I', label: 'Industrial' },
  { value: 'F,A', label: 'Farm / agricultural' },
  { value: 'E', label: 'Exempt' },
]

const ACRE_OPTIONS = [
  { value: '', label: 'Any size' },
  { value: '1', label: '1+ acres' },
  { value: '5', label: '5+ acres' },
  { value: '10', label: '10+ acres' },
  { value: '25', label: '25+ acres' },
]

const PAGE_SIZE = 200

function scoreColor(s: number): string {
  if (s >= 60) return 'var(--accent-green)'
  if (s >= 40) return 'var(--accent-gold)'
  if (s >= 20) return 'var(--accent-ink)'
  return 'var(--text-secondary)'
}

function scoreOptionsFor(view: RadarTab) {
  if (view === 'opportunity') {
    return [
      { value: '30', label: '30+ Recommended' },
      { value: '40', label: '40+' },
      { value: '50', label: '50+' },
      { value: '60', label: '60+' },
      { value: '0', label: '0+ Any' },
    ]
  }
  if (view === 'momentum') {
    return [
      { value: '30', label: '30+ Recommended' },
      { value: '40', label: '40+' },
      { value: '50', label: '50+' },
      { value: '60', label: '60+' },
      { value: '0', label: '0+ Any' },
    ]
  }
  if (view === 'movers') {
    return [
      { value: '5', label: 'Moved 5+ points' },
      { value: '10', label: 'Moved 10+ points' },
      { value: '20', label: 'Moved 20+ points' },
    ]
  }
  return [
    { value: '40', label: '40+ Higher screen' },
    { value: '50', label: '50+' },
    { value: '60', label: '60+' },
    { value: '70', label: '70+' },
    { value: '0', label: '0+ Review all' },
  ]
}

const DEFAULT_SCORE: Record<RadarTab, string> = { opportunity: '30', momentum: '30', readiness: '40', movers: '5' }

function isTab(value: string | null): value is RadarTab {
  return value === 'opportunity' || value === 'momentum' || value === 'readiness' || value === 'movers'
}

export default function DevelopmentRadar() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const requestedView = searchParams.get('view')
  const view: RadarTab = isTab(requestedView) ? requestedView : 'opportunity'
  const [parcels, setParcels] = useState<RadarParcel[]>([])
  const [resolvedKey, setResolvedKey] = useState<string | null>(null)
  const [loadingMore, setLoadingMore] = useState(false)
  const [hasMore, setHasMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const muniFilter = searchParams.get('municipality') ?? ''
  const minAcres = searchParams.get('min_acres') ?? ''
  const parcelClass = searchParams.get('class') ?? ''
  const direction = searchParams.get('direction')
  const moversDirection: RadarMoversDirection = direction === 'down' || direction === 'new' ? direction : 'up'
  const moversBasis = searchParams.get('basis') === 'momentum' ? 'momentum' : 'opportunity'
  const [page, setPage] = useState(0)
  const updateFilters = (values: Record<string, string | null>) => {
    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      for (const [key, value] of Object.entries(values)) {
        if (value) next.set(key, value)
        else next.delete(key)
      }
      return next
    }, { replace: true })
  }
  const setView = (nextView: RadarTab) => updateFilters({
    view: nextView, min_score: null,
    ...(nextView === 'movers' ? { min_acres: null, class: null } : { direction: null, basis: null }),
  })
  const setMuniFilter = (value: string) => updateFilters({ municipality: value })
  const setMinAcres = (value: string) => updateFilters({ min_acres: value })
  const setParcelClass = (value: string) => updateFilters({ class: value })
  const setMoversDirection = (value: RadarMoversDirection) => updateFilters({ direction: value })
  const setMoversBasis = (value: 'opportunity' | 'momentum') => updateFilters({ basis: value })
  const [comparison, setComparison] = useState(() => getComparison())
  const [saved, setSaved] = useState(false)
  const [previousComputedAt, setPreviousComputedAt] = useState<string | null>(null)
  const requestGeneration = useRef(0)
  const loadMoreController = useRef<AbortController | null>(null)

  const [municipalities, setMunicipalities] = useState<string[]>([])
  const [screeningCoverage, setScreeningCoverage] = useState<RadarParcelListResponse['coverage']>()
  const minScore = searchParams.get('min_score') || DEFAULT_SCORE[view]
  const requestKey = `${view}|${minScore}|${muniFilter}|${minAcres}|${parcelClass}|${moversDirection}|${moversBasis}`
  const loading = resolvedKey !== requestKey
  const setMinScore = (value: string) => updateFilters({ min_score: value })
  const scoreOptions = scoreOptionsFor(view)

  const buildParams = (pageNum: number) => {
    const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(pageNum * PAGE_SIZE) })
    if (muniFilter) params.set('municipality', muniFilter)
    if (view === 'movers') {
      params.set('view', moversBasis)
      params.set('direction', moversDirection)
      params.set('min_delta', minScore)
    } else {
      params.set('min_score', minScore)
      if (minAcres) params.set('min_acres', minAcres)
      if (parcelClass) params.set('class', parcelClass)
    }
    return params
  }

  const endpointFor = (tab: RadarTab) => (
    tab === 'opportunity' ? '/api/radar/opportunity'
      : tab === 'momentum' ? '/api/radar/development'
        : tab === 'movers' ? '/api/radar/movers'
          : '/api/radar/site-readiness'
  )

  const fetchPage = async (pageNum: number, append: boolean, generation: number, signal?: AbortSignal) => {
    if (append) setLoadingMore(true)
    const key = requestKey
    try {
      const response = await fetch(`${endpointFor(view)}?${buildParams(pageNum)}`, { signal })
      if (!response.ok) throw new Error(`Radar request failed (${response.status})`)
      const data = await response.json() as RadarParcelListResponse | RadarMoversResponse
      if (signal?.aborted || generation !== requestGeneration.current) return

      const items = data.parcels || []
      if (!append && view === 'readiness') setScreeningCoverage((data as RadarParcelListResponse).coverage)
      if (!append && view === 'movers') setPreviousComputedAt((data as RadarMoversResponse).previous_computed_at)
      if (append) {
        setParcels(prev => Array.from(new Map([...prev, ...items].map(item => [item.pidn, item])).values()))
      } else {
        setParcels(items)
        setResolvedKey(key)
      }
      setPage(pageNum)
      setHasMore(items.length === PAGE_SIZE)
      setError(null)
    } catch (caught) {
      if (signal?.aborted || generation !== requestGeneration.current) return
      const message = caught instanceof Error ? caught.message : 'Unknown radar error'
      console.error('Failed to load radar parcels', caught)
      setError(message)
      if (!append) {
        setParcels([])
        setHasMore(false)
        setScreeningCoverage(undefined)
        setPreviousComputedAt(null)
        setResolvedKey(key)
      }
    } finally {
      if (generation === requestGeneration.current) setLoadingMore(false)
    }
  }

  useEffect(() => {
    const controller = new AbortController()
    const generation = ++requestGeneration.current
    void fetchPage(0, false, generation, controller.signal)
    return () => {
      controller.abort()
      loadMoreController.current?.abort()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestKey])

  useEffect(() => {
    const controller = new AbortController()
    const listView: RadarViewMode = view === 'movers' ? moversBasis : view
    const params = new URLSearchParams({ view: listView, min_score: view === 'movers' ? '0' : minScore })
    fetch(`/api/radar/municipalities?${params}`, { signal: controller.signal })
      .then(r => {
        if (!r.ok) throw new Error(`Municipalities request failed (${r.status})`)
        return r.json()
      })
      .then((d: RadarMunicipalitiesResponse) => {
        if (controller.signal.aborted) return
        const munis = (d.municipalities || []) as string[]
        setMunicipalities(munis)
      })
      .catch((err) => {
        if (controller.signal.aborted) return
        console.error('Failed to load radar municipalities', err)
      })
    return () => controller.abort()
  }, [view, minScore, moversBasis])

  useEffect(() => {
    const refresh = () => setComparison(getComparison())
    window.addEventListener('countyiq-investigation-changed', refresh)
    return () => window.removeEventListener('countyiq-investigation-changed', refresh)
  }, [])

  const currentPath = () => {
    const params = new URLSearchParams({ view, min_score: minScore })
    if (muniFilter) params.set('municipality', muniFilter)
    if (minAcres) params.set('min_acres', minAcres)
    if (parcelClass) params.set('class', parcelClass)
    if (view === 'movers') {
      params.set('direction', moversDirection)
      params.set('basis', moversBasis)
    }
    return `/radar?${params}`
  }

  const saveCurrentSearch = () => {
    setSaved(Boolean(saveSearch(radarSearchName(view, muniFilter, minScore), 'radar', currentPath())))
    window.setTimeout(() => setSaved(false), 1800)
  }

  const mapLayer = view === 'momentum' ? 'momentum' : 'opportunity'
  const countLabel = view === 'opportunity' ? 'opportunities'
    : view === 'momentum' ? 'active sites'
      : view === 'movers' ? (moversDirection === 'new' ? 'new on radar' : moversDirection === 'up' ? 'risers' : 'fallers')
        : 'screened candidates'

  return (
    <PageShell maxWidth={1180}>
      <BackButton onClick={() => navigate(-1)} />

      <div style={{ marginBottom: 28 }}>
        <div className="record-eyebrow">Property development signals</div>
        <h1 className="page-title">Development Radar</h1>
        <p style={{ maxWidth: '72ch', fontSize: 16, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
          {view === 'opportunity'
            ? 'Build a shortlist from site characteristics, nearby plans and recorded ownership changes. Higher scores mean more matching signals; open a property to check the evidence.'
            : view === 'momentum'
              ? 'Where development activity is already happening: plans on or beside the parcel, municipal matters, park designations, recent sales, and owners assembling sites.'
              : view === 'movers'
                ? 'What changed since the previous radar rebuild. Rising scores mean new evidence arrived; new parcels had no signals at all last time.'
                : 'Parcel screening from public policy, infrastructure, physical constraints, and diligence records. Verify the linked evidence before relying on a score.'}
        </p>
      </div>

      {view === 'readiness' && screeningCoverage && (
        <div style={{ marginTop: -14, marginBottom: 20, fontSize: 13.5, color: screeningCoverage.missing_layers.length ? 'var(--accent-gold)' : 'var(--accent-green)' }}>
          Evidence coverage: {screeningCoverage.loaded_count}/{screeningCoverage.total_count} screening layers loaded
          {screeningCoverage.missing_layers.length > 0 ? ` · missing ${screeningCoverage.missing_layers.join(', ').replace(/_/g, ' ')}` : ''}
        </div>
      )}
      {view === 'movers' && (
        <div style={{ marginTop: -14, marginBottom: 20, fontSize: 13.5, color: 'var(--text-secondary)' }}>
          {previousComputedAt
            ? `Compared with the radar snapshot from ${formatShortDate(previousComputedAt)}.`
            : 'No previous snapshot yet. Movers appear after the second weekly radar rebuild.'}
        </div>
      )}

      <div className="segmented" role="group" aria-label="Radar view" style={{ marginBottom: 18 }}>
        {TABS.map((tab) => (
          <button key={tab.key} type="button" aria-pressed={view === tab.key} onClick={() => setView(tab.key)}>{tab.label}</button>
        ))}
      </div>

      <div className="filter-row">
        <label className="sr-only" htmlFor="radar-municipality">Municipality</label>
        <select id="radar-municipality" value={muniFilter} onChange={e => setMuniFilter(e.target.value)}>
          <option value="">All Municipalities</option>
          {muniFilter && !municipalities.includes(muniFilter) && <option value={muniFilter}>{muniFilter}</option>}
          {municipalities.map(m => <option key={m} value={m}>{m}</option>)}
        </select>
        <label className="sr-only" htmlFor="radar-min-score">{view === 'movers' ? 'Minimum change' : 'Minimum score'}</label>
        <select id="radar-min-score" value={minScore} onChange={e => setMinScore(e.target.value)}>
          {!scoreOptions.some(option => option.value === minScore) && <option value={minScore}>{minScore}+</option>}
          {scoreOptions.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
        {view === 'movers' ? (
          <>
            <label className="sr-only" htmlFor="radar-direction">Direction</label>
            <select id="radar-direction" value={moversDirection} onChange={e => setMoversDirection(e.target.value as RadarMoversDirection)}>
              <option value="up">Rising</option>
              <option value="new">New on radar</option>
              <option value="down">Falling</option>
            </select>
            <label className="sr-only" htmlFor="radar-basis">Score basis</label>
            <select id="radar-basis" value={moversBasis} onChange={e => setMoversBasis(e.target.value as 'opportunity' | 'momentum')}>
              <option value="opportunity">Opportunity score</option>
              <option value="momentum">Momentum score</option>
            </select>
          </>
        ) : (
          <>
            <label className="sr-only" htmlFor="radar-min-acres">Minimum acres</label>
            <select id="radar-min-acres" value={minAcres} onChange={e => setMinAcres(e.target.value)}>
              {!ACRE_OPTIONS.some(option => option.value === minAcres) && <option value={minAcres}>{minAcres}+ acres</option>}
              {ACRE_OPTIONS.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
            <label className="sr-only" htmlFor="radar-class">Property class</label>
            <select id="radar-class" value={parcelClass} onChange={e => setParcelClass(e.target.value)}>
              {!PARCEL_CLASSES.some(option => option.value === parcelClass) && <option value={parcelClass}>{parcelClass}</option>}
              {PARCEL_CLASSES.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </>
        )}
        <div className="filter-count">
          {loading ? 'Loading…' : `${parcels.length}${hasMore ? '+' : ''} ${countLabel}`}
        </div>
        <Button tone="quiet" onClick={saveCurrentSearch}>{saved ? 'Search saved' : 'Save search'}</Button>
        {view !== 'readiness' && <ButtonLink to={`/map?layer=radar&radar=${mapLayer}`} tone="quiet">Map view</ButtonLink>}
        {comparison.length > 0 && <ButtonLink to="/compare" tone="secondary">Compare {comparison.length}/4</ButtonLink>}
      </div>

      {error && <div className="error-box" role="alert">Failed to load data: {error}</div>}

      {!loading && parcels.length > 0 && (
        <div className="radar-results data-table">
          <div className="radar-results-header data-table-head" style={{ minWidth: 960, gridTemplateColumns: '64px 72px 1fr 130px 70px 100px minmax(240px, 1.4fr) 92px' }}>
            <div>Score</div><div>Change</div><div>Address</div><div>Municipality</div><div className="cell-right">Acres</div><div className="cell-right" style={{ paddingRight: 12 }}>Assessed value</div><div style={{ paddingLeft: 12 }}>Why It Ranked</div><div className="cell-right">Compare</div>
          </div>

          {parcels.map((p) => (
            <div className="radar-results-row data-table-row" key={p.pidn} style={{ minWidth: 960, gridTemplateColumns: '64px 72px 1fr 130px 70px 100px minmax(240px, 1.4fr) 92px', padding: '12px 16px' }}>
              <div>
                <span className="score-pill" style={{ '--score-color': scoreColor(p.score) } as React.CSSProperties}>{p.score}</span>
              </div>
              <div><DeltaBadge parcel={p} basis={view === 'movers' ? moversBasis : view === 'momentum' ? 'momentum' : 'opportunity'} /></div>
              <div style={{ minWidth: 0 }}>
                <Link to={`/property/${p.pidn}`} className="cell-strong">{p.propadr || p.pidn}</Link>
                <div className="cell-muted" style={{ marginTop: 2 }}>{p.owner_full || 'Owner not displayed'}</div>
              </div>
              <div className="cell-muted">{p.municipality || '--'}</div>
              <div className="cell-right">{p.acres ? Number(p.acres).toFixed(1) : '--'}</div>
              <div className="cell-right" style={{ paddingRight: 12 }}>{formatCurrencyCompact(p.aprtotal)}</div>
              <div style={{ paddingLeft: 12, borderLeft: '1px solid var(--border)', minWidth: 0 }}>
                <div style={{ color: 'var(--text-primary)', fontWeight: 600 }}>{p.top_signal || '--'}</div>
                <ReasonChips reasons={p.reason_signals} />
              </div>
              <Button
                tone={comparison.includes(p.pidn) ? 'secondary' : 'quiet'}
                aria-label={`${comparison.includes(p.pidn) ? 'Remove' : 'Add'} ${p.propadr || p.pidn} ${comparison.includes(p.pidn) ? 'from' : 'to'} comparison`}
                onClick={() => {
                  const result = toggleComparison(p.pidn)
                  if (result.full) window.alert('Comparison is limited to four parcels.')
                }}
              >
                {comparison.includes(p.pidn) ? '✓ Added' : '+ Add'}
              </Button>
            </div>
          ))}
        </div>
      )}

      {!loading && !error && parcels.length === 0 && (
        <div className="status-message">
          {view === 'movers' && !previousComputedAt
            ? 'No previous radar snapshot to compare against yet.'
            : 'No parcels match the current filters.'}
        </div>
      )}

      {!loading && hasMore && (
        <div style={{ textAlign: 'center', marginTop: 24 }}>
          <button
            onClick={() => {
              if (loadingMore) return
              const controller = new AbortController()
              loadMoreController.current?.abort()
              loadMoreController.current = controller
              void fetchPage(page + 1, true, requestGeneration.current, controller.signal)
            }}
            disabled={loadingMore}
            style={{
              fontFamily: 'var(--font-mono)', fontSize: 11, color: '#22c55e',
              background: 'none', border: '1px solid var(--border)', borderRadius: 4,
              padding: '8px 24px', cursor: 'pointer',
            }}
          >
            {loadingMore ? 'Loading...' : 'Load More'}
          </button>
        </div>
      )}
    </PageShell>
  )
}

function DeltaBadge({ parcel, basis }: { parcel: RadarParcel; basis: 'opportunity' | 'momentum' }) {
  if (parcel.is_new) return <span className="cell-muted" style={{ color: 'var(--accent-gold)', fontWeight: 600 }}>New</span>
  const delta = basis === 'momentum' ? parcel.score_delta : parcel.opportunity_delta
  if (delta == null || delta === 0) return <span className="cell-muted">—</span>
  const color = delta > 0 ? 'var(--accent-green)' : 'var(--accent-red)'
  return <span style={{ color, fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>{delta > 0 ? '▲' : '▼'} {Math.abs(delta)}</span>
}

function ReasonChips({ reasons }: { reasons: ReasonSignal[] | undefined }) {
  if (!Array.isArray(reasons) || reasons.length <= 1) return null
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 6 }}>
      {reasons.slice(1, 4).map((reason) => (
        <span
          key={reason.key}
          title={reason.label}
          style={{
            fontSize: 11.5,
            lineHeight: 1.4,
            padding: '2px 8px',
            borderRadius: 999,
            border: '1px solid var(--border)',
            color: reason.is_risk ? 'var(--accent-red)' : reason.is_direct ? 'var(--text-primary)' : 'var(--text-secondary)',
            background: 'var(--bg-panel)',
            maxWidth: 260,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {reason.label}
        </span>
      ))}
    </div>
  )
}
