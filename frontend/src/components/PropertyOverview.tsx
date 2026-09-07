import { Link } from 'react-router-dom'
import { formatCurrency, formatShortDate } from '../lib/format'
import { useSourceViewer } from '../lib/useSourceViewer'
import type { PropertyReport } from '../types/api'
import './PropertyOverview.css'

export default function PropertyOverview({ report }: { report: PropertyReport }) {
  const openSource = useSourceViewer()
  const p = report.parcel
  const soils = report.soil_profile
  const soilNote =
    soils.considerations[0] ??
    (soils.units.length
      ? 'Mapped soils are available; septic suitability is not established.'
      : 'Soil coverage is unavailable.')
  const adjacent = (report.source_explanation?.citation_evidence ?? []).filter(
    (item) =>
      item.citation_key.toLowerCase().includes(':adjacent_') &&
      typeof item.details?.pidn === 'string',
  )
  const zoningEvidence = report.evidence.filter(
    (item) => item.source_kind === 'official_zoning_layer',
  )
  const soilEvidence = report.evidence.filter((item) => item.source_kind === 'official_soil_layer')
  const floodEvidence = report.evidence.filter(
    (item) => item.source_kind === 'official_flood_layer',
  )

  return (
    <section
      id="property-context"
      className="property-overview"
      aria-labelledby="property-context-heading"
    >
      <h2 id="property-context-heading">Site & ownership</h2>
      <div className="property-overview-facts">
        <div>
          <span>Land area</span>
          <strong>
            {p.acres == null ? 'Not recorded' : `${Number(p.acres).toLocaleString()} acres`}
          </strong>
        </div>
        <div>
          <span>Assessed value</span>
          <strong>{formatCurrency(p.aprtotal)}</strong>
        </div>
        <div>
          <span>Last recorded sale</span>
          <strong>{formatCurrency(p.price)}</strong>
          <span>{formatShortDate(p.saledt) ?? 'Date unavailable'}</span>
        </div>
      </div>
      <div className="property-overview-constraints">
        <article>
          <h3>Current mapped zoning</h3>
          <p>
            {report.zoning?.name ?? 'Zoning is not available in the loaded records.'}
            {report.zoning?.code ? ` (${report.zoning.code})` : ''}
          </p>
          <p className="property-context-note">
            Confirm permitted uses with the municipality. Future land-use policy does not change
            current zoning.
          </p>
          {zoningEvidence.length > 0 && (
            <button className="source-catalog-button" onClick={() => openSource(zoningEvidence)}>
              View zoning source
            </button>
          )}
        </article>
        <article>
          <h3>Flood & soils</h3>
          <p>
            {report.flood_zone.in_flood_zone
              ? `Mapped high-risk flood area overlaps this property${report.flood_zone.overlap_pct == null ? '.' : ` (${report.flood_zone.overlap_pct.toFixed(1)}%).`}`
              : 'No overlap with the mapped high-risk flood area. This does not exclude all flood risk.'}
          </p>
          <p>{soilNote}</p>
          {soilEvidence.length > 0 && (
            <button
              className="source-catalog-button"
              onClick={() => openSource([...soilEvidence, ...floodEvidence])}
            >
              View mapped sources
            </button>
          )}
        </article>
        <article>
          <h3>What remains to check</h3>
          <p>
            Water and sewer availability, capacity, access and permitted use need confirmation for
            the intended project.
          </p>
          {report.tax_delinquency.is_delinquent && (
            <p>
              A tax-claim listing flags this property. Check its current status with the Tax Claim
              Bureau.
            </p>
          )}
        </article>
      </div>
      {adjacent.length > 0 && (
        <div className="property-connections">
          <h3>Adjoining parcels with the same recorded owner</h3>
          <p>Recorded names and mapped boundaries establish this connection.</p>
          {adjacent.map((item) => (
            <div key={item.evidence_id}>
              <Link to={`/property/${encodeURIComponent(String(item.details.pidn))}`}>
                {String(item.details.address ?? item.details.pidn)}
              </Link>
              <span>
                {typeof item.details.last_recorded_sale_date === 'string'
                  ? `Recorded sale ${formatShortDate(item.details.last_recorded_sale_date)}`
                  : 'Sale date unavailable'}
              </span>
              <button className="source-catalog-button" onClick={() => openSource([item])}>
                View ownership source
              </button>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
