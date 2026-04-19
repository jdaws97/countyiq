import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import BackButton from '../components/BackButton'
import PageShell from '../components/PageShell'
import { formatCurrencyCompact } from '../lib/format'
import type {
  RadarMunicipalitiesResponse,
  RadarParcel,
  RadarParcelResponse,
  RadarViewMode,
} from '../types/api'

function scoreColor(s: number): string {
  if (s >= 60) return '#22c55e'
  if (s >= 40) return '#eab308'
  if (s >= 20) return '#06b6d4'
  return 'var(--text-secondary)'
}

export default function DevelopmentRadar() {
  const navigate = useNavigate()
  const [parcels, setParcels] = useState<RadarParcel[]>([])
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [muniFilter, setMuniFilter] = useState('')
  const [minScoreByView, setMinScoreByView] = useState<Record<RadarViewMode, string>>({
    opportunity: '30',
    momentum: '50',
  })
  const [page, setPage] = useState(0)
  const [view, setView] = useState<RadarViewMode>('opportunity')
  const PAGE_SIZE = 200

  const [municipalities, setMunicipalities] = useState<string[]>([])
  const minScore = minScoreByView[view]
  const setMinScore = (value: string) => {
    setMinScoreByView(prev => ({ ...prev, [view]: value }))
  }
  const scoreOptions = view === 'opportunity'
    ? [
        { value: '30', label: '30+ Recommended' },
        { value: '40', label: '40+' },
        { value: '50', label: '50+' },
        { value: '60', label: '60+' },
        { value: '0', label: '0+ Any' },
      ]
    : [
        { value: '50', label: '50+ Recommended' },
        { value: '60', label: '60+' },
        { value: '70', label: '70+' },
        { value: '80', label: '80+' },
        { value: '0', label: '0+ Any' },
      ]

  const fetchPage = (pageNum: number, append: boolean) => {
    append ? setLoadingMore(true) : setLoading(true)
    const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(pageNum * PAGE_SIZE) })
    if (muniFilter) params.set('municipality', muniFilter)
    params.set('min_score', minScore)

    const endpoint = view === 'opportunity' ? '/api/scores/opportunity' : '/api/scores/development'

    fetch(`${endpoint}?${params}`)
      .then(r => {
        if (!r.ok) throw new Error(`Radar request failed (${r.status})`)
        return r.json()
      })
      .then((d: RadarParcelResponse) => {
        const items = d.parcels || []
        if (append) {
          setParcels(prev => [...prev, ...items])
        } else {
          setParcels(items)
        }
        setLoading(false)
        setLoadingMore(false)
      })
      .catch((err) => {
        console.error('Failed to load radar parcels', err)
        setError(err.message)
        setLoading(false)
        setLoadingMore(false)
      })
  }

  useEffect(() => {
    setPage(0)
    setParcels([])
    fetchPage(0, false)
  }, [muniFilter, minScore, view])

  useEffect(() => {
    const params = new URLSearchParams({ view, min_score: minScore })
    fetch(`/api/scores/municipalities?${params}`)
      .then(r => {
        if (!r.ok) throw new Error(`Municipalities request failed (${r.status})`)
        return r.json()
      })
      .then((d: RadarMunicipalitiesResponse) => {
        const munis = (d.municipalities || []) as string[]
        setMunicipalities(munis)
        if (muniFilter && !munis.includes(muniFilter)) {
          setMuniFilter('')
        }
      })
      .catch((err) => {
        console.error('Failed to load radar municipalities', err)
      })
  }, [view, minScore, muniFilter])

  return (
    <PageShell maxWidth={1100}>
      <BackButton onClick={() => navigate(-1)} />

        <div style={{ animation: 'fadeUp 0.4s ease both', marginBottom: 32 }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, letterSpacing: 3, textTransform: 'uppercase', color: '#22c55e', marginBottom: 8 }}>Intelligence</div>
          <h1 style={{ fontFamily: 'var(--font-mono)', fontSize: 28, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 8 }}>Development Radar</h1>
          <p style={{ fontFamily: 'var(--font-sans)', fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            {view === 'opportunity'
              ? 'Parcels with strong fundamentals but no developer activity yet \u2014 the early signal.'
              : 'Where development activity is already happening \u2014 market awareness.'}
          </p>
        </div>

        {/* View Toggle */}
        <div style={{ display: 'flex', gap: 0, marginBottom: 20, animation: 'fadeUp 0.4s ease 0.05s both' }}>
          <button
            onClick={() => setView('opportunity')}
            style={{
              fontFamily: 'var(--font-mono)', fontSize: 12, padding: '8px 20px', cursor: 'pointer',
              background: view === 'opportunity' ? '#22c55e' : 'var(--bg-panel)',
              color: view === 'opportunity' ? '#000' : 'var(--text-secondary)',
              border: '1px solid var(--border)', borderRadius: '4px 0 0 4px', fontWeight: view === 'opportunity' ? 700 : 400,
            }}
          >
            Opportunity
          </button>
          <button
            onClick={() => setView('momentum')}
            style={{
              fontFamily: 'var(--font-mono)', fontSize: 12, padding: '8px 20px', cursor: 'pointer',
              background: view === 'momentum' ? '#06b6d4' : 'var(--bg-panel)',
              color: view === 'momentum' ? '#000' : 'var(--text-secondary)',
              border: '1px solid var(--border)', borderLeft: 'none', borderRadius: '0 4px 4px 0', fontWeight: view === 'momentum' ? 700 : 400,
            }}
          >
            Momentum
          </button>
        </div>

        {/* Filters */}
        <div style={{ display: 'flex', gap: 12, marginBottom: 24, animation: 'fadeUp 0.4s ease 0.1s both' }}>
          <select value={muniFilter} onChange={e => setMuniFilter(e.target.value)} style={{
            background: 'var(--bg-panel)', border: '1px solid var(--border)', borderRadius: 4,
            padding: '6px 12px', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-primary)',
          }}>
            <option value="">All Municipalities</option>
            {municipalities.map(m => <option key={m} value={m}>{m}</option>)}
          </select>
          <select value={minScore} onChange={e => setMinScore(e.target.value)} style={{
            background: 'var(--bg-panel)', border: '1px solid var(--border)', borderRadius: 4,
            padding: '6px 12px', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-primary)',
          }}>
            {scoreOptions.map(option => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', display: 'flex', alignItems: 'center' }}>
            {loading ? 'Loading...' : `${parcels.length} ${view === 'opportunity' ? 'opportunities' : 'active sites'}`}
          </div>
        </div>

        {error && (
          <div style={{
            fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--accent-red)',
            padding: 24, background: 'rgba(224, 82, 82, 0.08)',
            border: '1px solid rgba(224, 82, 82, 0.2)', borderRadius: 6, marginBottom: 24,
          }}>
            Failed to load data: {error}
          </div>
        )}

        {/* Results */}
        {!loading && parcels.length > 0 && (
          <div style={{ border: '1px solid var(--border)', borderRadius: 8, overflow: 'hidden', animation: 'fadeUp 0.4s ease 0.2s both' }}>
            {/* Header */}
            <div style={{ display: 'grid', gridTemplateColumns: '55px 1fr 120px 80px 100px 1fr 60px', padding: '12px 20px', background: 'var(--bg-card)', fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: 1.5, textTransform: 'uppercase', color: 'var(--text-muted)' }}>
              <div>Score</div><div>Address</div><div>Municipality</div><div style={{ textAlign: 'right' }}>Acres</div><div style={{ textAlign: 'right' }}>Value</div><div>Why It Ranked</div><div style={{ textAlign: 'right' }}>Signals</div>
            </div>

            {parcels.map((p, i) => (
              <Link key={p.pidn} to={`/property/${p.pidn}`} style={{
                display: 'grid', gridTemplateColumns: '55px 1fr 120px 80px 100px 1fr 60px',
                padding: '14px 20px', alignItems: 'center', textDecoration: 'none', color: 'inherit',
                background: i % 2 === 0 ? 'var(--bg-panel)' : 'var(--bg-card)',
                borderTop: '1px solid var(--border)', transition: 'background 0.15s',
              }}
                onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'var(--bg-card-hover)' }}
                onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = i % 2 === 0 ? 'var(--bg-panel)' : 'var(--bg-card)' }}
              >
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 16, fontWeight: 700, color: scoreColor(p.score) }}>
                  {p.score}
                </div>
                <div>
                  <div style={{ fontFamily: 'var(--font-sans)', fontSize: 13, fontWeight: 500, color: 'var(--text-primary)' }}>{p.propadr || p.pidn}</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>{p.owner_full}</div>
                </div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-secondary)' }}>
                  {p.municipality || '--'}
                </div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-secondary)', textAlign: 'right' }}>
                  {p.acres ? Number(p.acres).toFixed(1) : '--'}
                </div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-secondary)', textAlign: 'right' }}>
                  {formatCurrencyCompact(p.aprtotal)}
                </div>
                <div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: view === 'opportunity' ? '#22c55e' : '#06b6d4' }}>
                    {p.top_signal || '--'}
                  </div>
                  {Array.isArray(p.reason_signals) && p.reason_signals.length > 1 && (
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>
                      {p.reason_signals[1]?.label}
                    </div>
                  )}
                </div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)', textAlign: 'right' }}>
                  {p.signal_count ?? '--'}
                </div>
              </Link>
            ))}
          </div>
        )}

        {!loading && parcels.length === 0 && (
          <div style={{ textAlign: 'center', padding: 48, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: 13 }}>
            No parcels match the current filters.
          </div>
        )}

        {/* Load More */}
        {!loading && parcels.length > 0 && parcels.length % PAGE_SIZE === 0 && (
          <div style={{ textAlign: 'center', marginTop: 24 }}>
            <button
              onClick={() => { const next = page + 1; setPage(next); fetchPage(next, true) }}
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
