import { useEffect, useState } from 'react'
import { useParams, Link, useLocation, useNavigate } from 'react-router-dom'

import BackButton from '../components/BackButton'
import Badge from '../components/Badge'
import EvidencePanel, { CitedText } from '../components/EvidencePanel'
import IntelligenceEventCard from '../components/IntelligenceEventCard'
import PageShell from '../components/PageShell'
import Section from '../components/Section'
import { formatCurrencyCompact } from '../lib/format'
import { getPropertyClassLabel } from '../lib/propertyLabels'
import { useFetchJson } from '../lib/useFetchJson'
import { isEntityWatched, toggleEntityWatch } from '../lib/watchlist'
import type { IntelligenceFeedResponse, OwnerProfileResponse } from '../types/api'

const RECOMMENDATION_COLORS: Record<string, string> = {
  investigate: 'var(--accent-blue)',
  watch: 'var(--accent-cyan)',
  insufficient_evidence: 'var(--text-muted)',
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

      <div style={{ marginBottom: 32 }}>
        <div className="record-eyebrow">
          {entityView ? 'Entity case file' : 'Owner profile'}
        </div>
        <h1 className="page-title">{owner.canonical_name}</h1>
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
            className="watch-button"
            aria-pressed={watched}
          >
            {watched ? '★ Watching entity' : '☆ Watch entity'}
          </button>
        </div>
      </div>

      {(owner.aliases && owner.aliases.length > 0) || owner.verification_reasoning || data.verification_evidence.length > 0 ? (
        <Section title="Entity Context">
          {owner.aliases && owner.aliases.length > 0 && (
            <div style={{ marginBottom: owner.verification_reasoning ? 14 : 0 }}>
              <div className="record-label">Known Aliases</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {owner.aliases.map((alias) => (
                  <Badge key={alias} color="var(--accent-cyan)">{alias}</Badge>
                ))}
              </div>
            </div>
          )}
          {owner.verification_reasoning && (
            <div>
              <div className="record-label">Why These Records Are Linked</div>
              <div style={{ fontFamily: 'var(--font-sans)', fontSize: 14, lineHeight: 1.6, color: 'var(--text-secondary)' }}>
                <CitedText text={owner.verification_reasoning} evidence={data.verification_evidence} />
              </div>
            </div>
          )}
          {data.verification_evidence.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <EvidencePanel
                items={data.verification_evidence}
                title="Records used to verify this entity"
                intro="These governed record identifiers are the factual inputs to the entity-linking decision."
              />
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
                  {evidence && <div style={{ marginTop: 8, fontFamily: 'var(--font-sans)', fontSize: 13, lineHeight: 1.6, color: 'var(--text-secondary)' }}><CitedText text={evidence} evidence={data.verification_evidence} /></div>}
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
              <div className="record-label">Key Pattern</div>
              <div style={{ fontFamily: 'var(--font-sans)', fontSize: 14, lineHeight: 1.6, color: 'var(--text-primary)', fontWeight: 500 }}>
                <CitedText text={data.brief.key_pattern} evidence={data.brief.citation_evidence ?? []} />
              </div>
            </div>
          )}
          <div style={{ fontFamily: 'var(--font-sans)', fontSize: 14, lineHeight: 1.7, color: 'var(--text-secondary)', whiteSpace: 'pre-line', marginBottom: 12 }}>
            <CitedText text={data.brief.brief_text} evidence={data.brief.citation_evidence ?? []} />
          </div>
          {data.brief.top_risk && (
            <div style={{ marginBottom: 12 }}>
              <div className="record-label">Top Risk</div>
              <div style={{ fontFamily: 'var(--font-sans)', fontSize: 13, lineHeight: 1.6, color: 'var(--text-secondary)' }}><CitedText text={data.brief.top_risk} evidence={data.brief.citation_evidence ?? []} /></div>
            </div>
          )}
          {(data.brief.citation_evidence?.length ?? 0) > 0 && (
            <div style={{ marginBottom: 12 }}>
              <EvidencePanel
                items={data.brief.citation_evidence}
                title="Verify the portfolio brief"
                intro="Inline references resolve to the validated signals and exact parcels used in this synthesis."
              />
            </div>
          )}
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)' }}>
            {data.brief.confidence !== null ? `confidence ${(data.brief.confidence * 100).toFixed(0)}% · ` : ''}
            {data.brief.model_version ?? 'model unknown'}
            {data.brief.generated_at ? ` · ${new Date(data.brief.generated_at).toLocaleDateString()}` : ''}
          </div>
        </Section>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: 12, marginBottom: 32 }}>
        <StatCard label="Properties" value={portfolio.parcel_count.toLocaleString()} color="var(--accent-blue)" />
        <StatCard label="Total Assessed" value={formatCurrencyCompact(portfolio.total_assessed, { allowBillions: true })} color="var(--accent-green)" />
        {delinq.detail_available !== false && (
          <>
            <StatCard label="Delinquent" value={delinq.delinquent_parcels.toLocaleString()} color={delinq.delinquent_parcels > 0 ? 'var(--accent-red)' : 'var(--text-muted)'} />
            <StatCard label="Total Owed" value={formatCurrencyCompact(delinq.total_owed, { allowBillions: true })} color="var(--accent-gold)" />
          </>
        )}
      </div>
      {delinq.detail_available === false && (
        <div style={{ marginTop: -20, marginBottom: 32, fontSize: 13, color: 'var(--text-muted)' }}>
          Exact tax-claim balances for this entity are withheld under the current source-use policy. Parcel-level delinquency signals remain visible on each property report.
        </div>
      )}

      <Section title={`Properties (${portfolio.parcel_count})`}>
        <div className="data-table">
          <div className="data-table-head" style={{ gridTemplateColumns: '140px 1fr 110px 110px 90px', minWidth: 580 }}>
            <div>PIDN</div><div>Address</div><div className="cell-right">Assessed</div><div className="cell-right">Sale Price</div><div className="cell-right">Class</div>
          </div>
          {portfolio.parcels.map((p) => (
            <Link
              key={p.pidn}
              to={`/property/${p.pidn}`}
              className="data-table-row"
              style={{ gridTemplateColumns: '140px 1fr 110px 110px 90px', minWidth: 580 }}
            >
              <div className="cell-id">{p.pidn}</div>
              <div className="cell-strong">{p.propadr || '--'}</div>
              <div className="cell-right">{formatCurrencyCompact(p.aprtotal, { allowBillions: true })}</div>
              <div className="cell-right">{formatCurrencyCompact(p.price, { allowBillions: true })}</div>
              <div className="cell-right cell-muted">{getPropertyClassLabel(p.class)}</div>
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
  return (
    <div className="stat-tile" style={{ '--stat-color': color } as React.CSSProperties}>
      <div className="field-label">{label}</div>
      <div className="stat-tile-value">{value}</div>
    </div>
  )
}
