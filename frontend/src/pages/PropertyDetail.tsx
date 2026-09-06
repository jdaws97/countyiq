import { useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import BackButton from '../components/BackButton'
import Badge from '../components/Badge'
import EvidencePanel, { CitedText } from '../components/EvidencePanel'
import IntelligenceEventCard from '../components/IntelligenceEventCard'
import NarrativeCard from '../components/NarrativeCard'
import NearbyParcels from '../components/NearbyParcels'
import PageShell from '../components/PageShell'
import ReportActions from '../components/ReportActions'
import Section from '../components/Section'
import { Button, ButtonLink, Freshness } from '../components/ui'
import { sourceLinkLabel } from '../lib/evidence'
import { formatCurrency, formatLabel, formatShortDate } from '../lib/format'
import { isCompared, toggleComparison } from '../lib/investigationState'
import { useFetchJson } from '../lib/useFetchJson'
import { isWatched, toggleWatch } from '../lib/watchlist'
import { getPropertyClassLabel, getSchoolDistrictLabel } from '../lib/propertyLabels'
import type {
  DevelopmentSignal,
  DevelopmentSignalEvidence,
  IntelligenceFeedResponse,
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
  const flat: DevelopmentSignalEvidence = {}
  for (const [key, value] of Object.entries(signal)) {
    if (value === null || typeof value !== 'object') {
      flat[key] = value
    }
  }
  return flat
}

function getString(value: unknown): string | null {
  return typeof value === 'string' && value.length > 0 ? value : null
}

function getValidationStatus(
  signal: DevelopmentSignal,
  evidence: DevelopmentSignalEvidence,
): string | null {
  return getString(signal.validation_status) ?? getString(evidence['validation_status'])
}

function getAdjustedSignificance(
  signal: DevelopmentSignal,
  evidence: DevelopmentSignalEvidence,
): string | null {
  return getString(signal.adjusted_significance) ?? getString(evidence['adjusted_significance'])
}

function getValidationReasoning(
  signal: DevelopmentSignal,
  evidence: DevelopmentSignalEvidence,
): string | null {
  return getString(signal.validation_reasoning) ?? getString(evidence['validation_reasoning'])
}

function validationBadgeColor(status: string): string {
  if (status === 'upgraded' || status === 'confirmed') {
    return 'var(--accent-green)'
  }
  if (status === 'stale' || status === 'irrelevant') {
    return 'var(--accent-red)'
  }
  if (status === 'downgraded') {
    return 'var(--accent-gold)'
  }
  return 'var(--accent-blue)'
}

function significanceBadgeColor(significance: string): string {
  if (significance === 'high') {
    return 'var(--accent-green)'
  }
  if (significance === 'medium') {
    return 'var(--accent-gold)'
  }
  if (significance === 'low' || significance === 'none') {
    return 'var(--text-muted)'
  }
  return 'var(--accent-blue)'
}

const BRIEF_ACTIONS = {
  investigate: { label: 'Investigate the record', color: 'var(--accent-blue)' },
  watch: { label: 'Watch for changes', color: 'var(--accent-cyan)' },
  insufficient_evidence: { label: 'No clear development lead', color: 'var(--text-muted)' },
}

export default function PropertyDetail() {
  const { pidn } = useParams<{ pidn: string }>()
  const navigate = useNavigate()
  const {
    data: report,
    error,
    loading,
  } = useFetchJson<PropertyReport>(pidn ? `/api/parcels/${encodeURIComponent(pidn)}` : null)
  const intelligenceTimeline = useFetchJson<IntelligenceFeedResponse>(
    pidn
      ? `/api/feed?pidns=${encodeURIComponent(pidn)}&since_days=3650&limit=100&sort=latest`
      : null,
  )
  // localStorage read is cheap; deriving at render (re-triggered by the
  // counter bump on toggle) avoids a setState-in-effect.
  const [, setWatchToggleCount] = useState(0)

  if (loading) {
    return (
      <PageShell>
        <div className="status-message">Loading property…</div>
      </PageShell>
    )
  }
  if (error || !report) {
    return (
      <PageShell>
        <div className="status-message status-message-error">Property not found: {pidn}</div>
      </PageShell>
    )
  }

  const p = report.parcel
  const watchedState = isWatched(p.pidn)
  const tax = report.tax_delinquency
  const flood = report.flood_zone
  const structures = report.structures
  const brief = report.parcel_brief
  const briefAction = brief?.recommendation ? BRIEF_ACTIONS[brief.recommendation] : null
  const narratives = report.related_narratives
  const intelligence = report.intelligence_summary
  const proceedings = report.linked_proceedings ?? []
  const comparedState = isCompared(p.pidn)
  const evidenceFreshness = (report.evidence ?? [])
    .map((item) => item.observed_at ?? item.effective_at)
    .filter((value): value is string => Boolean(value))
    .sort()
    .at(-1)

  return (
    <PageShell>
      {/* Back + Actions */}
      <div className="property-toolbar">
        <BackButton onClick={() => navigate(-1)} marginBottom={0} />
        <div className="property-actions" data-print-hidden>
          <Button
            tone="quiet"
            onClick={() => {
              toggleWatch(p.pidn)
              setWatchToggleCount((c) => c + 1)
            }}
          >
            {watchedState ? '★ Watching' : '☆ Watch'}
          </Button>
          <Button
            tone="quiet"
            onClick={() => {
              const result = toggleComparison(p.pidn)
              if (result.full) {
                window.alert(
                  'Comparison is limited to four parcels. Remove one before adding another.',
                )
              }
              setWatchToggleCount((c) => c + 1)
            }}
          >
            {comparedState ? '✓ In comparison' : '+ Compare'}
          </Button>
          {comparedState && (
            <ButtonLink to="/compare" tone="secondary">
              Open comparison
            </ButtonLink>
          )}
          {p.lat != null && p.lng != null && (
            <ButtonLink
              to={`/map?lat=${p.lat}&lng=${p.lng}&zoom=18&highlight=${p.pidn}`}
              tone="quiet"
            >
              View on map
            </ButtonLink>
          )}
          <ReportActions label={`${p.propadr || p.pidn} property report`} />
        </div>
      </div>

      {/* Header */}
      <div style={{ marginBottom: 32 }}>
        <div className="record-eyebrow">Property Report</div>
        <h1 className="property-address">{p.propadr || 'Address unavailable'}</h1>
        <div className="property-owner">
          {p.owner_full ? (
            <Link
              to={
                p.owner_id
                  ? `/entity/${p.owner_id}`
                  : `/search?q=${encodeURIComponent(p.owner_full)}`
              }
            >
              {p.owner_full}
            </Link>
          ) : (
            'Owner not displayed'
          )}
          <span> · PIDN {p.pidn}</span>
        </div>
        <div className="property-badges">
          {p.class && <Badge color="var(--accent-blue)">{getPropertyClassLabel(p.class)}</Badge>}
          {p.municipality && <Badge color="var(--text-muted)">{formatLabel(p.municipality)}</Badge>}
          {tax.is_delinquent && <Badge color="var(--accent-red)">Tax Delinquent</Badge>}
          {report.zoning?.code && (
            <Badge color="var(--accent-ink)">Zoned {report.zoning.code}</Badge>
          )}
          {flood.in_flood_zone && <Badge color="var(--accent-cyan)">Flood Zone {flood.zone}</Badge>}
          {structures.likely_vacant && <Badge color="var(--accent-gold)">Vacancy screen</Badge>}
          <Freshness value={evidenceFreshness} />
        </div>
      </div>

      {/* Development Momentum */}
      {report?.development_momentum && (
        <div className="momentum-card">
          <h2>Development signals</h2>
          <p className="property-radar-summary">
            {report.development_momentum.eligible
              ? report.development_momentum.top_signal ||
                'Open the signals to review this property’s context.'
              : `Outside radar ranking: ${(report.development_momentum.exclusion_reasons || []).map(formatLabel).join(', ')}`}
          </p>
          <div className="property-radar-scores">
            <div>
              <span>Opportunity</span>
              <strong>{report.development_momentum.opportunity_score}</strong>
            </div>
            <div>
              <span>Momentum</span>
              <strong>{report.development_momentum.score}</strong>
            </div>
            <div>
              <span>Site screening</span>
              <strong>{report.development_momentum.site_readiness_score}</strong>
            </div>
          </div>
          <p className="property-radar-note">
            Compare the signals, then check the source. Scores do not establish that a property is
            for sale or ready to build.
          </p>
          {report.development_momentum.signals && (
            <details className="property-signal-details">
              <summary>
                Review {Object.keys(report.development_momentum.signals).length} signals and their
                evidence
              </summary>
              <div className="signal-list">
                {Object.entries(report.development_momentum.signals)
                  .sort(([, a], [, b]) => {
                    const aExcludes = a.presentation?.affects_eligibility ? 1 : 0
                    const bExcludes = b.presentation?.affects_eligibility ? 1 : 0
                    return (
                      bExcludes - aExcludes ||
                      Math.abs(getSignalWeight(b)) - Math.abs(getSignalWeight(a))
                    )
                  })
                  .map(([key, sig]) => {
                    const ev = getSignalEvidence(sig)
                    const presentation = sig.presentation
                    const validationStatus = getValidationStatus(sig, ev)
                    const adjustedSignificance = getAdjustedSignificance(sig, ev)
                    const validationReasoning = getValidationReasoning(sig, ev)
                    const receipt = sig.evidence_receipt
                    const sourceUrl =
                      receipt?.url ??
                      receipt?.document_url ??
                      getString(ev['detail_url']) ??
                      getString(sig.source_url) ??
                      getString(ev['source_url'])
                    const impacts = presentation?.score_impacts
                    const impactBadges = impacts
                      ? [
                          impacts.momentum !== 0
                            ? { label: 'Momentum', value: impacts.momentum }
                            : null,
                          impacts.opportunity !== 0
                            ? { label: 'Opportunity', value: impacts.opportunity }
                            : null,
                          impacts.site_screening !== 0
                            ? { label: 'Site', value: impacts.site_screening }
                            : null,
                        ].filter((item): item is { label: string; value: number } => item !== null)
                      : []
                    return (
                      <div key={key} className="signal-row">
                        <div style={{ minWidth: 0, flex: 1 }}>
                          <div style={{ color: 'var(--text-primary)', fontWeight: 600 }}>
                            {presentation?.title ?? formatLabel(key)}:{' '}
                            <span style={{ color: 'var(--text-secondary)', fontWeight: 400 }}>
                              {presentation?.summary ?? formatLabel(key)}
                            </span>
                          </div>
                          {presentation?.interpretation && (
                            <div
                              style={{
                                marginTop: 7,
                                color: 'var(--text-secondary)',
                                lineHeight: 1.5,
                              }}
                            >
                              {presentation.interpretation}
                            </div>
                          )}
                          {(presentation?.facts.length ?? 0) > 0 && (
                            <div
                              style={{
                                display: 'flex',
                                flexWrap: 'wrap',
                                gap: '6px 18px',
                                marginTop: 8,
                              }}
                            >
                              {presentation!.facts.map((fact) => (
                                <span
                                  key={`${fact.label}:${fact.value}`}
                                  style={{ fontSize: 12.5, color: 'var(--text-muted)' }}
                                >
                                  <strong style={{ color: 'var(--text-secondary)' }}>
                                    {fact.label}:
                                  </strong>{' '}
                                  {fact.value}
                                </span>
                              ))}
                            </div>
                          )}
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 8 }}>
                            {impactBadges.map((impact) => (
                              <Badge
                                key={impact.label}
                                color={
                                  impact.value > 0 ? 'var(--accent-green)' : 'var(--accent-red)'
                                }
                              >
                                {impact.label} {impact.value > 0 ? '+' : ''}
                                {impact.value}
                              </Badge>
                            ))}
                            {impactBadges.length === 0 && !presentation?.affects_eligibility && (
                              <Badge color="var(--text-muted)">
                                Context only · no direct score change
                              </Badge>
                            )}
                            {presentation?.affects_eligibility && (
                              <Badge color="var(--accent-red)">Radar eligibility exclusion</Badge>
                            )}
                          </div>
                          {(validationStatus || adjustedSignificance) && (
                            <div
                              style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 6 }}
                            >
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
                            <div
                              style={{
                                marginTop: 8,
                                color: 'var(--text-secondary)',
                                lineHeight: 1.5,
                              }}
                            >
                              {validationReasoning}
                            </div>
                          )}
                          {presentation?.caveat && (
                            <div
                              style={{
                                marginTop: 8,
                                color: 'var(--text-muted)',
                                lineHeight: 1.45,
                                fontSize: 12.5,
                              }}
                            >
                              <strong>Caveat:</strong> {presentation.caveat}
                            </div>
                          )}
                          {sourceUrl && (
                            <a
                              href={sourceUrl}
                              target="_blank"
                              rel="noreferrer"
                              className="signal-link"
                            >
                              {sourceLinkLabel(sourceUrl)}
                            </a>
                          )}
                        </div>
                      </div>
                    )
                  })}
              </div>
            </details>
          )}
        </div>
      )}

      {/* Assessment & Sale */}
      <Section title="Assessment & Sale">
        <Grid>
          <Field label="Assessed Total" value={formatCurrency(p.aprtotal)} highlight />
          <Field label="Acres" value={p.acres ? Number(p.acres).toFixed(2) : '--'} />
          <Field label="Sale Date" value={p.saledt || '--'} />
          <Field label="Recorded Sale Price" value={formatCurrency(p.price)} highlight />
          {p.prev_price != null && (
            <Field label="Previous Price" value={formatCurrency(p.prev_price)} />
          )}
          {p.aprland != null && <Field label="Land Value" value={formatCurrency(p.aprland)} />}
          {p.aprbldg != null && <Field label="Building Value" value={formatCurrency(p.aprbldg)} />}
        </Grid>
      </Section>

      {/* Property Details */}
      <Section title="Property Details">
        <Grid>
          <Field label="PIDN" value={p.pidn} />
          <Field label="Class" value={getPropertyClassLabel(p.class) || '--'} />
          <Field label="School District" value={getSchoolDistrictLabel(p.school_dis) || '--'} />
          <Field
            label="Zoning"
            value={
              report.zoning
                ? `${report.zoning.code ?? ''} ${report.zoning.name ?? ''}`.trim() || '--'
                : 'Not mapped'
            }
          />
          {report.zoning?.general_name && (
            <Field label="Zoning category" value={report.zoning.general_name} />
          )}
          {p.acres != null && <Field label="Acres" value={Number(p.acres).toFixed(2)} />}
          {p.yrblt != null && <Field label="Year Built" value={String(p.yrblt)} />}
          {p.style && <Field label="Style" value={p.style} />}
          {p.num_stories != null && <Field label="Stories" value={String(p.num_stories)} />}
          {p.res_living_area != null && (
            <Field label="Living Area" value={`${Number(p.res_living_area).toLocaleString()} sf`} />
          )}
          {p.prev_owner && <Field label="Previous Owner" value={p.prev_owner} />}
          {p.deed_bk && <Field label="Deed" value={`${p.deed_bk}/${p.deed_pg}`} />}
        </Grid>
      </Section>

      {/* Tax Status */}
      <Section title="Tax Status">
        {tax.is_delinquent ? (
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
              <Badge color="var(--accent-red)">Delinquency signal detected</Badge>
            </div>
            {!tax.detail_available && (
              <div
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 11,
                  color: 'var(--text-muted)',
                  marginBottom: 12,
                }}
              >
                Verify the current balance and status with the taxing authority.
              </div>
            )}
            {tax.detail_available && (
              <div
                style={{ border: '1px solid var(--border)', borderRadius: 6, overflow: 'hidden' }}
              >
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '80px 120px 1fr 120px',
                    padding: '8px 16px',
                    background: 'var(--bg-card)',
                    fontFamily: 'var(--font-mono)',
                    fontSize: 9,
                    letterSpacing: 1.5,
                    textTransform: 'uppercase',
                    color: 'var(--text-muted)',
                  }}
                >
                  <div>Year</div>
                  <div>Authority</div>
                  <div></div>
                  <div style={{ textAlign: 'right' }}>Amount</div>
                </div>
                {tax.records.map((rec: TaxDelinquencyRecord, i: number) => (
                  <div
                    key={i}
                    style={{
                      display: 'grid',
                      gridTemplateColumns: '80px 120px 1fr 120px',
                      padding: '8px 16px',
                      borderTop: '1px solid var(--border)',
                      fontFamily: 'var(--font-mono)',
                      fontSize: 12,
                      color: 'var(--text-secondary)',
                    }}
                  >
                    <div>{rec.tax_year}</div>
                    <div>{rec.authority_name}</div>
                    <div></div>
                    <div
                      style={{ textAlign: 'right', color: 'var(--accent-red)', fontWeight: 600 }}
                    >
                      {formatCurrency(rec.total)}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </>
        ) : (
          <Badge color="var(--accent-green)">No delinquency found in the loaded records</Badge>
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
            <Badge color="var(--accent-cyan)">FEMA SFHA · Zone {flood.zone}</Badge>
            <span style={{ fontSize: 14, color: 'var(--text-secondary)', marginLeft: 12 }}>
              {flood.overlap_pct != null
                ? `${flood.overlap_pct.toFixed(1)}% of parcel area overlaps.`
                : 'Parcel overlap detected.'}{' '}
              Insurance and elevation requirements depend on the structure, loan, and official
              determination.
            </span>
          </div>
        ) : (
          <Badge color="var(--accent-green)">No mapped FEMA SFHA overlap</Badge>
        )}
      </Section>

      <Section title="Soils & Site Conditions">
        {report.soil_profile.units.length > 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {report.soil_profile.considerations.length > 0 && (
              <div
                style={{
                  padding: 14,
                  border: '1px solid var(--border)',
                  borderRadius: 6,
                  background: 'var(--bg-card)',
                }}
              >
                <div className="record-label" style={{ marginBottom: 8 }}>
                  What the mapped soils suggest
                </div>
                <ul
                  style={{
                    margin: 0,
                    paddingLeft: 20,
                    color: 'var(--text-secondary)',
                    lineHeight: 1.6,
                  }}
                >
                  {report.soil_profile.considerations.map((consideration) => (
                    <li key={consideration}>{consideration}</li>
                  ))}
                </ul>
              </div>
            )}
            <details className="property-signal-details">
              <summary>Review {report.soil_profile.units.length} mapped soil units</summary>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {report.soil_profile.units.map((unit) => (
                  <div
                    key={unit.source_record_ids.join(',')}
                    style={{
                      padding: 14,
                      border: '1px solid var(--border)',
                      borderRadius: 6,
                      background: 'var(--bg-panel)',
                    }}
                  >
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        gap: 12,
                        alignItems: 'baseline',
                      }}
                    >
                      <div style={{ color: 'var(--text-primary)', fontWeight: 600 }}>
                        {unit.map_unit_symbol || 'Soil unit'}:{' '}
                        {unit.map_unit_name || 'Name unavailable'}
                      </div>
                      <Badge color="var(--accent-blue)">
                        {unit.coverage_pct.toFixed(1)}% of parcel
                      </Badge>
                    </div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 10 }}>
                      {(unit.slope_low != null || unit.slope_high != null) && (
                        <Badge
                          color={
                            (unit.representative_slope ?? 0) >= 15
                              ? 'var(--accent-red)'
                              : 'var(--text-muted)'
                          }
                        >
                          Slope {unit.slope_low ?? '?'}–{unit.slope_high ?? '?'}%; representative{' '}
                          {unit.representative_slope ?? '?'}%
                        </Badge>
                      )}
                      {unit.drainage && (
                        <Badge color="var(--text-muted)">Drainage: {unit.drainage}</Badge>
                      )}
                      {unit.septic_rating && (
                        <Badge
                          color={
                            unit.septic_rating === 'Very limited'
                              ? 'var(--accent-gold)'
                              : 'var(--text-muted)'
                          }
                        >
                          On-lot septic: {unit.septic_rating}
                        </Badge>
                      )}
                      {unit.hydrologic_group && (
                        <Badge
                          color={
                            unit.hydrologic_group === 'D'
                              ? 'var(--accent-red)'
                              : 'var(--text-muted)'
                          }
                        >
                          Hydrologic group {unit.hydrologic_group}
                        </Badge>
                      )}
                      {unit.hydric_rating && (
                        <Badge color="var(--text-muted)">{unit.hydric_rating}</Badge>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </details>
            <div style={{ fontSize: 12.5, lineHeight: 1.5, color: 'var(--text-muted)' }}>
              Generalized mapped-soil screening only. Confirm grading, drainage, foundations, and
              wastewater design with parcel-specific professional review.
              {report.soil_profile.source_url && (
                <>
                  {' '}
                  <a
                    href={report.soil_profile.source_url}
                    target="_blank"
                    rel="noreferrer"
                    className="signal-link"
                  >
                    Open the exact mapped soil records
                  </a>
                  .
                </>
              )}
            </div>
          </div>
        ) : (
          <div style={{ color: 'var(--text-secondary)' }}>
            No county soil polygons intersected this parcel. This is a data-coverage gap, not a
            favorable soil finding.
          </div>
        )}
      </Section>

      {/* Structures */}
      <Section title="Structures">
        <div
          style={{
            fontSize: 15,
            color: 'var(--text-primary)',
            marginBottom: structures.buildings?.length ? 12 : 0,
          }}
        >
          {structures.count} building footprint{structures.count !== 1 ? 's' : ''} detected
          {structures.likely_vacant && (
            <span style={{ color: 'var(--accent-gold)', marginLeft: 12 }}>
              — Vacancy screen; verify current use
            </span>
          )}
        </div>
        {structures.buildings?.length > 0 && (
          <div style={{ border: '1px solid var(--border)', borderRadius: 6, overflow: 'hidden' }}>
            {structures.buildings.map((b: StructureBuilding, i: number) => (
              <div
                key={i}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '10px 16px',
                  borderTop: i > 0 ? '1px solid var(--border)' : 'none',
                  background: i % 2 === 0 ? 'var(--bg-panel)' : 'var(--bg-card)',
                }}
              >
                <span
                  style={{
                    fontFamily: 'var(--font-sans)',
                    fontSize: 13,
                    color: 'var(--text-primary)',
                  }}
                >
                  {b.type}
                </span>
                <span
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 12,
                    color: 'var(--text-secondary)',
                  }}
                >
                  {b.sqft > 0 ? `${b.sqft.toLocaleString()} sf` : '--'}
                </span>
              </div>
            ))}
          </div>
        )}
      </Section>

      <NearbyParcels pidn={p.pidn} title="Nearby parcels" />

      <Section title="Verify This Property Report">
        <EvidencePanel
          items={report.evidence ?? []}
          title="Official and derived records"
          intro="These receipts separate source facts from CountyIQ calculations and show when each record became effective. Open the original link where source policy allows it."
        />
      </Section>

      <Section title="Property intelligence timeline">
        {intelligenceTimeline.loading && (
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)' }}>
            Loading property-linked events...
          </div>
        )}
        {!intelligenceTimeline.loading && intelligenceTimeline.error && (
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--accent-red)' }}>
            Property-linked events could not be loaded. The property report remains available.
          </div>
        )}
        {!intelligenceTimeline.loading &&
          !intelligenceTimeline.error &&
          (intelligenceTimeline.data?.events.length ?? 0) === 0 && (
            <div
              style={{
                fontFamily: 'var(--font-sans)',
                fontSize: 14,
                lineHeight: 1.6,
                color: 'var(--text-secondary)',
              }}
            >
              No source-backed intelligence events are linked to this property yet. This is not a
              claim that nothing has happened.
            </div>
          )}
        {(intelligenceTimeline.data?.events.length ?? 0) > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {intelligenceTimeline.data!.events.map((event) => (
              <IntelligenceEventCard key={event.event_key} event={event} />
            ))}
          </div>
        )}
      </Section>

      {intelligence?.cross_signal_insight && (
        <Section title="Cross-Signal Insight">
          <div
            style={{
              borderLeft: '2px solid var(--accent-gold)',
              paddingLeft: 14,
              fontFamily: 'var(--font-sans)',
              fontSize: 14,
              lineHeight: 1.7,
              color: 'var(--text-secondary)',
            }}
          >
            <CitedText text={intelligence.cross_signal_insight} evidence={report.evidence} />
            <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
              {intelligence.signals_validated_count ? (
                <Badge color="var(--accent-blue)">
                  {intelligence.signals_validated_count} signal
                  {intelligence.signals_validated_count === 1 ? '' : 's'} validated
                </Badge>
              ) : null}
              {intelligence.last_run_at && (
                <Badge color="var(--accent-cyan)">
                  Validated {formatShortDate(intelligence.last_run_at)}
                </Badge>
              )}
            </div>
          </div>
        </Section>
      )}

      {brief && (
        <Section title="Research brief">
          <div
            style={{
              background: 'var(--bg-card)',
              border: '1px solid var(--border)',
              borderRadius: 8,
              padding: 18,
            }}
          >
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 14 }}>
              {briefAction && <Badge color={briefAction.color}>{briefAction.label}</Badge>}
              {brief.signal_count != null && (
                <Badge color="var(--text-muted)">
                  {brief.signal_count} source {brief.signal_count === 1 ? 'signal' : 'signals'}
                </Badge>
              )}
              {brief.generated_at && (
                <Badge color="var(--accent-cyan)">
                  Generated {formatShortDate(brief.generated_at)}
                </Badge>
              )}
            </div>

            <div
              style={{
                fontFamily: 'var(--font-sans)',
                fontSize: 15,
                lineHeight: 1.7,
                color: 'var(--text-primary)',
                marginBottom: brief.key_questions.length > 0 || brief.citations.length > 0 ? 16 : 0,
              }}
            >
              <CitedText text={brief.brief_text} evidence={brief.citation_evidence ?? []} />
            </div>

            {brief.key_questions.length > 0 && (
              <div style={{ marginBottom: brief.citations.length > 0 ? 16 : 0 }}>
                <div className="record-label">Questions to resolve</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {brief.key_questions.map((question) => (
                    <div
                      key={question}
                      style={{
                        fontFamily: 'var(--font-sans)',
                        fontSize: 14,
                        color: 'var(--text-secondary)',
                      }}
                    >
                      {question}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {(brief.citation_evidence?.length ?? 0) > 0 && (
              <div style={{ marginTop: 16 }}>
                <EvidencePanel
                  items={brief.citation_evidence}
                  title="Source evidence"
                  intro="Review the source facts behind this summary."
                />
              </div>
            )}
          </div>
        </Section>
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
  return <div className="field-grid">{children}</div>
}

const IDENTIFIER_FIELDS = new Set(['PIDN', 'Deed'])

function Field({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  const valueClass = highlight
    ? 'field-value field-value-highlight'
    : IDENTIFIER_FIELDS.has(label)
      ? 'field-value field-value-mono'
      : 'field-value'
  return (
    <div>
      <div className="field-label">{label}</div>
      <div className={valueClass}>{value}</div>
    </div>
  )
}

function decisionColor(decision: string | null | undefined): string {
  if (!decision) {
    return 'var(--text-muted)'
  }
  const d = decision.toLowerCase()
  if (d.includes('approv') || d.includes('grant')) {
    return 'var(--accent-green)'
  }
  if (d.includes('deni') || d.includes('reject')) {
    return 'var(--accent-red)'
  }
  if (d.includes('continu') || d.includes('tabl')) {
    return 'var(--accent-gold)'
  }
  return 'var(--accent-blue)'
}

function ProceedingRow({ proceeding }: { proceeding: LinkedProceeding }) {
  const zoningDelta =
    proceeding.current_zoning && proceeding.proposed_zoning
      ? `${proceeding.current_zoning} → ${proceeding.proposed_zoning}`
      : null
  return (
    <div
      style={{
        border: '1px solid var(--border)',
        borderRadius: 6,
        padding: 12,
        background: 'var(--bg-card)',
      }}
    >
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 8 }}>
        {proceeding.extraction_type && (
          <Badge color="var(--accent-blue)">{formatLabel(proceeding.extraction_type)}</Badge>
        )}
        {proceeding.decision && (
          <Badge color={decisionColor(proceeding.decision)}>
            {proceeding.decision_scope && formatLabel(proceeding.decision_scope) + ': '}
            {proceeding.decision}
          </Badge>
        )}
        {proceeding.meeting_date && (
          <Badge color="var(--accent-cyan)">{formatShortDate(proceeding.meeting_date)}</Badge>
        )}
        {proceeding.page_number != null && (
          <Badge color="var(--text-muted)">page {proceeding.page_number}</Badge>
        )}
        {proceeding.extraction_confidence != null && (
          <Badge color="var(--text-muted)">
            {Math.round(proceeding.extraction_confidence * 100)}% extraction confidence
          </Badge>
        )}
        {proceeding.match_type === 'address' && (
          <Badge color="var(--text-muted)">matched by address</Badge>
        )}
      </div>
      <div
        style={{
          fontFamily: 'var(--font-sans)',
          fontSize: 13,
          color: 'var(--text-primary)',
          marginBottom: 4,
        }}
      >
        {proceeding.body_name || 'Unknown body'}
        {proceeding.applicant_name && (
          <span style={{ color: 'var(--text-secondary)' }}> — {proceeding.applicant_name}</span>
        )}
        {zoningDelta && (
          <span style={{ color: 'var(--text-secondary)', marginLeft: 8 }}>({zoningDelta})</span>
        )}
      </div>
      {proceeding.supporting_text && (
        <div
          style={{
            fontFamily: 'var(--font-sans)',
            fontSize: 13,
            color: 'var(--text-secondary)',
            lineHeight: 1.5,
            marginBottom: 6,
          }}
        >
          {proceeding.supporting_text}
        </div>
      )}
      {proceeding.evidence && (
        <div style={{ marginTop: 10 }}>
          <EvidencePanel items={[proceeding.evidence]} title="Verify this proceeding" />
        </div>
      )}
    </div>
  )
}
