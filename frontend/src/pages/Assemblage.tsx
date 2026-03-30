import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import Nav from '../components/Nav'

const SCHOOL_DISTRICTS: Record<string, string> = {
  '002': 'Central York', '004': 'Dallastown', '006': 'Dover',
  '008': 'Eastern York', '010': 'Hanover', '012': 'Northeastern',
  '014': 'Northern York', '016': 'Red Lion', '018': 'South Eastern',
  '020': 'South Western', '022': 'Southern York', '024': 'Spring Grove',
  '026': 'West Shore', '028': 'West York', '030': 'York Suburban',
  '17F': 'York City', '17G': 'York City', '17L': 'York City', '17N': 'York City',
}

const CLASS_NAMES: Record<string, string> = {
  'R': 'Residential', 'C': 'Commercial', 'I': 'Industrial',
  'F': 'Farm', 'E': 'Exempt', 'A': 'Agricultural', 'U': 'Utility',
}

function fmtDollar(v: any): string {
  if (!v) return '--'
  const n = typeof v === 'number' ? v : parseFloat(v)
  if (isNaN(n)) return '--'
  if (n >= 1e6) return `$${(n / 1e6).toFixed(1)}M`
  return `$${n.toLocaleString('en-US', { maximumFractionDigits: 0 })}`
}

export default function Assemblage() {
  const navigate = useNavigate()
  const [clusters, setClusters] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [minParcels, setMinParcels] = useState('3')
  const [expanded, setExpanded] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    fetch(`/api/scores/assemblage?min_parcels=${minParcels}&min_acres=0.5&limit=50`)
      .then(r => r.json())
      .then(d => { setClusters(d.clusters || []); setLoading(false) })
      .catch(() => setLoading(false))
  }, [minParcels])

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-deep)' }}>
      <Nav />
      <main style={{ maxWidth: 1100, margin: '0 auto', padding: '48px 32px' }}>

        <button onClick={() => navigate(-1)} style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', background: 'none', border: 'none', cursor: 'pointer', padding: 0, marginBottom: 24 }}>&larr; Back</button>

        <div style={{ animation: 'fadeUp 0.4s ease both', marginBottom: 32 }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, letterSpacing: 3, textTransform: 'uppercase', color: 'var(--accent-purple)', marginBottom: 8 }}>Intelligence</div>
          <h1 style={{ fontFamily: 'var(--font-mono)', fontSize: 28, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 8 }}>Assemblage Opportunities</h1>
          <p style={{ fontFamily: 'var(--font-sans)', fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            Clusters of adjacent parcels with shared distress signals — delinquency, vacancy, fragmented ownership.
            Each cluster represents a potential land assembly acquisition.
          </p>
        </div>

        {/* Filters */}
        <div style={{ display: 'flex', gap: 12, marginBottom: 24 }}>
          <select value={minParcels} onChange={e => setMinParcels(e.target.value)} style={{
            background: 'var(--bg-panel)', border: '1px solid var(--border)', borderRadius: 4,
            padding: '6px 12px', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-primary)',
          }}>
            <option value="2">2+ adjacent</option>
            <option value="3">3+ adjacent</option>
            <option value="5">5+ adjacent</option>
            <option value="10">10+ adjacent</option>
          </select>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', display: 'flex', alignItems: 'center' }}>
            {loading ? 'Loading...' : `${clusters.length} clusters found`}
          </span>
        </div>

        {/* Results */}
        {!loading && clusters.map((c, i) => {
          const isExpanded = expanded === c.seed_pidn
          return (
            <div key={c.seed_pidn} style={{
              marginBottom: 12,
              border: '1px solid var(--border)',
              borderRadius: 8,
              overflow: 'hidden',
              animation: `fadeUp 0.4s ease ${0.05 + i * 0.02}s both`,
              opacity: 0,
            }}>
              {/* Cluster header */}
              <div
                onClick={() => setExpanded(isExpanded ? null : c.seed_pidn)}
                style={{
                  display: 'grid', gridTemplateColumns: '1fr 100px 100px 100px 80px 80px',
                  padding: '16px 20px', alignItems: 'center', cursor: 'pointer',
                  background: 'var(--bg-panel)', transition: 'background 0.15s',
                }}
                onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'var(--bg-card-hover)' }}
                onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'var(--bg-panel)' }}
              >
                <div>
                  <div style={{ fontFamily: 'var(--font-sans)', fontSize: 15, fontWeight: 600, color: 'var(--text-primary)' }}>
                    {c.seed_owner}
                  </div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
                    {c.seed_address || c.seed_pidn} · {SCHOOL_DISTRICTS[c.school_dis] || c.school_dis} · {CLASS_NAMES[c.seed_class] || c.seed_class}
                  </div>
                </div>
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 18, fontWeight: 700, color: 'var(--accent-blue)' }}>{c.adjacent_count}</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-muted)', letterSpacing: 1, textTransform: 'uppercase' }}>Adjacent</div>
                </div>
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 18, fontWeight: 700, color: 'var(--accent-red)' }}>{c.delinquent_neighbors}</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-muted)', letterSpacing: 1, textTransform: 'uppercase' }}>Delinquent</div>
                </div>
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 18, fontWeight: 700, color: 'var(--accent-green)' }}>{c.vacant_neighbors}</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-muted)', letterSpacing: 1, textTransform: 'uppercase' }}>Vacant</div>
                </div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--text-secondary)', textAlign: 'right' }}>
                  {c.total_acres?.toFixed(1)} ac
                </div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--accent-green)', textAlign: 'right' }}>
                  {fmtDollar(c.total_assessed)}
                </div>
              </div>

              {/* Expanded neighbor details */}
              {isExpanded && (
                <div style={{ borderTop: '1px solid var(--border)' }}>
                  <div style={{ padding: '8px 20px', background: 'var(--bg-card)', fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: 1.5, textTransform: 'uppercase', color: 'var(--text-muted)', display: 'grid', gridTemplateColumns: '1fr 1fr 80px 80px 80px 60px' }}>
                    <div>Owner</div><div>Address</div><div style={{ textAlign: 'right' }}>Assessed</div><div style={{ textAlign: 'right' }}>Acres</div><div>Status</div><div></div>
                  </div>
                  {/* Seed parcel */}
                  <Link to={`/property/${c.seed_pidn}`} style={{ textDecoration: 'none', color: 'inherit', display: 'grid', gridTemplateColumns: '1fr 1fr 80px 80px 80px 60px', padding: '8px 20px', background: 'rgba(224,82,82,0.08)', borderBottom: '1px solid var(--border)' }}>
                    <div style={{ fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--text-primary)', fontWeight: 600 }}>{c.seed_owner}</div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-secondary)' }}>{c.seed_address}</div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-secondary)', textAlign: 'right' }}>{fmtDollar(c.seed_assessed)}</div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, textAlign: 'right' }}>{c.seed_acres?.toFixed(1)}</div>
                    <div><Badge color="var(--accent-red)">Delinquent</Badge></div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--accent-blue)' }}>Seed</div>
                  </Link>
                  {/* Neighbors */}
                  {(c.neighbors || []).map((n: any, j: number) => (
                    <Link key={n.pidn} to={`/property/${n.pidn}`} style={{
                      textDecoration: 'none', color: 'inherit',
                      display: 'grid', gridTemplateColumns: '1fr 1fr 80px 80px 80px 60px',
                      padding: '8px 20px',
                      background: j % 2 === 0 ? 'var(--bg-panel)' : 'var(--bg-card)',
                      borderBottom: '1px solid var(--border)',
                    }}>
                      <div style={{ fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--text-primary)' }}>{n.owner}</div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-secondary)' }}>{n.address}</div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-secondary)', textAlign: 'right' }}>{fmtDollar(n.assessed)}</div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, textAlign: 'right' }}>{n.acres ? Number(n.acres).toFixed(1) : '--'}</div>
                      <div style={{ display: 'flex', gap: 4 }}>
                        {n.delinquent && <Badge color="var(--accent-red)">Delq</Badge>}
                        {n.vacant && <Badge color="var(--accent-gold)">Vacant</Badge>}
                      </div>
                      <div></div>
                    </Link>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </main>
    </div>
  )
}

function Badge({ color, children }: { color: string; children: React.ReactNode }) {
  return (
    <span style={{
      display: 'inline-block', padding: '1px 6px', borderRadius: 3,
      fontFamily: 'var(--font-mono)', fontSize: 9, fontWeight: 600,
      color, background: `${color}20`, border: `1px solid ${color}40`,
    }}>
      {children}
    </span>
  )
}
