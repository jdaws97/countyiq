import { useEffect, useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import Nav from '../components/Nav'

interface MuniData {
  name: string
  muni_type: string
  county: string
  delinquency: {
    delinquent_parcels: number
    total_delinquent: number
    oldest_delinquent_year: number | null
    delinquent_years: number
  }
}

interface MuniStats {
  parcel_count: number
  total_assessed: number
  licenses: any[]
  top_owners: any[]
}

function fmtDollar(v: any): string {
  if (!v) return '--'
  const n = typeof v === 'number' ? v : parseFloat(v)
  if (isNaN(n)) return '--'
  if (n >= 1e9) return `$${(n / 1e9).toFixed(1)}B`
  if (n >= 1e6) return `$${(n / 1e6).toFixed(1)}M`
  return `$${n.toLocaleString('en-US', { maximumFractionDigits: 0 })}`
}

export default function MunicipalityDetail() {
  const { name } = useParams<{ name: string }>()
  const navigate = useNavigate()
  const [muni, setMuni] = useState<MuniData | null>(null)
  const [stats, setStats] = useState<MuniStats | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!name) return
    setLoading(true)

    // Fetch municipality profile
    fetch(`/api/municipalities/${encodeURIComponent(name)}`)
      .then(r => { if (!r.ok) throw new Error(`${r.status}`); return r.json() })
      .then(setMuni)
      .catch(() => {})

    // Fetch PLCB licenses for this municipality
    const muniName = decodeURIComponent(name)
    fetch(`/api/licenses?municipality=${encodeURIComponent(muniName)}&limit=50`)
      .then(r => r.json())
      .then(licData => {
        // Fetch delinquent owners for this municipality
        fetch(`/api/delinquent/top-owners?municipality=${encodeURIComponent(muniName)}&limit=10`)
          .then(r => r.json())
          .then(owners => {
            setStats({
              parcel_count: 0,
              total_assessed: 0,
              licenses: licData.licenses || [],
              top_owners: owners || [],
            })
            setLoading(false)
          })
      })
      .catch(() => setLoading(false))
  }, [name])

  if (loading) return <Page><Loading /></Page>
  if (!muni) return <Page><div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--accent-red)' }}>Municipality not found: {name}</div></Page>

  const delinq = muni.delinquency || {}

  return (
    <Page>
      <button onClick={() => navigate(-1)} style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', background: 'none', border: 'none', cursor: 'pointer', padding: 0, marginBottom: 24 }}>&larr; Back</button>

      {/* Header */}
      <div style={{ animation: 'fadeUp 0.4s ease both', marginBottom: 32 }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, letterSpacing: 3, textTransform: 'uppercase', color: 'var(--accent-gold)', marginBottom: 8 }}>Municipality</div>
        <h1 style={{ fontFamily: 'var(--font-sans)', fontSize: 28, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>{muni.name}</h1>
        <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
          <Badge color="var(--accent-blue)">{muni.muni_type}</Badge>
          <Badge color="var(--accent-purple)">{muni.county} County</Badge>
        </div>
      </div>

      {/* Stats Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, marginBottom: 32, animation: 'fadeUp 0.4s ease 0.1s both' }}>
        <StatCard label="Delinquent Parcels" value={delinq.delinquent_parcels?.toLocaleString() || '0'} color={delinq.delinquent_parcels > 0 ? 'var(--accent-red)' : 'var(--accent-green)'} />
        <StatCard label="Total Delinquent" value={fmtDollar(delinq.total_delinquent)} color="var(--accent-gold)" />
        <StatCard label="Oldest Delinquency" value={delinq.oldest_delinquent_year?.toString() || 'None'} color="var(--text-primary)" />
      </div>

      {/* Top Delinquent Owners */}
      {stats?.top_owners && stats.top_owners.length > 0 && (
        <Section title="Top Delinquent Owners">
          <div style={{ border: '1px solid var(--border)', borderRadius: 6, overflow: 'hidden' }}>
            {stats.top_owners.map((o: any, i: number) => (
              <div key={i} style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                padding: '10px 16px', borderTop: i > 0 ? '1px solid var(--border)' : 'none',
                background: i % 2 === 0 ? 'var(--bg-panel)' : 'var(--bg-card)',
              }}>
                <div>
                  <div style={{ fontFamily: 'var(--font-sans)', fontSize: 14, fontWeight: 500, color: 'var(--text-primary)' }}>{o.owner_name}</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}>{o.parcel_count} parcel{o.parcel_count !== 1 ? 's' : ''}</div>
                </div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 14, fontWeight: 600, color: 'var(--accent-red)' }}>
                  {fmtDollar(o.total_owed)}
                </div>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* Liquor Licenses */}
      {stats?.licenses && stats.licenses.length > 0 && (
        <Section title={`Liquor Licenses (${stats.licenses.length})`}>
          <div style={{ border: '1px solid var(--border)', borderRadius: 6, overflow: 'hidden' }}>
            {stats.licenses.map((l: any, i: number) => (
              <div key={i} style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                padding: '10px 16px', borderTop: i > 0 ? '1px solid var(--border)' : 'none',
                background: i % 2 === 0 ? 'var(--bg-panel)' : 'var(--bg-card)',
              }}>
                <div>
                  <div style={{ fontFamily: 'var(--font-sans)', fontSize: 14, fontWeight: 500, color: 'var(--text-primary)' }}>{l.premises_name || l.licensee}</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}>{l.premises_address}</div>
                </div>
                <Badge color="var(--accent-blue)">{l.license_type}</Badge>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* Quick Links */}
      <Section title="Explore">
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <Link to={`/search?q=properties+in+${encodeURIComponent(muni.name)}`} style={linkStyle}>Search Properties</Link>
          <Link to={`/search?q=vacant+land+in+${encodeURIComponent(muni.name)}`} style={linkStyle}>Vacant Land</Link>
          <Link to="/map" style={linkStyle}>View on Map</Link>
        </div>
      </Section>
    </Page>
  )
}

const linkStyle: React.CSSProperties = {
  fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--accent-blue)',
  textDecoration: 'none', padding: '6px 14px', border: '1px solid var(--border)',
  borderRadius: 4,
}

function Page({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-deep)' }}>
      <Nav />
      <main style={{ maxWidth: 900, margin: '0 auto', padding: '48px 32px' }}>{children}</main>
    </div>
  )
}

function Loading() {
  return <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--text-muted)', textAlign: 'center', padding: '80px 0' }}>Loading municipality...</div>
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 32, animation: 'fadeUp 0.4s ease both' }}>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: 2, textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 12, paddingBottom: 8, borderBottom: '1px solid var(--border)' }}>{title}</div>
      {children}
    </div>
  )
}

function StatCard({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)', borderRadius: 6, padding: '16px 20px' }}>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: 2, textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 6 }}>{label}</div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 24, fontWeight: 700, color }}>{value}</div>
    </div>
  )
}

function Badge({ color, children }: { color: string; children: React.ReactNode }) {
  return (
    <span style={{
      display: 'inline-block', padding: '3px 10px', borderRadius: 4,
      fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 600,
      color, background: `${color}20`, border: `1px solid ${color}40`,
    }}>
      {children}
    </span>
  )
}
