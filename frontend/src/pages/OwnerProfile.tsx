import { useEffect, useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'

import BackButton from '../components/BackButton'
import Badge from '../components/Badge'
import PageShell from '../components/PageShell'
import Section from '../components/Section'
import { formatCurrencyCompact } from '../lib/format'
import { getPropertyClassLabel } from '../lib/propertyLabels'
import type { OwnerProfileResponse } from '../types/api'

function formatEntityTypeLabel(entityType: string | null | undefined): string {
  if (!entityType) return 'Unknown'
  const normalized = entityType.toLowerCase()
  if (normalized === 'business') return 'Business'
  if (normalized === 'person' || normalized === 'individual') return 'Person'
  return normalized.replace(/_/g, ' ')
}

export default function OwnerProfile() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [data, setData] = useState<OwnerProfileResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!id) return
    setLoading(true)
    setError(null)
    fetch(`/api/owners/${id}`)
      .then(r => { if (!r.ok) throw new Error(`${r.status}`); return r.json() })
      .then((ownerData) => {
        setData(ownerData)
      })
      .catch((loadError) => {
        console.error('Failed to load owner profile', loadError)
        setData(null)
        setError('Unable to load owner profile.')
      })
      .finally(() => setLoading(false))
  }, [id])

  if (loading) {
    return (
      <PageShell maxWidth={1000}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--text-muted)', textAlign: 'center', padding: '80px 0' }}>
          Loading owner profile...
        </div>
      </PageShell>
    )
  }

  if (error) {
    return (
      <PageShell maxWidth={1000}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--accent-red)' }}>{error}</div>
      </PageShell>
    )
  }

  if (!data) {
    return (
      <PageShell maxWidth={1000}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--accent-red)' }}>Owner not found</div>
      </PageShell>
    )
  }

  const owner = data.owner
  const portfolio = data.portfolio
  const delinq = data.delinquency
  const licenses = data.licenses

  return (
    <PageShell maxWidth={1000}>
      <BackButton onClick={() => navigate(-1)} />

      <div style={{ animation: 'fadeUp 0.4s ease both', marginBottom: 32 }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, letterSpacing: 3, textTransform: 'uppercase', color: 'var(--accent-gold)', marginBottom: 8 }}>Owner Profile</div>
        <h1 style={{ fontFamily: 'var(--font-sans)', fontSize: 28, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 8 }}>{owner.canonical_name}</h1>
        <div style={{ display: 'flex', gap: 8 }}>
          <Badge color="var(--accent-blue)">{formatEntityTypeLabel(owner.entity_type)}</Badge>
          {owner.verification_status && (
            <Badge color={owner.verification_status === 'verified' ? 'var(--accent-green)' : 'var(--accent-gold)'}>
              {owner.verification_status === 'verified' ? 'Verified Entity' : 'Tentative Entity'}
            </Badge>
          )}
          {delinq.total_owed > 0 && <Badge color="var(--accent-red)">Tax Delinquent — {formatCurrencyCompact(delinq.total_owed, { allowBillions: true })}</Badge>}
          {licenses.length > 0 && <Badge color="var(--accent-green)">{licenses.length} Liquor License{licenses.length > 1 ? 's' : ''}</Badge>}
        </div>
      </div>

      {(owner.aliases && owner.aliases.length > 0) || owner.verification_reasoning ? (
        <Section title="Entity Context">
          {owner.aliases && owner.aliases.length > 0 && (
            <div style={{ marginBottom: owner.verification_reasoning ? 14 : 0 }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: 1.5, textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 6 }}>Known Aliases</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {owner.aliases.map((alias) => (
                  <Badge key={alias} color="var(--accent-cyan)">{alias}</Badge>
                ))}
              </div>
            </div>
          )}
          {owner.verification_reasoning && (
            <div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: 1.5, textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 6 }}>Why These Records Are Linked</div>
              <div style={{ fontFamily: 'var(--font-sans)', fontSize: 14, lineHeight: 1.6, color: 'var(--text-secondary)' }}>
                {owner.verification_reasoning}
              </div>
            </div>
          )}
        </Section>
      ) : null}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 32, animation: 'fadeUp 0.4s ease 0.1s both' }}>
        <StatCard label="Properties" value={portfolio.parcel_count.toLocaleString()} color="var(--accent-blue)" />
        <StatCard label="Total Assessed" value={formatCurrencyCompact(portfolio.total_assessed, { allowBillions: true })} color="var(--accent-green)" />
        <StatCard label="Delinquent" value={delinq.delinquent_parcels.toLocaleString()} color={delinq.delinquent_parcels > 0 ? 'var(--accent-red)' : 'var(--text-muted)'} />
        <StatCard label="Total Owed" value={formatCurrencyCompact(delinq.total_owed, { allowBillions: true })} color="var(--accent-gold)" />
      </div>

      <Section title={`Properties (${portfolio.parcel_count})`}>
        <div style={{ border: '1px solid var(--border)', borderRadius: 6, overflow: 'hidden' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '140px 1fr 100px 100px 80px', padding: '8px 16px', background: 'var(--bg-card)', fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: 1.5, textTransform: 'uppercase', color: 'var(--text-muted)' }}>
            <div>PIDN</div><div>Address</div><div style={{ textAlign: 'right' }}>Assessed</div><div style={{ textAlign: 'right' }}>Sale Price</div><div style={{ textAlign: 'right' }}>Class</div>
          </div>
          {portfolio.parcels.map((p, i: number) => (
            <Link
              key={p.pidn}
              to={`/property/${p.pidn}`}
              style={{ textDecoration: 'none', color: 'inherit', display: 'grid', gridTemplateColumns: '140px 1fr 100px 100px 80px', padding: '10px 16px', borderTop: '1px solid var(--border)', background: i % 2 === 0 ? 'var(--bg-panel)' : 'var(--bg-card)', transition: 'background 0.15s' }}
              onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'var(--bg-card-hover)' }}
              onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = i % 2 === 0 ? 'var(--bg-panel)' : 'var(--bg-card)' }}
            >
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--accent-blue)' }}>{p.pidn}</div>
              <div style={{ fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--text-primary)' }}>{p.propadr || '--'}</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-secondary)', textAlign: 'right' }}>{formatCurrencyCompact(p.aprtotal, { allowBillions: true })}</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-secondary)', textAlign: 'right' }}>{formatCurrencyCompact(p.price, { allowBillions: true })}</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', textAlign: 'right' }}>{getPropertyClassLabel(p.class)}</div>
            </Link>
          ))}
        </div>
      </Section>

      {delinq.records.length > 0 && (
        <Section title={`Tax Delinquency (${formatCurrencyCompact(delinq.total_owed, { allowBillions: true })} across ${delinq.delinquent_parcels} parcel${delinq.delinquent_parcels > 1 ? 's' : ''})`}>
          <div style={{ border: '1px solid var(--border)', borderRadius: 6, overflow: 'hidden' }}>
            {delinq.records.map((r, i: number) => (
              <div key={i} style={{ display: 'grid', gridTemplateColumns: '140px 1fr 80px 80px 120px', padding: '8px 16px', borderTop: i > 0 ? '1px solid var(--border)' : 'none', background: i % 2 === 0 ? 'var(--bg-panel)' : 'var(--bg-card)', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-secondary)' }}>
                <div style={{ color: 'var(--accent-blue)' }}>{r.pidn}</div>
                <div>{r.property_address}</div>
                <div>{r.tax_year}</div>
                <div>{r.authority_name}</div>
                <div style={{ textAlign: 'right', color: 'var(--accent-red)', fontWeight: 600 }}>{formatCurrencyCompact(r.total, { allowBillions: true })}</div>
              </div>
            ))}
          </div>
        </Section>
      )}

      {licenses.length > 0 && (
        <Section title={`Linked Liquor Licenses (${licenses.length})`}>
          <div style={{ border: '1px solid var(--border)', borderRadius: 6, overflow: 'hidden' }}>
            {licenses.map((l, i: number) => (
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
    </PageShell>
  )
}

function StatCard({ label, value, color }: { label: string; value: string; color: string }) {
  return <div style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)', borderRadius: 6, padding: '14px 18px' }}><div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: 2, textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 4 }}>{label}</div><div style={{ fontFamily: 'var(--font-mono)', fontSize: 22, fontWeight: 700, color }}>{value}</div></div>
}
