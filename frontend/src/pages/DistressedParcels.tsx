import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import BackButton from '../components/BackButton'
import PageShell from '../components/PageShell'
import { formatCurrencyCompact } from '../lib/format'
import { getPropertyClassLabel, getSchoolDistrictLabel } from '../lib/propertyLabels'
import type {
  DistressedParcel,
  DistressedResponse,
} from '../types/api'

function scoreColor(s: number): string {
  if (s >= 0.7) return 'var(--accent-red)'
  if (s >= 0.5) return 'var(--accent-gold)'
  return 'var(--accent-blue)'
}

function scoreBar(s: number) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 16, fontWeight: 700, color: scoreColor(s) }}>
        {(s * 100).toFixed(0)}
      </span>
      <div style={{ width: 40, height: 4, background: 'var(--border)', borderRadius: 2, overflow: 'hidden' }}>
        <div style={{ width: `${Math.min(s * 100, 100)}%`, height: '100%', background: scoreColor(s), borderRadius: 2 }} />
      </div>
    </div>
  )
}

export default function DistressedParcels() {
  const navigate = useNavigate()
  const [parcels, setParcels] = useState<DistressedParcel[]>([])
  const [error, setError] = useState<string | null>(null)
  const [classFilter, setClassFilter] = useState('')
  const [minAcres, setMinAcres] = useState('')
  const PAGE_SIZE = 200

  // Cache results to avoid re-fetching on back navigation. Loading is
  // derived (resolved key vs requested key) so the effect never sets state
  // synchronously; cache hits resolve through the same promise chain.
  const cacheKey = `distressed_${classFilter}_${minAcres}`
  const [resolvedKey, setResolvedKey] = useState<string | null>(null)
  const loading = resolvedKey !== cacheKey

  useEffect(() => {
    const key = `distressed_${classFilter}_${minAcres}`
    let cancelled = false
    const cached = window.__distressedCache?.[key]
    const load: Promise<DistressedParcel[]> = cached
      ? Promise.resolve(cached)
      : (() => {
          const params = new URLSearchParams({ limit: String(PAGE_SIZE), min_score: '0.2' })
          if (classFilter) params.set('parcel_class', classFilter)
          if (minAcres) params.set('min_acres', minAcres)
          return fetch(`/api/scores/distressed?${params}`)
            .then(r => {
              if (!r.ok) throw new Error(`Distressed request failed (${r.status})`)
              return r.json()
            })
            .then((d: DistressedResponse) => {
              const items = d.parcels || []
              if (!window.__distressedCache) window.__distressedCache = {}
              window.__distressedCache[key] = items
              return items
            })
        })()
    load
      .then((items) => {
        if (cancelled) return
        setParcels(items)
        setError(null)
        setResolvedKey(key)
      })
      .catch((err) => {
        if (cancelled) return
        console.error('Failed to load distressed parcels', err)
        setError(err.message)
        setResolvedKey(key)
      })
    return () => {
      cancelled = true
    }
  }, [classFilter, minAcres])

  return (
    <PageShell maxWidth={1100}>
      <BackButton onClick={() => navigate(-1)} />

        <div style={{ animation: 'fadeUp 0.4s ease both', marginBottom: 32 }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, letterSpacing: 3, textTransform: 'uppercase', color: 'var(--accent-red)', marginBottom: 8 }}>Intelligence</div>
          <h1 style={{ fontFamily: 'var(--font-mono)', fontSize: 28, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 8 }}>Distressed Acquisition Opportunities</h1>
          <p style={{ fontFamily: 'var(--font-sans)', fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            Parcels ranked by 9 weighted signals: tax delinquency, sheriff sale/foreclosure, tax sale stage, vacancy, traffic proximity, flood risk, acreage, property class, and hold time.
          </p>
          <Link to="/assemblage" style={{ display: 'inline-block', marginTop: 12, fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--accent-purple)', textDecoration: 'none', padding: '4px 12px', border: '1px solid var(--border)', borderRadius: 4 }}>
            View Assemblage Opportunities &rarr;
          </Link>
        </div>

        {/* Filters */}
        <div style={{ display: 'flex', gap: 12, marginBottom: 24, animation: 'fadeUp 0.4s ease 0.1s both' }}>
          <select value={classFilter} onChange={e => setClassFilter(e.target.value)} style={{
            background: 'var(--bg-panel)', border: '1px solid var(--border)', borderRadius: 4,
            padding: '6px 12px', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-primary)',
          }}>
            <option value="">All Classes</option>
            <option value="C">Commercial</option>
            <option value="I">Industrial</option>
            <option value="F">Farm</option>
            <option value="R">Residential</option>
            <option value="A">Agricultural</option>
          </select>
          <select value={minAcres} onChange={e => setMinAcres(e.target.value)} style={{
            background: 'var(--bg-panel)', border: '1px solid var(--border)', borderRadius: 4,
            padding: '6px 12px', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-primary)',
          }}>
            <option value="">Any Size</option>
            <option value="1">1+ acres</option>
            <option value="5">5+ acres</option>
            <option value="10">10+ acres</option>
            <option value="50">50+ acres</option>
          </select>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', display: 'flex', alignItems: 'center' }}>
            {loading ? 'Loading...' : `${parcels.length} opportunities`}
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
            <div style={{ display: 'grid', gridTemplateColumns: '55px 1fr 120px 100px 100px 70px 90px', padding: '12px 20px', background: 'var(--bg-card)', fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: 1.5, textTransform: 'uppercase', color: 'var(--text-muted)' }}>
              <div>Score</div><div>Parcel / Address</div><div>District</div><div style={{ textAlign: 'right' }}>Distress</div><div style={{ textAlign: 'right' }}>Assessed</div><div style={{ textAlign: 'right' }}>Acres</div><div style={{ textAlign: 'right' }}>Class</div>
            </div>

            {parcels.map((p, i) => (
              <Link key={p.pidn} to={`/property/${p.pidn}`} style={{
                display: 'grid', gridTemplateColumns: '55px 1fr 120px 100px 100px 70px 90px',
                padding: '14px 20px', alignItems: 'center', textDecoration: 'none', color: 'inherit',
                background: i % 2 === 0 ? 'var(--bg-panel)' : 'var(--bg-card)',
                borderTop: '1px solid var(--border)', transition: 'background 0.15s',
              }}
                onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'var(--bg-card-hover)' }}
                onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = i % 2 === 0 ? 'var(--bg-panel)' : 'var(--bg-card)' }}
              >
                <div>{scoreBar(p.distress_score)}</div>
                <div>
                  <div style={{ fontFamily: 'var(--font-sans)', fontSize: 13, fontWeight: 500, color: 'var(--text-primary)' }}>{p.pidn}</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}>{p.propadr || p.pidn}</div>
                </div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-secondary)' }}>
                  {getSchoolDistrictLabel(p.school_dis)}
                </div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--accent-red)', textAlign: 'right', fontWeight: 600 }}>
                  {Math.round((p.delinquency_score ?? 0) * 100)}%
                </div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-secondary)', textAlign: 'right' }}>
                  {formatCurrencyCompact(p.aprtotal)}
                </div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-secondary)', textAlign: 'right' }}>
                  {p.acres ? Number(p.acres).toFixed(1) : '--'}
                </div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', textAlign: 'right' }}>
                  {getPropertyClassLabel(p.class)}
                </div>
              </Link>
            ))}
          </div>
        )}
    </PageShell>
  )
}
