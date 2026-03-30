import { useEffect, useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
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
  if (n >= 1e9) return `$${(n / 1e9).toFixed(1)}B`
  if (n >= 1e6) return `$${(n / 1e6).toFixed(1)}M`
  return `$${n.toLocaleString('en-US', { maximumFractionDigits: 0 })}`
}

export default function OwnerProfile() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!id) return
    fetch(`/api/owners/${id}`)
      .then(r => { if (!r.ok) throw new Error(`${r.status}`); return r.json() })
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [id])

  if (loading) return <Page><div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--text-muted)', textAlign: 'center', padding: '80px 0' }}>Loading owner profile...</div></Page>
  if (!data) return <Page><div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--accent-red)' }}>Owner not found</div></Page>

  const owner = data.owner
  const portfolio = data.portfolio
  const delinq = data.delinquency
  const licenses = data.licenses

  return (
    <Page>
      <button onClick={() => navigate(-1)} style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', background: 'none', border: 'none', cursor: 'pointer', padding: 0, marginBottom: 24 }}>&larr; Back</button>

      {/* Header */}
      <div style={{ animation: 'fadeUp 0.4s ease both', marginBottom: 32 }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, letterSpacing: 3, textTransform: 'uppercase', color: 'var(--accent-gold)', marginBottom: 8 }}>Owner Profile</div>
        <h1 style={{ fontFamily: 'var(--font-sans)', fontSize: 28, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 8 }}>{owner.canonical_name}</h1>
        <div style={{ display: 'flex', gap: 8 }}>
          <Badge color="var(--accent-blue)">{owner.entity_type === 'business' ? 'Business' : 'Person'}</Badge>
          {delinq.total_owed > 0 && <Badge color="var(--accent-red)">Tax Delinquent — {fmtDollar(delinq.total_owed)}</Badge>}
          {licenses.length > 0 && <Badge color="var(--accent-green)">{licenses.length} Liquor License{licenses.length > 1 ? 's' : ''}</Badge>}
        </div>
      </div>

      {/* Stats */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 32, animation: 'fadeUp 0.4s ease 0.1s both' }}>
        <StatCard label="Properties" value={portfolio.parcel_count.toLocaleString()} color="var(--accent-blue)" />
        <StatCard label="Total Assessed" value={fmtDollar(portfolio.total_assessed)} color="var(--accent-green)" />
        <StatCard label="Delinquent" value={delinq.delinquent_parcels.toLocaleString()} color={delinq.delinquent_parcels > 0 ? 'var(--accent-red)' : 'var(--text-muted)'} />
        <StatCard label="Total Owed" value={fmtDollar(delinq.total_owed)} color="var(--accent-gold)" />
      </div>

      {/* Property Portfolio */}
      <Section title={`Properties (${portfolio.parcel_count})`}>
        <div style={{ border: '1px solid var(--border)', borderRadius: 6, overflow: 'hidden' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '140px 1fr 100px 100px 80px', padding: '8px 16px', background: 'var(--bg-card)', fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: 1.5, textTransform: 'uppercase', color: 'var(--text-muted)' }}>
            <div>PIDN</div><div>Address</div><div style={{ textAlign: 'right' }}>Assessed</div><div style={{ textAlign: 'right' }}>Sale Price</div><div style={{ textAlign: 'right' }}>Class</div>
          </div>
          {portfolio.parcels.map((p: any, i: number) => (
            <Link key={p.pidn} to={`/property/${p.pidn}`} style={{ textDecoration: 'none', color: 'inherit', display: 'grid', gridTemplateColumns: '140px 1fr 100px 100px 80px', padding: '10px 16px', borderTop: '1px solid var(--border)', background: i % 2 === 0 ? 'var(--bg-panel)' : 'var(--bg-card)', transition: 'background 0.15s' }}
              onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'var(--bg-card-hover)' }}
              onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = i % 2 === 0 ? 'var(--bg-panel)' : 'var(--bg-card)' }}
            >
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--accent-blue)' }}>{p.pidn}</div>
              <div style={{ fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--text-primary)' }}>{p.propadr || '--'}</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-secondary)', textAlign: 'right' }}>{fmtDollar(p.aprtotal)}</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-secondary)', textAlign: 'right' }}>{fmtDollar(p.price)}</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', textAlign: 'right' }}>{CLASS_NAMES[p.class] || p.class}</div>
            </Link>
          ))}
        </div>
      </Section>

      {/* Tax Delinquency */}
      {delinq.records.length > 0 && (
        <Section title={`Tax Delinquency (${fmtDollar(delinq.total_owed)} across ${delinq.delinquent_parcels} parcel${delinq.delinquent_parcels > 1 ? 's' : ''})`}>
          <div style={{ border: '1px solid var(--border)', borderRadius: 6, overflow: 'hidden' }}>
            {delinq.records.map((r: any, i: number) => (
              <div key={i} style={{ display: 'grid', gridTemplateColumns: '140px 1fr 80px 80px 120px', padding: '8px 16px', borderTop: i > 0 ? '1px solid var(--border)' : 'none', background: i % 2 === 0 ? 'var(--bg-panel)' : 'var(--bg-card)', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-secondary)' }}>
                <div style={{ color: 'var(--accent-blue)' }}>{r.pidn}</div>
                <div>{r.property_address}</div>
                <div>{r.tax_year}</div>
                <div>{r.authority_name}</div>
                <div style={{ textAlign: 'right', color: 'var(--accent-red)', fontWeight: 600 }}>{fmtDollar(r.total)}</div>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* Liquor Licenses */}
      {licenses.length > 0 && (
        <Section title={`Linked Liquor Licenses (${licenses.length})`}>
          <div style={{ border: '1px solid var(--border)', borderRadius: 6, overflow: 'hidden' }}>
            {licenses.map((l: any, i: number) => (
              <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 16px', borderTop: i > 0 ? '1px solid var(--border)' : 'none', background: i % 2 === 0 ? 'var(--bg-panel)' : 'var(--bg-card)' }}>
                <div>
                  <div style={{ fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--text-primary)' }}>{l.source_name}</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}>{l.source_address}</div>
                </div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}>
                  {l.match_tier} · {Math.round((l.confidence || 0) * 100)}%
                </div>
              </div>
            ))}
          </div>
        </Section>
      )}
    </Page>
  )
}

function Page({ children }: { children: React.ReactNode }) {
  return <div style={{ minHeight: '100vh', background: 'var(--bg-deep)' }}><Nav /><main style={{ maxWidth: 1000, margin: '0 auto', padding: '48px 32px' }}>{children}</main></div>
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return <div style={{ marginBottom: 32, animation: 'fadeUp 0.4s ease both' }}><div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: 2, textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 12, paddingBottom: 8, borderBottom: '1px solid var(--border)' }}>{title}</div>{children}</div>
}

function StatCard({ label, value, color }: { label: string; value: string; color: string }) {
  return <div style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)', borderRadius: 6, padding: '14px 18px' }}><div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: 2, textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 4 }}>{label}</div><div style={{ fontFamily: 'var(--font-mono)', fontSize: 22, fontWeight: 700, color }}>{value}</div></div>
}

function Badge({ color, children }: { color: string; children: React.ReactNode }) {
  return <span style={{ display: 'inline-block', padding: '3px 10px', borderRadius: 4, fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 600, color, background: `${color}20`, border: `1px solid ${color}40` }}>{children}</span>
}
