import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
// @ts-ignore — Link already imported
import Nav from '../components/Nav'

const CLASS_NAMES: Record<string, string> = {
  'R': 'Residential', 'C': 'Commercial', 'I': 'Industrial',
  'F': 'Farm', 'E': 'Exempt', 'A': 'Agricultural', 'U': 'Utility',
}

const SCHOOL_DISTRICTS: Record<string, string> = {
  '002': 'Central York', '004': 'Dallastown', '006': 'Dover',
  '008': 'Eastern York', '010': 'Hanover', '012': 'Northeastern',
  '014': 'Northern York', '016': 'Red Lion', '018': 'South Eastern',
  '020': 'South Western', '022': 'Southern York', '024': 'Spring Grove',
  '026': 'West Shore', '028': 'West York', '030': 'York Suburban',
  '17F': 'York City', '17G': 'York City', '17L': 'York City', '17N': 'York City',
}

function fmtDollar(v: any): string {
  if (!v) return '--'
  const n = typeof v === 'number' ? v : parseFloat(v)
  if (isNaN(n)) return '--'
  if (n >= 1e6) return `$${(n / 1e6).toFixed(1)}M`
  return `$${n.toLocaleString('en-US', { maximumFractionDigits: 0 })}`
}

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
  const [parcels, setParcels] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [classFilter, setClassFilter] = useState('')
  const [minAcres, setMinAcres] = useState('')
  const [page, setPage] = useState(0)
  const PAGE_SIZE = 200

  const fetchPage = (pageNum: number, append: boolean) => {
    append ? setLoadingMore(true) : setLoading(true)
    const params = new URLSearchParams({ limit: String(PAGE_SIZE), min_score: '0.2' })
    if (classFilter) params.set('parcel_class', classFilter)
    if (minAcres) params.set('min_acres', minAcres)

    fetch(`/api/scores/distressed?${params}`)
      .then(r => r.json())
      .then(d => {
        const items = d.parcels || []
        if (append) {
          setParcels(prev => [...prev, ...items])
        } else {
          setParcels(items)
        }
        setLoading(false)
        setLoadingMore(false)
      })
      .catch(() => { setLoading(false); setLoadingMore(false) })
  }

  useEffect(() => {
    setPage(0)
    fetchPage(0, false)
  }, [classFilter, minAcres])

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-deep)' }}>
      <Nav />
      <main style={{ maxWidth: 1100, margin: '0 auto', padding: '48px 32px' }}>

        <button onClick={() => navigate(-1)} style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', background: 'none', border: 'none', cursor: 'pointer', padding: 0, marginBottom: 24 }}>&larr; Back</button>

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

        {/* Results */}
        {!loading && parcels.length > 0 && (
          <div style={{ border: '1px solid var(--border)', borderRadius: 8, overflow: 'hidden', animation: 'fadeUp 0.4s ease 0.2s both' }}>
            {/* Header */}
            <div style={{ display: 'grid', gridTemplateColumns: '55px 1fr 120px 100px 100px 70px 90px', padding: '10px 16px', background: 'var(--bg-card)', fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: 1.5, textTransform: 'uppercase', color: 'var(--text-muted)' }}>
              <div>Score</div><div>Owner / Address</div><div>District</div><div style={{ textAlign: 'right' }}>Owed</div><div style={{ textAlign: 'right' }}>Assessed</div><div style={{ textAlign: 'right' }}>Acres</div><div style={{ textAlign: 'right' }}>Class</div>
            </div>

            {parcels.map((p, i) => (
              <Link key={p.pidn} to={`/property/${p.pidn}`} style={{
                display: 'grid', gridTemplateColumns: '55px 1fr 120px 100px 100px 70px 90px',
                padding: '12px 16px', alignItems: 'center', textDecoration: 'none', color: 'inherit',
                background: i % 2 === 0 ? 'var(--bg-panel)' : 'var(--bg-card)',
                borderTop: '1px solid var(--border)', transition: 'background 0.15s',
              }}
                onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'var(--bg-card-hover)' }}
                onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = i % 2 === 0 ? 'var(--bg-panel)' : 'var(--bg-card)' }}
              >
                <div>{scoreBar(p.distress_score)}</div>
                <div>
                  <div style={{ fontFamily: 'var(--font-sans)', fontSize: 13, fontWeight: 500, color: 'var(--text-primary)' }}>{p.owner_full}</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}>{p.propadr || p.pidn}</div>
                </div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-secondary)' }}>
                  {SCHOOL_DISTRICTS[p.school_dis] || p.school_dis}
                </div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--accent-red)', textAlign: 'right', fontWeight: 600 }}>
                  {fmtDollar(p.total_owed)}
                </div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-secondary)', textAlign: 'right' }}>
                  {fmtDollar(p.aprtotal)}
                </div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-secondary)', textAlign: 'right' }}>
                  {p.acres ? Number(p.acres).toFixed(1) : '--'}
                </div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', textAlign: 'right' }}>
                  {CLASS_NAMES[p.class] || p.class}
                </div>
              </Link>
            ))}
          </div>
        )}
      </main>
    </div>
  )
}
