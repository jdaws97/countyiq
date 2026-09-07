import { Link } from 'react-router-dom'

import { formatShortDate } from '../lib/format'
import { recordDateTimestamp } from '../lib/recordDates'
import type { OwnerParcel } from '../types/api'
import './OwnerRecordSummary.css'

function acreage(value: OwnerParcel['acres']): number | null {
  if (value == null || value === '') {
    return null
  }
  const parsed = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null
}

function formatAcreage(value: number): string {
  return `${value.toLocaleString('en-US', { maximumFractionDigits: 2 })} acres`
}

function latestRecordedSale(parcels: OwnerParcel[]): OwnerParcel | null {
  return parcels.reduce<OwnerParcel | null>((latest, parcel) => {
    const parcelTimestamp = recordDateTimestamp(parcel.saledt)
    if (parcelTimestamp == null) {
      return latest
    }
    const latestTimestamp = latest ? recordDateTimestamp(latest.saledt) : null
    if (latestTimestamp == null || parcelTimestamp > latestTimestamp) {
      return parcel
    }
    return latest
  }, null)
}

export default function OwnerRecordSummary({ parcels }: { parcels: OwnerParcel[] }) {
  if (parcels.length === 0) {
    return null
  }

  const acreageValues = parcels
    .map((parcel) => acreage(parcel.acres))
    .filter((value) => value != null)
  const totalAcreage = acreageValues.reduce((sum, value) => sum + value, 0)
  const municipalities = new Map<string, number>()
  for (const parcel of parcels) {
    const name = parcel.municipality || 'Municipality unavailable'
    municipalities.set(name, (municipalities.get(name) ?? 0) + 1)
  }
  const topMunicipalities = [...municipalities.entries()]
    .sort(([leftName, leftCount], [rightName, rightCount]) => {
      return rightCount - leftCount || leftName.localeCompare(rightName)
    })
    .slice(0, 3)
  const latestSale = latestRecordedSale(parcels)

  return (
    <section className="owner-record-summary" aria-labelledby="owner-record-summary-heading">
      <div className="owner-record-summary-heading">
        <div className="owner-record-summary-eyebrow">Recorded portfolio</div>
        <h2 id="owner-record-summary-heading">Linked county property records</h2>
        <p>
          Grouped from the linked county records. Confirm deeds and entity records before treating
          this as one legal portfolio.
        </p>
      </div>

      <div className="owner-record-summary-grid">
        <div className="owner-record-summary-item">
          <div className="owner-record-summary-label">Known acreage</div>
          <div className="owner-record-summary-value">
            {acreageValues.length > 0 ? formatAcreage(totalAcreage) : 'Unavailable'}
          </div>
          <div className="owner-record-summary-detail">
            Acreage available for {acreageValues.length} of {parcels.length} records
          </div>
        </div>

        <div className="owner-record-summary-item">
          <div className="owner-record-summary-label">Municipalities</div>
          <ul className="owner-record-summary-municipalities">
            {topMunicipalities.map(([municipality, count]) => (
              <li key={municipality}>
                <span>{municipality}</span>
                <span>{count} records</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="owner-record-summary-item">
          <div className="owner-record-summary-label">Most recent recorded sale</div>
          {latestSale ? (
            <Link
              className="owner-record-summary-sale"
              to={`/property/${encodeURIComponent(latestSale.pidn)}`}
            >
              {formatShortDate(latestSale.saledt)}
              <span>{latestSale.propadr || latestSale.pidn}</span>
            </Link>
          ) : (
            <div className="owner-record-summary-detail">No recorded sale date available</div>
          )}
        </div>
      </div>
    </section>
  )
}
