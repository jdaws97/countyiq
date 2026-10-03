import MunicipalEvidence from '../MunicipalEvidence'
import { Button } from '../ui'
import { useSourceViewer } from '../../lib/useSourceViewer'
import { floodScreeningSummary } from '../../lib/floodScreening'
import { collectionStatusLabel } from '../../lib/sitePacket'
import { formatShortDate } from '../../lib/format'
import type { SiteIntakePacket } from '../../types/siteIntake'

export default function SiteEvidence({ packet, pidn }: { packet: SiteIntakePacket; pidn: string }) {
  const openSource = useSourceViewer()
  return (
    <>
      <section className="site-section" id="site-evidence" aria-labelledby="site-evidence-heading">
        <div className="site-section-title">
          <h2 id="site-evidence-heading">What the records establish</h2>
          <Button onClick={() => openSource(packet.report.evidence)}>Check source receipts</Button>
        </div>
        <div className="site-facts">
          <article>
            <h3>Mapped zoning</h3>
            <strong>
              {packet.report.zoning
                ? `${packet.report.zoning.code} · ${packet.report.zoning.name}`
                : 'Unknown'}
            </strong>
            <p>
              This is a parcel-center match. Check split zoning and the current municipal ordinance;
              it does not establish that the proposed use is permitted.
            </p>
          </article>
          <article>
            <h3>Flood screening</h3>
            <p>{floodScreeningSummary(packet.report.flood_zone)}</p>
          </article>
          <article>
            <h3>Mapped soils</h3>
            <strong>{packet.report.soil_profile.mapped_coverage_pct}% parcel coverage</strong>
            <p>
              {packet.report.soil_profile.considerations.join(' ') ||
                'No soil considerations established by the loaded records.'}
            </p>
            <p>Missing mapping does not establish site suitability.</p>
          </article>
        </div>
        <div className="site-source-grid">
          {packet.sources.map((source) => (
            <div key={source.key}>
              <strong>{source.label}</strong>
              <span className={`site-source-status site-source-${source.status}`}>
                {source.status === 'current'
                  ? 'Refresh current'
                  : source.status === 'stale'
                    ? 'Refresh needs attention'
                    : 'Refresh unverified'}
              </span>
              <small>
                Last successful acquisition:{' '}
                {source.last_successful_run_at
                  ? formatShortDate(source.last_successful_run_at)
                  : 'Unknown'}
              </small>
            </div>
          ))}
        </div>
        <p className="site-muted">
          Acquisition dates describe when CountyIQ checked a source, not when the map or rule became
          effective.
        </p>
      </section>
      <section className="site-section" id="site-history" aria-labelledby="site-history-heading">
        <h2 id="site-history-heading">Municipal record trail</h2>
        <p>
          These are source passages associated with this parcel by PIDN or address. A reference does
          not itself establish approval or a complete project history.
        </p>
        <MunicipalEvidence
          pidn={pidn}
          municipality={packet.report.parcel.municipality}
          initialData={packet.report.municipal_evidence}
        />
        <details>
          <summary>Collection coverage for this municipality</summary>
          {packet.municipal_collection.length ? (
            <ul>
              {packet.municipal_collection.map((body, index) => (
                <li key={`${body.body_name}:${index}`}>
                  {body.body_name}: {collectionStatusLabel(body.status)} · Checked{' '}
                  {body.checked_at ? formatShortDate(body.checked_at) : 'unknown'}
                </li>
              ))}
            </ul>
          ) : (
            <p>No active municipal collection coverage is established.</p>
          )}
        </details>
      </section>
    </>
  )
}
