import { useState } from 'react'
import { Link } from 'react-router-dom'

import Badge from './Badge'
import Section from './Section'
import { Button, ButtonLink, StatusMessage } from './ui'
import { formatCurrencyCompact } from '../lib/format'
import { getPropertyClassLabel } from '../lib/propertyLabels'
import { useFetchJson } from '../lib/useFetchJson'
import type { NearbyParcelsResponse } from '../types/api'

const RADIUS_OPTIONS = [
  { value: 400, label: '400 m' },
  { value: 800, label: '800 m' },
  { value: 1600, label: '1.6 km' },
]

/**
 * Parcels around an anchor: the corridor view an investor needs when a plan,
 * a hearing, or a sale lands next door. Ranked by opportunity score, then
 * distance. Owner names are public record; an owner links to its case file
 * when the entity resolver knows it.
 */
export default function NearbyParcels({
  pidn,
  projectKey,
  title = 'Nearby parcels',
}: {
  pidn?: string
  projectKey?: string
  title?: string
}) {
  const [radius, setRadius] = useState(800)
  const [expandedScope, setExpandedScope] = useState<string | null>(null)
  const scope = `${pidn ?? projectKey}:${radius}`
  const expanded = expandedScope === scope
  const params = new URLSearchParams({ radius_m: String(radius), limit: '40' })
  if (pidn) {
    params.set('pidn', pidn)
  }
  if (projectKey) {
    params.set('project_key', projectKey)
  }
  const { data, error, loading } = useFetchJson<NearbyParcelsResponse>(
    pidn || projectKey ? `/api/parcels/near?${params}` : null,
  )
  const parcels = data?.parcels ?? []
  const anchor = data?.anchor_pidns ?? []

  return (
    <Section title={title}>
      <div className="section-actions" data-print-hidden style={{ marginBottom: 12 }}>
        <label
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 8,
            fontSize: 13,
            color: 'var(--text-secondary)',
          }}
        >
          Within
          <select value={radius} onChange={(event) => setRadius(Number(event.target.value))}>
            {RADIUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        {anchor.length > 1 && (
          <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>
            Measured from {anchor.length} linked parcels
          </span>
        )}
      </div>
      {loading && <StatusMessage>Finding parcels nearby…</StatusMessage>}
      {!loading && error && (
        <StatusMessage tone="error">Nearby parcels could not be loaded.</StatusMessage>
      )}
      {!loading && !error && data && anchor.length === 0 && (
        <div className="status-message">
          No mapped parcel geometry is linked to this record yet, so a corridor view is not
          possible.
        </div>
      )}
      {!loading && !error && anchor.length > 0 && parcels.length === 0 && (
        <div className="status-message">No other current parcels fall within {radius} m.</div>
      )}
      {parcels.length > 0 && (
        <div className="data-table nearby-parcels" data-expanded={expanded}>
          <div
            className="data-table-head"
            style={{ gridTemplateColumns: '1fr 70px 90px 60px 90px 150px 70px', minWidth: 760 }}
          >
            <div>Parcel</div>
            <div className="cell-right">Distance</div>
            <div>Class</div>
            <div className="cell-right">Acres</div>
            <div className="cell-right">Assessed</div>
            <div>Owner</div>
            <div className="cell-right">Opp.</div>
          </div>
          {parcels.map((row, index) => (
            <div
              key={row.pidn}
              className="data-table-row"
              data-nearby-extra={index >= 5 ? 'true' : undefined}
              style={{
                gridTemplateColumns: '1fr 70px 90px 60px 90px 150px 70px',
                minWidth: 760,
                padding: '10px 16px',
              }}
            >
              <div style={{ minWidth: 0 }}>
                <Link to={`/property/${row.pidn}`} className="cell-strong">
                  {row.propadr || row.pidn}
                </Link>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 4 }}>
                  {row.has_active_plan && (
                    <Badge color="var(--accent-cyan)">Own plan or matter</Badge>
                  )}
                  {row.likely_vacant && <Badge color="var(--accent-gold)">Vacancy screen</Badge>}
                  {row.has_tax_delinquency && (
                    <Badge color="var(--accent-red)">Delinquency signal</Badge>
                  )}
                  {row.top_signal && !row.has_active_plan && (
                    <span className="cell-muted" style={{ fontSize: 12 }}>
                      {row.top_signal}
                    </span>
                  )}
                </div>
              </div>
              <div className="cell-right" data-label="Distance">
                {row.distance_m != null ? `${row.distance_m} m` : '—'}
              </div>
              <div className="cell-muted" data-label="Class">
                {getPropertyClassLabel(row.class) || row.class || '—'}
              </div>
              <div className="cell-right" data-label="Acres">
                {row.acres != null ? Number(row.acres).toFixed(1) : '—'}
              </div>
              <div className="cell-right" data-label="Assessed value">
                {row.aprtotal != null ? formatCurrencyCompact(row.aprtotal) : '—'}
              </div>
              <div style={{ minWidth: 0 }} data-label="Owner">
                {row.owner_id != null && row.owner_label ? (
                  <Link to={`/entity/${row.owner_id}`}>{row.owner_label}</Link>
                ) : (
                  <span className="cell-muted">{row.owner_label || 'Owner unknown'}</span>
                )}
              </div>
              <div className="cell-right" data-label="Opportunity">
                {row.opportunity_score != null ? (
                  <span
                    className="score-pill"
                    style={
                      {
                        '--score-color':
                          row.opportunity_score >= 60
                            ? 'var(--accent-green)'
                            : row.opportunity_score >= 40
                              ? 'var(--accent-gold)'
                              : 'var(--accent-ink)',
                      } as React.CSSProperties
                    }
                  >
                    {row.opportunity_score}
                  </span>
                ) : (
                  <span className="cell-muted">—</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
      {parcels.length > 5 && (
        <div className="section-actions" style={{ marginTop: 12 }} data-print-hidden>
          <Button
            tone="quiet"
            aria-expanded={expanded}
            onClick={() => setExpandedScope(expanded ? null : scope)}
          >
            {expanded
              ? 'Show fewer nearby parcels'
              : `Show ${parcels.length - 5} more nearby parcels`}
          </Button>
          <span className="cell-muted" style={{ fontSize: 12 }}>
            Ranked by opportunity · up to 40 results
          </span>
        </div>
      )}
      {parcels.length > 0 && data && data.anchor_lat != null && data.anchor_lng != null && (
        <div className="section-actions" style={{ marginTop: 12 }} data-print-hidden>
          <ButtonLink
            to={`/map?lat=${data.anchor_lat}&lng=${data.anchor_lng}&zoom=16&layer=radar&radar=opportunity`}
            tone="quiet"
          >
            Open this area on the map
          </ButtonLink>
        </div>
      )}
    </Section>
  )
}
