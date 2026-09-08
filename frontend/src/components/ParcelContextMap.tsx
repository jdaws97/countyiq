import { Link } from 'react-router-dom'
import type { Geometry } from 'geojson'
import { useFetchJson } from '../lib/useFetchJson'
import type { ParcelFeatureCollection, PropertyReport } from '../types/api'
import './ParcelContextMap.css'

function polygons(geometry: Geometry): number[][][] {
  if (geometry.type === 'Polygon') {
    return geometry.coordinates
  }
  if (geometry.type === 'MultiPolygon') {
    return geometry.coordinates.flat()
  }
  return []
}

export default function ParcelContextMap({ report }: { report: PropertyReport }) {
  const parcel = report.parcel
  const latitude = parcel.lat
  const longitude = parcel.lng
  const radius = Math.max(0.003, Math.sqrt(Number(parcel.acres ?? 0)) * 0.00055)
  const coordinatesAvailable = latitude != null && longitude != null
  const query = coordinatesAvailable
    ? `/api/parcels/bbox?west=${longitude - radius}&east=${longitude + radius}&south=${latitude - radius}&north=${latitude + radius}&limit=1500`
    : null
  const { data, loading, error } = useFetchJson<ParcelFeatureCollection>(query)
  const features = data?.features ?? []
  const selected = features.find((feature) => feature.properties?.pidn === parcel.pidn)
  const points = selected ? polygons(selected.geometry).flat() : []
  const lngs = points.map((point) => point[0])
  const lats = points.map((point) => point[1])
  const cosine = Math.cos(((latitude ?? 40) * Math.PI) / 180)
  const centerX = points.length ? (Math.min(...lngs) + Math.max(...lngs)) / 2 : (longitude ?? 0)
  const centerY = points.length ? (Math.min(...lats) + Math.max(...lats)) / 2 : (latitude ?? 0)
  const span = points.length
    ? Math.max(
        ((Math.max(...lngs) - Math.min(...lngs)) * cosine) / 1.76,
        Math.max(...lats) - Math.min(...lats),
        0.0007,
      ) * 1.7
    : radius
  const project = (point: number[]) =>
    `${300 + (((point[0] - centerX) * cosine) / span) * 340},${170 - ((point[1] - centerY) / span) * 340}`
  const adjacent = new Set(
    (report.source_explanation?.citation_evidence ?? [])
      .filter((item) => item.citation_key.includes(':adjacent_'))
      .map((item) => item.details.pidn),
  )

  return (
    <div className="parcel-context-map">
      {selected ? (
        <svg
          viewBox="0 0 600 340"
          role="img"
          aria-label={`Mapped boundaries around ${parcel.propadr || parcel.pidn}. The selected property is teal.`}
        >
          <defs>
            <pattern
              id={`map-grid-${parcel.pidn}`}
              width="34"
              height="34"
              patternUnits="userSpaceOnUse"
            >
              <path d="M 34 0 L 0 0 0 34" fill="none" stroke="currentColor" strokeWidth="0.4" />
            </pattern>
          </defs>
          <rect width="600" height="340" fill={`url(#map-grid-${parcel.pidn})`} />
          {features.map((feature) => (
            <g
              key={feature.properties.pidn}
              className={
                feature.properties.pidn === parcel.pidn
                  ? 'parcel-map-subject'
                  : adjacent.has(feature.properties.pidn)
                    ? 'parcel-map-adjoining'
                    : 'parcel-map-neighbor'
              }
            >
              <path
                fillRule="evenodd"
                d={polygons(feature.geometry)
                  .map((ring) => `M ${ring.map(project).join(' L ')} Z`)
                  .join(' ')}
              />
            </g>
          ))}
        </svg>
      ) : (
        <div className="parcel-map-empty">
          {loading
            ? 'Loading parcel boundaries…'
            : error
              ? 'Map preview unavailable'
              : 'Parcel boundary unavailable'}
        </div>
      )}
      <span className="parcel-map-north" aria-hidden="true">
        N ↑
      </span>
      <div className="parcel-map-caption">
        <span>
          <i />
          Selected property
        </span>
        {adjacent.size > 0 && (
          <span>
            <i className="adjoining-key" />
            Adjoining ownership
          </span>
        )}
      </div>
      {coordinatesAvailable && (
        <Link
          className="parcel-map-open"
          to={`/map?lat=${latitude}&lng=${longitude}&zoom=17&highlight=${parcel.pidn}`}
        >
          Explore map ↗
        </Link>
      )}
      <span className="parcel-map-attribution">County parcel boundaries · context view</span>
    </div>
  )
}
