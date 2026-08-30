import { useEffect, useState } from 'react'
import { useParams, Link, useLocation, useNavigate } from 'react-router-dom'

import BackButton from '../components/BackButton'
import Badge from '../components/Badge'
import IntelligenceEventCard from '../components/IntelligenceEventCard'
import PageShell from '../components/PageShell'
import Section from '../components/Section'
import { formatCurrencyCompact } from '../lib/format'
import { getPropertyClassLabel } from '../lib/propertyLabels'
import { useFetchJson } from '../lib/useFetchJson'
import { isEntityWatched, toggleEntityWatch } from '../lib/watchlist'
import type { IntelligenceFeedResponse, OwnerProfileResponse } from '../types/api'

const RECOMMENDATION_COLORS: Record<string, string> = {
  pursue_acquisition: 'var(--accent-green)',
  compete: 'var(--accent-gold)',
  monitor: 'var(--accent-cyan)',
  none: 'var(--text-muted)',
}

function formatBriefLabel(value: string | null | undefined): string {
  if (!value) return '--'
  return value.replace(/_/g, ' ')
}

function formatEntityTypeLabel(entityType: string | null | undefined): string {
  if (!entityType) return 'Unknown'
  const normalized = entityType.toLowerCase()
  if (normalized === 'business') return 'Business'
  if (normalized === 'person' || normalized === 'individual') return 'Person'
  return normalized.replace(/_/g, ' ')
}

export default function OwnerProfile() {
  const { id } = useParams<{ id: string }>()
  const location = useLocation()
  const navigate = useNavigate()
  const entityView = location.pathname.startsWith('/entity/')
  const { data, error: fetchError, loading } = useFetchJson<OwnerProfileResponse>(
    id ? `/api/${entityView ? 'entities' : 'owners'}/${encodeURIComponent(id)}` : null,
  )
  const intelligence = useFetchJson<IntelligenceFeedResponse>(
    data?.owner.owner_id
      ? `/api/feed?entity_ids=${data.owner.owner_id}&since_days=3650&limit=20&sort=latest`
      : null,
  )
  const [, setWatchRevision] = useState(0)

  useEffect(() => {
    const refresh = () => setWatchRevision((value) => value + 1)
    window.addEventListener('countyiq-watchlist-changed', refresh)
    return () => window.removeEventListener('countyiq-watchlist-changed', refresh)
  }, [])
  const error = fetchError ? 'Unable to load owner profile.' : null

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
  const watched = isEntityWatched(owner.owner_id)

  return (
    <PageShell maxWidth={1000}>
      <BackButton onClick={() => navigate(-1)} />

      <div style={{ animation: 'fadeUp 0.4s ease both', marginBottom: 32 }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, letterSpacing: 3, textTransform: 'uppercase', color: 'var(--accent-gold)', marginBottom: 8 }}>
          {entityView ? 'Entity case file' : 'Owner profile'}
        </div>
        <h1 style={{ fontFamily: 'var(--font-sans)', fontSize: 28, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 8 }}>{owner.canonical_name}</h1>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
          <Badge color="var(--accent-blue)">{formatEntityTypeLabel(owner.entity_type)}</Badge>
          {owner.verification_status && (
            <Badge color={owner.verification_status === 'verified' ? 'var(--accent-green)' : 'var(--accent-gold)'}>
              {owner.verification_status === 'verified' ? 'Verified Entity' : 'Tentative Entity'}
            </Badge>
          )}
          {delinq.total_owed > 0 && <Badge color="var(--accent-red)">Tax Delinquent — {formatCurrencyCompact(delinq.total_owed, { allowBillions: true })}</Badge>}
          {licenses.length > 0 && <Badge color="var(--accent-green)">{licenses.length} Liquor License{licenses.length > 1 ? 's' : ''}</Badge>}
          <button
            onClick={() => {
              toggleEntityWatch({ id: owner.owner_id, name: owner.canonical_name })
              setWatchRevision((value) => value + 1)
            }}
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              color: watched ? 'var(--accent-gold)' : 'var(--accent-blue)',
              background: 'transparent',
              border: `1px solid ${watched ? 'var(--accent-gold)' : 'var(--border)'}`,
              borderRadius: 4,
              padding: '5px 10px',
              cursor: 'pointer',
            }}
          >
            {watched ? '★ Watching entity' : '☆ Watch entity'}
          </button>
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

      {data.relationships.length > 0 && (
        <Section title={`Known relationships (${data.relationships.length})`}>
          <div style={{ display: 'grid', gap: 10 }}>
            {data.relationships.map((relationship, index) => {
              const name = String(relationship.related_canonical_name ?? relationship.related_entity ?? 'Related entity')
              const relationshipType = String(relationship.relationship_type ?? 'related').replace(/_/g, ' ')
              const evidence = relationship.evidence ? String(relationship.evidence) : null
              const relatedId = typeof relationship.related_owner_id === 'number' ? relationship.related_owner_id : null
              return (
                <div key={`${name}-${relationshipType}-${index}`} style={{ border: '1px solid var(--border)', borderRadius: 6, padding: '12px 14px', background: 'var(--bg-panel)' }}>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
                    <Badge color="var(--accent-purple)">{relationshipType}</Badge>
                    {relatedId ? (
                      <Link to={`/entity/${relatedId}`} style={{ fontFamily: 'var(--font-sans)', fontSize: 14, fontWeight: 600, color: 'var(--accent-green)' }}>
                        {name} →
                      </Link>
                    ) : (
                      <span style={{ fontFamily: 'var(--font-sans)', fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>{name}</span>
                    )}
                  </div>
                  {evidence && <div style={{ marginTop: 8, fontFamily: 'var(--font-sans)', fontSize: 13, lineHeight: 1.6, color: 'var(--text-secondary)' }}>{evidence}</div>}
                </div>
              )
            })}
          </div>
        </Section>
      )}

      <Section title="Recent intelligence">
        {intelligence.loading && <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)' }}>Loading related changes…</div>}
        {intelligence.error && <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--accent-red)' }}>{intelligence.error}</div>}
        {!intelligence.loading && !intelligence.error && (intelligence.data?.events.length ?? 0) === 0 && (
          <div style={{ fontFamily: 'var(--font-sans)', fontSize: 14, lineHeight: 1.6, color: 'var(--text-secondary)' }}>
            No parcel or municipal events are linked to this entity yet. That absence is explicit; CountyIQ does not invent a narrative when the source record is thin.
          </div>
        )}
        {(intelligence.data?.events.length ?? 0) > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {intelligence.data!.events.map((event) => <IntelligenceEventCard key={event.event_key} event={event} />)}
          </div>
        )}
      </Section>

      {data.brief && (
        <Section title="Portfolio Intelligence">
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 14 }}>
            <Badge color={RECOMMENDATION_COLORS[data.brief.recommendation ?? 'none'] ?? 'var(--text-muted)'}>
              {formatBriefLabel(data.brief.recommendation)}
            </Badge>
            {data.brief.portfolio_strategy && (
              <Badge color="var(--accent-blue)">{formatBriefLabel(data.brief.portfolio_strategy)}</Badge>
            )}
            {data.brief.urgency && data.brief.urgency !== 'none' && (
              <Badge color="var(--accent-gold)">{formatBriefLabel(data.brief.urgency)}</Badge>
            )}
            {data.brief.evidence_strength && (
              <Badge color="var(--accent-cyan)">evidence: {data.brief.evidence_strength}</Badge>
            )}
          </div>
          {data.brief.key_pattern && (
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: 1.5, textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 6 }}>Key Pattern</div>
              <div style={{ fontFamily: 'var(--font-sans)', fontSize: 14, lineHeight: 1.6, color: 'var(--text-primary)', fontWeight: 500 }}>
                {data.brief.key_pattern}
              </div>
            </div>
          )}
          <div style={{ fontFamily: 'var(--font-sans)', fontSize: 14, lineHeight: 1.7, color: 'var(--text-secondary)', whiteSpace: 'pre-line', marginBottom: 12 }}>
            {data.brief.brief_text}
          </div>
          {data.brief.top_risk && (
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: 1.5, textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 6 }}>Top Risk</div>
              <div style={{ fontFamily: 'var(--font-sans)', fontSize: 13, lineHeight: 1.6, color: 'var(--text-secondary)' }}>{data.brief.top_risk}</div>
            </div>
          )}
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)' }}>
            {data.brief.confidence !== null ? `confidence ${(data.brief.confidence * 100).toFixed(0)}% · ` : ''}
            {data.brief.model_version ?? 'model unknown'}
            {data.brief.generated_at ? ` · ${new Date(data.brief.generated_at).toLocaleDateString()}` : ''}
          </div>
        </Section>
      )}

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
