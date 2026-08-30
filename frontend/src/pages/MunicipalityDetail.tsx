import { useEffect, useState, type CSSProperties } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'

import BackButton from '../components/BackButton'
import Badge from '../components/Badge'
import PageShell from '../components/PageShell'
import Section from '../components/Section'
import { formatCurrencyCompact } from '../lib/format'
import type { MunicipalityProfile } from '../types/api'

function formatCompactCurrencyOrZero(value: number | null | undefined): string {
  if (value == null) return '--'
  if (value === 0) return '$0'
  return formatCurrencyCompact(value, { allowBillions: true })
}

export default function MunicipalityDetail() {
  const { name } = useParams<{ name: string }>()
  const navigate = useNavigate()
  const [municipality, setMunicipality] = useState<MunicipalityProfile | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!name) return
    const muniName = name
    let cancelled = false

    async function loadMunicipality() {
      setLoading(true)
      setError(null)

      try {
        const response = await fetch(`/api/municipalities/${encodeURIComponent(muniName)}`)
        if (!response.ok) {
          throw new Error(`Municipality request failed (${response.status})`)
        }

        const data: MunicipalityProfile = await response.json()
        if (!cancelled) {
          setMunicipality(data)
        }
      } catch (loadError) {
        console.error('Failed to load municipality profile', loadError)
        if (!cancelled) {
          setMunicipality(null)
          setError('Unable to load municipality profile.')
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
  if (!municipality) {
    return (
      <PageShell>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--accent-red)' }}>
          Municipality not found: {name}
        </div>
      </PageShell>
    )
  }

  const delinquency = municipality.delinquency
  const stats = municipality.stats
  const licenses = municipality.licenses ?? []

  return (
    <PageShell>
      <BackButton onClick={() => navigate(-1)} />

      <div style={{ animation: 'fadeUp 0.4s ease both', marginBottom: 32 }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, letterSpacing: 3, textTransform: 'uppercase', color: 'var(--accent-gold)', marginBottom: 8 }}>
          Municipality
        </div>
        <h1 style={{ fontFamily: 'var(--font-sans)', fontSize: 28, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>
          {municipality.name}
        </h1>
        <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
          {municipality.muni_type && <Badge color="var(--accent-blue)">{municipality.muni_type}</Badge>}
          {municipality.county && <Badge color="var(--accent-purple)">{municipality.county} County</Badge>}
        </div>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
          gap: 16,
          marginBottom: 32,
          animation: 'fadeUp 0.4s ease 0.1s both',
        }}
      >
        <StatCard label="Parcel Count" value={stats.parcel_count.toLocaleString()} color="var(--accent-blue)" />
        <StatCard label="Total Assessed" value={formatCompactCurrencyOrZero(stats.total_assessed)} color="var(--accent-green)" />
        <StatCard label="Delinquent Parcels" value={delinquency.delinquent_parcels.toLocaleString()} color={delinquency.delinquent_parcels > 0 ? 'var(--accent-red)' : 'var(--accent-green)'} />
        <StatCard label="Total Delinquent" value={formatCompactCurrencyOrZero(delinquency.total_delinquent)} color="var(--accent-gold)" />
        <StatCard label="Oldest Delinquency" value={delinquency.oldest_delinquent_year?.toString() || 'None'} color="var(--text-primary)" />
      </div>

      {licenses.length > 0 && (
        <Section title={`Liquor Licenses (${licenses.length})`}>
          <div style={{ border: '1px solid var(--border)', borderRadius: 6, overflow: 'hidden' }}>
            {licenses.map((license, index) => (
              <div
                key={`${license.premises_name ?? 'license'}-${license.premises_address ?? index}`}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '10px 16px',
                  borderTop: index > 0 ? '1px solid var(--border)' : 'none',
                  background: index % 2 === 0 ? 'var(--bg-panel)' : 'var(--bg-card)',
                }}
              >
                <div>
                  <div style={{ fontFamily: 'var(--font-sans)', fontSize: 14, fontWeight: 500, color: 'var(--text-primary)' }}>
                    {license.premises_name || license.licensee || 'Licensed premises'}
                  </div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}>
                    {license.premises_address || '--'}
                  </div>
                </div>
                <Badge color="var(--accent-blue)">{license.license_type}</Badge>
              </div>
            ))}
          </div>
        </Section>
      )}

      <Section title="Explore">
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <Link to={`/search?q=properties+in+${encodeURIComponent(municipality.name)}`} style={linkStyle}>Search Properties</Link>
          <Link to={`/search?q=vacant+land+in+${encodeURIComponent(municipality.name)}`} style={linkStyle}>Vacant Land</Link>
          <Link to="/map" style={linkStyle}>View on Map</Link>
        </div>
      </Section>
    </PageShell>
  )
}

const linkStyle: CSSProperties = {
  fontFamily: 'var(--font-mono)',
  fontSize: 11,
  color: 'var(--accent-blue)',
  textDecoration: 'none',
  padding: '6px 14px',
  border: '1px solid var(--border)',
  borderRadius: 4,
}

function Loading() {
  return (
    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--text-muted)', textAlign: 'center', padding: '80px 0' }}>
      Loading municipality...
    </div>
  )
}

function StatCard({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)', borderRadius: 6, padding: '16px 20px' }}>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: 2, textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 6 }}>
        {label}
      </div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 24, fontWeight: 700, color }}>{value}</div>
    </div>
  )
}
