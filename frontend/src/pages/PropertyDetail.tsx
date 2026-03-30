import { useEffect, useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import Nav from '../components/Nav'

interface PropertyReport {
  parcel: Record<string, any>
  tax_delinquency: { is_delinquent: boolean; total_owed: number; records: any[] }
  flood_zone: { in_flood_zone: boolean; zone: string | null; sfha: boolean }
  structures: { count: number; likely_vacant: boolean }
}

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
  return `$${n.toLocaleString('en-US', { maximumFractionDigits: 0 })}`
}

export default function PropertyDetail() {
  const { pidn } = useParams<{ pidn: string }>()
  const navigate = useNavigate()
  const [report, setReport] = useState<PropertyReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!pidn) return
    setLoading(true)
    fetch(`/api/parcels/${pidn}`)
      .then(r => { if (!r.ok) throw new Error(`${r.status}`); return r.json() })
      .then(setReport)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [pidn])

  if (loading) return <div style={{ minHeight: '100vh', background: 'var(--bg-deep)' }}><Nav /><main style={{ maxWidth: 900, margin: '0 auto', padding: '48px 32px' }}><div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--text-muted)', textAlign: 'center', padding: '80px 0' }}>Loading property...</div></main></div>
  if (error || !report) return <div style={{ minHeight: '100vh', background: 'var(--bg-deep)' }}><Nav /><main style={{ maxWidth: 900, margin: '0 auto', padding: '48px 32px' }}><div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--accent-red)' }}>Property not found: {pidn}</div></main></div>

  const p = report.parcel
  const tax = report.tax_delinquency
  const flood = report.flood_zone
  const structures = report.structures

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-deep)' }}>
      <Nav />
      <main style={{ maxWidth: 900, margin: '0 auto', padding: '48px 32px' }}>

        {/* Back + Actions */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
          <button onClick={() => navigate(-1)} style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>&larr; Back</button>
          <Link to={`/map?lat=39.95&lng=-76.73&zoom=16`} style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--accent-blue)', textDecoration: 'none', padding: '4px 10px', border: '1px solid var(--border)', borderRadius: 4 }}>View on Map</Link>
        </div>

        {/* Header */}
        <div style={{ animation: 'fadeUp 0.4s ease both', marginBottom: 32 }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, letterSpacing: 3, textTransform: 'uppercase', color: 'var(--accent-gold)', marginBottom: 8 }}>Property Report</div>
          <h1 style={{ fontFamily: 'var(--font-sans)', fontSize: 28, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>{p.owner_full || 'Unknown Owner'}</h1>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 14, color: 'var(--text-secondary)' }}>{p.propadr || 'No address'}</div>
          <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
            {p.class && <Badge color="var(--accent-blue)">{CLASS_NAMES[p.class] || p.class}</Badge>}
            {p.school_dis && <Badge color="var(--accent-purple)">{SCHOOL_DISTRICTS[p.school_dis] || p.school_dis}</Badge>}
            {tax.is_delinquent && <Badge color="var(--accent-red)">Tax Delinquent</Badge>}
            {flood.in_flood_zone && <Badge color="var(--accent-cyan)">Flood Zone {flood.zone}</Badge>}
            {structures.likely_vacant && <Badge color="var(--accent-gold)">Vacant</Badge>}
          </div>
        </div>

        {/* Assessment & Sale */}
        <Section title="Assessment & Sale">
          <Grid>
            <Field label="Assessed Total" value={fmtDollar(p.aprtotal)} highlight />
            <Field label="Acres" value={p.acres ? Number(p.acres).toFixed(2) : '--'} />
            <Field label="Sale Date" value={p.saledt || '--'} />
            <Field label="Sale Price" value={fmtDollar(p.price)} highlight />
            {p.prev_price && <Field label="Previous Price" value={fmtDollar(p.prev_price)} />}
            {p.aprland && <Field label="Land Value" value={fmtDollar(p.aprland)} />}
            {p.aprbldg && <Field label="Building Value" value={fmtDollar(p.aprbldg)} />}
          </Grid>
        </Section>

        {/* Property Details */}
        <Section title="Property Details">
          <Grid>
            <Field label="PIDN" value={p.pidn} />
            <Field label="Class" value={CLASS_NAMES[p.class] || p.class || '--'} />
            <Field label="School District" value={SCHOOL_DISTRICTS[p.school_dis] || p.school_dis || '--'} />
            {p.acres && <Field label="Acres" value={Number(p.acres).toFixed(2)} />}
            {p.yrblt && <Field label="Year Built" value={p.yrblt} />}
            {p.style && <Field label="Style" value={p.style} />}
            {p.num_stories && <Field label="Stories" value={p.num_stories} />}
            {p.res_living_area && <Field label="Living Area" value={`${Number(p.res_living_area).toLocaleString()} sf`} />}
            {p.prev_owner && <Field label="Previous Owner" value={p.prev_owner} />}
            {p.deed_bk && <Field label="Deed" value={`${p.deed_bk}/${p.deed_pg}`} />}
          </Grid>
        </Section>

        {/* Tax Status */}
        <Section title="Tax Status">
          {tax.is_delinquent ? (
            <>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
                <Badge color="var(--accent-red)">Delinquent — {fmtDollar(tax.total_owed)}</Badge>
              </div>
              <div style={{ border: '1px solid var(--border)', borderRadius: 6, overflow: 'hidden' }}>
                <div style={{ display: 'grid', gridTemplateColumns: '80px 120px 1fr 120px', padding: '8px 16px', background: 'var(--bg-card)', fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: 1.5, textTransform: 'uppercase', color: 'var(--text-muted)' }}>
                  <div>Year</div><div>Authority</div><div></div><div style={{ textAlign: 'right' }}>Amount</div>
                </div>
                {tax.records.map((rec: any, i: number) => (
                  <div key={i} style={{ display: 'grid', gridTemplateColumns: '80px 120px 1fr 120px', padding: '8px 16px', borderTop: '1px solid var(--border)', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-secondary)' }}>
                    <div>{rec.tax_year}</div>
                    <div>{rec.authority_name}</div>
                    <div></div>
                    <div style={{ textAlign: 'right', color: 'var(--accent-red)', fontWeight: 600 }}>{fmtDollar(rec.total)}</div>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <Badge color="var(--accent-green)">Current — No Delinquent Taxes</Badge>
          )}
        </Section>

        {/* Flood Risk */}
        <Section title="Flood Risk">
          {flood.in_flood_zone ? (
            <div>
              <Badge color="var(--accent-cyan)">FEMA Zone {flood.zone}</Badge>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-secondary)', marginLeft: 12 }}>
                {flood.sfha ? 'Special Flood Hazard Area — flood insurance required' : 'Minimal flood risk'}
              </span>
            </div>
          ) : (
            <Badge color="var(--accent-green)">Not in Flood Zone</Badge>
          )}
        </Section>

        {/* Structures */}
        <Section title="Structures">
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 14, color: 'var(--text-primary)', marginBottom: structures.buildings?.length ? 12 : 0 }}>
            {structures.count} building footprint{structures.count !== 1 ? 's' : ''} detected
            {structures.likely_vacant && <span style={{ color: 'var(--accent-gold)', marginLeft: 12 }}>— Likely vacant land</span>}
          </div>
          {structures.buildings?.length > 0 && (
            <div style={{ border: '1px solid var(--border)', borderRadius: 6, overflow: 'hidden' }}>
              {structures.buildings.map((b: any, i: number) => (
                <div key={i} style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '10px 16px', borderTop: i > 0 ? '1px solid var(--border)' : 'none',
                  background: i % 2 === 0 ? 'var(--bg-panel)' : 'var(--bg-card)',
                }}>
                  <span style={{ fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--text-primary)' }}>
                    {b.type}
                  </span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-secondary)' }}>
                    {b.sqft > 0 ? `${b.sqft.toLocaleString()} sf` : '--'}
                  </span>
                </div>
              ))}
            </div>
          )}
        </Section>

      </main>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 32, animation: 'fadeUp 0.4s ease both' }}>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: 2, textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 12, paddingBottom: 8, borderBottom: '1px solid var(--border)' }}>
        {title}
      </div>
      {children}
    </div>
  )
}

function Grid({ children }: { children: React.ReactNode }) {
  return <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: '12px 24px' }}>{children}</div>
}

function Field({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: 1.5, textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 2 }}>{label}</div>
      <div style={{ fontFamily: highlight ? 'var(--font-mono)' : 'var(--font-sans)', fontSize: 14, fontWeight: highlight ? 600 : 400, color: highlight ? 'var(--accent-green)' : 'var(--text-primary)' }}>{value}</div>
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
