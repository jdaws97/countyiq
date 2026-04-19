import { useEffect, useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import BackButton from '../components/BackButton'
import Badge from '../components/Badge'
import NarrativeCard from '../components/NarrativeCard'
import PageShell from '../components/PageShell'
import Section from '../components/Section'
import { formatCurrency, formatLabel, formatShortDate } from '../lib/format'
import { getPropertyClassLabel, getSchoolDistrictLabel } from '../lib/propertyLabels'
import type {
  DevelopmentSignal,
  DevelopmentSignalEvidence,
  LinkedProceeding,
  PropertyReport,
  StructureBuilding,
  TaxDelinquencyRecord,
} from '../types/api'

function getSignalWeight(signal: DevelopmentSignal): number {
  return typeof signal.weight === 'number' ? signal.weight : 0
}

function getSignalEvidence(signal: DevelopmentSignal): DevelopmentSignalEvidence {
  if (signal.evidence && typeof signal.evidence === 'object') {
    return signal.evidence
  }
  return signal
}

function getString(value: string | number | boolean | null | undefined): string | null {
  return typeof value === 'string' && value.length > 0 ? value : null
}

function getNumber(value: string | number | boolean | null | undefined): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.length > 0) {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

function formatSignalDetail(key: string, evidence: DevelopmentSignalEvidence): string {
  if (key === 'active_subdivision') {
    return getString(evidence['plan_title']) ?? ''
  }
  if (key === 'ecodev_candidate') {
    const underutilized = getNumber(evidence['percent_underutilized'])
    return underutilized == null ? '' : `${underutilized}% underutilized`
  }
  if (key === 'zoning_mismatch') {
    const current = getString(evidence['current_zname']) ?? getString(evidence['current_ztype']) ?? '?'
    const future = getString(evidence['future_lu']) ?? '?'
    return `${current} -> ${future}`
  }
  if (key === 'ownership_change') {
    const price = getNumber(evidence['price'])
    return price == null ? '' : `Sold for $${price.toLocaleString()}`
  }
  if (key === 'tax_distress') {
    const totalOwed = getNumber(evidence['total_owed'])
    return totalOwed == null ? '' : `$${totalOwed.toLocaleString()} owed`
  }
  if (key === 'penndot_project') {
    return getString(evidence['project_name']) ?? ''
  }
  if (key === 'flood_zone') {
    const zone = getString(evidence['fld_zone'])
    return zone ? `Zone ${zone}` : ''
  }
  if (key === 'growth_area') {
    const type = getString(evidence['ga_type'])
    if (type === 'PGA') return 'Primary Growth Area'
    if (type) return 'Secondary Growth Area'
  }
  if (key === 'cdbg_investment') {
    return getString(evidence['name']) ?? getString(evidence['address']) ?? 'nearby'
  }
  return ''
}

function getValidationStatus(signal: DevelopmentSignal, evidence: DevelopmentSignalEvidence): string | null {
  return getString(signal.validation_status) ?? getString(evidence['validation_status'])
}

function getAdjustedSignificance(signal: DevelopmentSignal, evidence: DevelopmentSignalEvidence): string | null {
  return getString(signal.adjusted_significance) ?? getString(evidence['adjusted_significance'])
}

function getValidationReasoning(signal: DevelopmentSignal, evidence: DevelopmentSignalEvidence): string | null {
  return getString(signal.validation_reasoning) ?? getString(evidence['validation_reasoning'])
}

function validationBadgeColor(status: string): string {
  if (status === 'upgraded' || status === 'confirmed') return 'var(--accent-green)'
  if (status === 'stale' || status === 'irrelevant') return 'var(--accent-red)'
  if (status === 'downgraded') return 'var(--accent-gold)'
  return 'var(--accent-blue)'
}

function significanceBadgeColor(significance: string): string {
  if (significance === 'high') return 'var(--accent-green)'
  if (significance === 'medium') return 'var(--accent-gold)'
  if (significance === 'low' || significance === 'none') return 'var(--text-muted)'
  return 'var(--accent-blue)'
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

  if (loading) return <PageShell><div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--text-muted)', textAlign: 'center', padding: '80px 0' }}>Loading property...</div></PageShell>
  if (error || !report) return <PageShell><div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--accent-red)' }}>Property not found: {pidn}</div></PageShell>

  const p = report.parcel
  const tax = report.tax_delinquency
  const flood = report.flood_zone
  const structures = report.structures
  const brief = report.parcel_brief
  const narratives = report.related_narratives
  const intelligence = report.intelligence_summary
  const proceedings = report.linked_proceedings ?? []

  return (
    <PageShell>
        {/* Back + Actions */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
          <BackButton onClick={() => navigate(-1)} marginBottom={0} />
          {p.lat && p.lng && (
            <Link to={`/map?lat=${p.lat}&lng=${p.lng}&zoom=18&highlight=${p.pidn}`} style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--accent-blue)', textDecoration: 'none', padding: '4px 10px', border: '1px solid var(--border)', borderRadius: 4 }}>View on Map</Link>
          )}
        </div>

        {/* Header */}
        <div style={{ animation: 'fadeUp 0.4s ease both', marginBottom: 32 }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, letterSpacing: 3, textTransform: 'uppercase', color: 'var(--accent-gold)', marginBottom: 8 }}>Property Report</div>
          <h1 style={{ fontFamily: 'var(--font-sans)', fontSize: 28, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>{p.owner_full || 'Unknown Owner'}</h1>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 14, color: 'var(--text-secondary)' }}>{p.propadr || 'No address'}</div>
          <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
            {p.class && <Badge color="var(--accent-blue)">{getPropertyClassLabel(p.class)}</Badge>}
            {p.school_dis && <Badge color="var(--accent-purple)">{getSchoolDistrictLabel(p.school_dis)}</Badge>}
            {tax.is_delinquent && <Badge color="var(--accent-red)">Tax Delinquent</Badge>}
            {flood.in_flood_zone && <Badge color="var(--accent-cyan)">Flood Zone {flood.zone}</Badge>}
            {structures.likely_vacant && <Badge color="var(--accent-gold)">Vacant</Badge>}
          </div>
        </div>

        {/* Assessment & Sale */}
        <Section title="Assessment & Sale">
          <Grid>
            <Field label="Assessed Total" value={formatCurrency(p.aprtotal)} highlight />
            <Field label="Acres" value={p.acres ? Number(p.acres).toFixed(2) : '--'} />
            <Field label="Sale Date" value={p.saledt || '--'} />
            <Field label="Sale Price" value={formatCurrency(p.price)} highlight />
            {p.prev_price && <Field label="Previous Price" value={formatCurrency(p.prev_price)} />}
            {p.aprland && <Field label="Land Value" value={formatCurrency(p.aprland)} />}
            {p.aprbldg && <Field label="Building Value" value={formatCurrency(p.aprbldg)} />}
          </Grid>
        </Section>

        {/* Property Details */}
        <Section title="Property Details">
          <Grid>
            <Field label="PIDN" value={p.pidn} />
            <Field label="Class" value={getPropertyClassLabel(p.class) || '--'} />
            <Field label="School District" value={getSchoolDistrictLabel(p.school_dis) || '--'} />
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
                <Badge color="var(--accent-red)">Delinquent — {formatCurrency(tax.total_owed)}</Badge>
              </div>
              <div style={{ border: '1px solid var(--border)', borderRadius: 6, overflow: 'hidden' }}>
                <div style={{ display: 'grid', gridTemplateColumns: '80px 120px 1fr 120px', padding: '8px 16px', background: 'var(--bg-card)', fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: 1.5, textTransform: 'uppercase', color: 'var(--text-muted)' }}>
                  <div>Year</div><div>Authority</div><div></div><div style={{ textAlign: 'right' }}>Amount</div>
                </div>
                {tax.records.map((rec: TaxDelinquencyRecord, i: number) => (
                  <div key={i} style={{ display: 'grid', gridTemplateColumns: '80px 120px 1fr 120px', padding: '8px 16px', borderTop: '1px solid var(--border)', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-secondary)' }}>
                    <div>{rec.tax_year}</div>
                    <div>{rec.authority_name}</div>
                    <div></div>
                    <div style={{ textAlign: 'right', color: 'var(--accent-red)', fontWeight: 600 }}>{formatCurrency(rec.total)}</div>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <Badge color="var(--accent-green)">Current — No Delinquent Taxes</Badge>
          )}
        </Section>

        {proceedings.length > 0 && (
          <Section title="Proceedings & Hearings">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {proceedings.map((pr) => (
                <ProceedingRow key={pr.proceeding_id} proceeding={pr} />
              ))}
            </div>
          </Section>
        )}

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
              {structures.buildings.map((b: StructureBuilding, i: number) => (
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

        {intelligence?.cross_signal_insight && (
          <Section title="Cross-Signal Insight">
            <div style={{
              borderLeft: '2px solid var(--accent-gold)',
              paddingLeft: 14,
              fontFamily: 'var(--font-sans)',
              fontSize: 14,
              lineHeight: 1.7,
              color: 'var(--text-secondary)',
            }}>
              {intelligence.cross_signal_insight}
              <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
                {intelligence.signals_validated_count ? (
                  <Badge color="var(--accent-blue)">
                    {intelligence.signals_validated_count} signal{intelligence.signals_validated_count === 1 ? '' : 's'} validated
                  </Badge>
                ) : null}
                {intelligence.last_run_at && (
                  <Badge color="var(--accent-cyan)">Validated {formatShortDate(intelligence.last_run_at)}</Badge>
                )}
              </div>
            </div>
          </Section>
        )}

        {brief && (
          <Section title="Intelligence Brief">
            <div style={{
              background: 'var(--bg-card)',
              border: '1px solid var(--border)',
              borderRadius: 8,
              padding: 18,
            }}>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 14 }}>
                {brief.assessment && (
                  <Badge color={brief.assessment === 'high_priority' ? 'var(--accent-red)' : brief.assessment === 'monitor' ? 'var(--accent-gold)' : 'var(--accent-green)'}>
                    {brief.assessment.replace(/_/g, ' ')}
                  </Badge>
                )}
                {brief.signal_count != null && (
                  <Badge color="var(--accent-blue)">{brief.signal_count} validated signals</Badge>
                )}
                {brief.generated_at && (
                  <Badge color="var(--accent-cyan)">Generated {formatShortDate(brief.generated_at)}</Badge>
                )}
              </div>

              <div style={{ fontFamily: 'var(--font-sans)', fontSize: 15, lineHeight: 1.7, color: 'var(--text-primary)', marginBottom: brief.assessment_reasoning || brief.key_questions.length > 0 || brief.citations.length > 0 ? 16 : 0 }}>
                {brief.brief_text}
              </div>

              {brief.assessment_reasoning && (
                <div style={{ marginBottom: brief.key_questions.length > 0 || brief.citations.length > 0 ? 16 : 0 }}>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: 1.5, textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 6 }}>
                    Assessment Rationale
                  </div>
                  <div style={{ fontFamily: 'var(--font-sans)', fontSize: 14, lineHeight: 1.6, color: 'var(--text-secondary)' }}>
                    {brief.assessment_reasoning}
                  </div>
                </div>
              )}

              {brief.key_questions.length > 0 && (
                <div style={{ marginBottom: brief.citations.length > 0 ? 16 : 0 }}>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: 1.5, textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 6 }}>
                    Key Questions
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {brief.key_questions.map((question) => (
                      <div key={question} style={{ fontFamily: 'var(--font-sans)', fontSize: 14, color: 'var(--text-secondary)' }}>
                        {question}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {brief.citations.length > 0 && (
                <div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: 1.5, textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 6 }}>
                    Citations
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                    {brief.citations.map((citation) => (
                      <Badge key={citation} color="var(--accent-cyan)">{citation}</Badge>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </Section>
        )}

        {/* Development Momentum */}
        {report?.development_momentum && (
          <div style={{
            background: 'var(--bg-card)', borderRadius: 8, padding: 16, marginTop: 16,
            border: `1px solid ${report.development_momentum.eligible ? '#22c55e' : 'var(--text-secondary)'}40`,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
              <span style={{
                fontSize: 28, fontWeight: 700, fontFamily: 'var(--font-mono)',
                color: report.development_momentum.eligible
                  ? (report.development_momentum.score >= 60 ? '#22c55e' : report.development_momentum.score >= 40 ? '#eab308' : '#06b6d4')
                  : 'var(--text-secondary)',
              }}>
                {report.development_momentum.score}
              </span>
              <div>
                <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Development Momentum</div>
                <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                  {report.development_momentum.eligible
                    ? report.development_momentum.top_signal || 'No top signal'
                    : `Ineligible: ${(report.development_momentum.exclusion_reasons || []).join(', ')}`}
                </div>
              </div>
            </div>
            {report.development_momentum.eligible && report.development_momentum.signals && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {Object.entries(report.development_momentum.signals)
                  .filter(([key]) => !['conservation_easement', 'ag_security'].includes(key))
                  .sort(([, a], [, b]) => getSignalWeight(b) - getSignalWeight(a))
                  .map(([key, sig]) => {
                    const w = getSignalWeight(sig)
                    const ev = getSignalEvidence(sig)
                    const detail = formatSignalDetail(key, ev)
                    const validationStatus = getValidationStatus(sig, ev)
                    const adjustedSignificance = getAdjustedSignificance(sig, ev)
                    const validationReasoning = getValidationReasoning(sig, ev)
                    return (
                      <div key={key} style={{
                        display: 'flex', justifyContent: 'space-between', gap: 12, fontSize: 13,
                        padding: '6px 10px', background: 'var(--bg-panel)', borderRadius: 4,
                      }}>
                        <div style={{ minWidth: 0, flex: 1 }}>
                          <div style={{ color: 'var(--text-primary)', fontWeight: 600 }}>
                            {formatLabel(key)}
                            {detail ? <span style={{ color: 'var(--text-secondary)', marginLeft: 8, fontWeight: 400 }}>{detail}</span> : null}
                          </div>
                          {(validationStatus || adjustedSignificance) && (
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 6 }}>
                              {validationStatus && (
                                <Badge color={validationBadgeColor(validationStatus)}>
                                  {validationStatus.replace(/_/g, ' ')}
                                </Badge>
                              )}
                              {adjustedSignificance && (
                                <Badge color={significanceBadgeColor(adjustedSignificance)}>
                                  Significance: {adjustedSignificance}
                                </Badge>
                              )}
                            </div>
                          )}
                          {validationReasoning && (
                            <div style={{ marginTop: 8, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                              {validationReasoning}
                            </div>
                          )}
                        </div>
                        <span style={{ fontFamily: 'var(--font-mono)', color: w > 0 ? '#22c55e' : w < 0 ? '#ef4444' : 'var(--text-muted)', fontWeight: 600 }}>
                          {w > 0 ? '+' : ''}{Math.round(w * 100)}
                        </span>
                      </div>
                    )
                  })}
              </div>
            )}
          </div>
        )}

        {narratives.length > 0 && (
          <Section title="Related County Narratives">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {narratives.map((narrative) => (
                <NarrativeCard key={narrative.narrative_id} narrative={narrative} />
              ))}
            </div>
          </Section>
        )}

    </PageShell>
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

function decisionColor(decision: string | null | undefined): string {
  if (!decision) return 'var(--text-muted)'
  const d = decision.toLowerCase()
  if (d.includes('approv') || d.includes('grant')) return 'var(--accent-green)'
  if (d.includes('deni') || d.includes('reject')) return 'var(--accent-red)'
  if (d.includes('continu') || d.includes('tabl')) return 'var(--accent-gold)'
  return 'var(--accent-blue)'
}

function ProceedingRow({ proceeding }: { proceeding: LinkedProceeding }) {
  const zoningDelta = proceeding.current_zoning && proceeding.proposed_zoning
    ? `${proceeding.current_zoning} → ${proceeding.proposed_zoning}`
    : null
  return (
    <div style={{
      border: '1px solid var(--border)',
      borderRadius: 6,
      padding: 12,
      background: 'var(--bg-card)',
    }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 8 }}>
        {proceeding.extraction_type && (
          <Badge color="var(--accent-blue)">{formatLabel(proceeding.extraction_type)}</Badge>
        )}
        {proceeding.decision && (
          <Badge color={decisionColor(proceeding.decision)}>{proceeding.decision}</Badge>
        )}
        {proceeding.meeting_date && (
          <Badge color="var(--accent-cyan)">{formatShortDate(proceeding.meeting_date)}</Badge>
        )}
        {proceeding.match_type === 'address' && (
          <Badge color="var(--text-muted)">matched by address</Badge>
        )}
      </div>
      <div style={{ fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--text-primary)', marginBottom: 4 }}>
        {proceeding.body_name || 'Unknown body'}
        {proceeding.applicant_name && (
          <span style={{ color: 'var(--text-secondary)' }}> — {proceeding.applicant_name}</span>
        )}
        {zoningDelta && (
          <span style={{ color: 'var(--text-secondary)', marginLeft: 8 }}>({zoningDelta})</span>
        )}
      </div>
      {proceeding.supporting_text && (
        <div style={{ fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.5, marginBottom: 6 }}>
          {proceeding.supporting_text}
        </div>
      )}
      {proceeding.document_url && (
        <a
          href={proceeding.document_url}
          target="_blank"
          rel="noopener noreferrer"
          style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--accent-blue)', textDecoration: 'none' }}
        >
          View source PDF →
        </a>
      )}
    </div>
  )
}
