import { useEffect, useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import BackButton from '../components/BackButton'
import Badge from '../components/Badge'
import PageShell from '../components/PageShell'
import Section from '../components/Section'
import { formatCurrencyCompact } from '../lib/format'
import type {
  LicenseRecord,
  MunicipalityLicenseResponse,
  MunicipalityProfile,
  TopDelinquentOwner,
} from '../types/api'

interface MuniStats {
  parcel_count: number
  total_assessed: number
  licenses: LicenseRecord[]
  top_owners: TopDelinquentOwner[]
}

export default function MunicipalityDetail() {
  const { name } = useParams<{ name: string }>()
  const navigate = useNavigate()
  const [muni, setMuni] = useState<MunicipalityProfile | null>(null)
  const [stats, setStats] = useState<MuniStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [statsError, setStatsError] = useState<string | null>(null)

  useEffect(() => {
    if (!name) return
    let cancelled = false

    async function loadMunicipality() {
      setLoading(true)
      setError(null)
      setStatsError(null)

      try {
        const muniResponse = await fetch(`/api/municipalities/${encodeURIComponent(name)}`)
        if (!muniResponse.ok) {
          throw new Error(`Municipality request failed (${muniResponse.status})`)
        }

        const muniData: MunicipalityProfile = await muniResponse.json()
        if (!cancelled) setMuni(muniData)
      } catch (loadError) {
        console.error('Failed to load municipality profile', loadError)
        if (!cancelled) {
          setMuni(null)
          setError('Unable to load municipality profile.')
          setLoading(false)
        }
        return
      }

      const muniName = decodeURIComponent(name)
      try {
        const [licensesResponse, ownersResponse] = await Promise.all([
          fetch(`/api/licenses?municipality=${encodeURIComponent(muniName)}&limit=50`),
          fetch(`/api/delinquent/top-owners?municipality=${encodeURIComponent(muniName)}&limit=10`),
        ])

        if (!licensesResponse.ok) {
          throw new Error(`License request failed (${licensesResponse.status})`)
        }
        if (!ownersResponse.ok) {
          throw new Error(`Top owners request failed (${ownersResponse.status})`)
        }

        const licData: MunicipalityLicenseResponse = await licensesResponse.json()
        const owners: TopDelinquentOwner[] = await ownersResponse.json()

        if (!cancelled) {
          setStats({
            parcel_count: 0,
            total_assessed: 0,
            licenses: licData.licenses || [],
            top_owners: owners || [],
          })
        }
      } catch (loadError) {
        console.error('Failed to load municipality supplemental data', loadError)
        if (!cancelled) {
          setStats(null)
          setStatsError('Supplemental municipality data is unavailable right now.')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    loadMunicipality()

    return () => {
      cancelled = true
    }
  }, [name])

  if (loading) return <PageShell><Loading /></PageShell>
  if (error) return <PageShell><div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--accent-red)' }}>{error}</div></PageShell>
  if (!muni) return <PageShell><div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--accent-red)' }}>Municipality not found: {name}</div></PageShell>

  const delinq = muni.delinquency || {}

  return (
    <PageShell>
      <BackButton onClick={() => navigate(-1)} />

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
        <StatCard label="Total Delinquent" value={formatCurrencyCompact(delinq.total_delinquent, { allowBillions: true })} color="var(--accent-gold)" />
        <StatCard label="Oldest Delinquency" value={delinq.oldest_delinquent_year?.toString() || 'None'} color="var(--text-primary)" />
      </div>

      {statsError && (
        <div style={{ marginBottom: 24, fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--accent-red)' }}>
          {statsError}
        </div>
      )}

      {/* Top Delinquent Owners */}
      {stats?.top_owners && stats.top_owners.length > 0 && (
        <Section title="Top Delinquent Owners">
          <div style={{ border: '1px solid var(--border)', borderRadius: 6, overflow: 'hidden' }}>
            {stats.top_owners.map((o, i: number) => (
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
                  {formatCurrencyCompact(o.total_owed, { allowBillions: true })}
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
            {stats.licenses.map((l, i: number) => (
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
    </PageShell>
  )
}

const linkStyle: React.CSSProperties = {
  fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--accent-blue)',
  textDecoration: 'none', padding: '6px 14px', border: '1px solid var(--border)',
  borderRadius: 4,
}

function Loading() {
  return <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--text-muted)', textAlign: 'center', padding: '80px 0' }}>Loading municipality...</div>
}

function StatCard({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)', borderRadius: 6, padding: '16px 20px' }}>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: 2, textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 6 }}>{label}</div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 24, fontWeight: 700, color }}>{value}</div>
    </div>
  )
}
