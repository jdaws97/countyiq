import { WebMercatorViewport } from '@deck.gl/core'
import type { MapViewState } from '@deck.gl/core'
import type { Geometry } from 'geojson'

export interface MapBounds {
  west: number
  south: number
  east: number
  north: number
}

export interface MapSize { width: number; height: number }

const isFiniteNumber = (value: string | null) => value !== null && value.trim() !== '' && Number.isFinite(Number(value))

export function urlView(search: URLSearchParams, fallback: MapViewState): MapViewState {
  const lat = search.get('lat')
  const lng = search.get('lng')
  const zoom = search.get('zoom')
  if (!isFiniteNumber(lat) || !isFiniteNumber(lng)) return fallback
  const latitude = Number(lat)
  const longitude = Number(lng)
  if (latitude < -85.051129 || latitude > 85.051129 || longitude < -180 || longitude > 180) return fallback
  if (zoom !== null && !isFiniteNumber(zoom)) return fallback
  const parsedZoom = zoom === null ? 16 : Number(zoom)
  if (parsedZoom < 0 || parsedZoom > 24) return fallback
  return { ...fallback, latitude, longitude, zoom: parsedZoom }
}

function viewport(viewState: MapViewState, size: MapSize) {
  return new WebMercatorViewport({ ...viewState, width: Math.max(1, size.width), height: Math.max(1, size.height) })
}

export function visibleBounds(viewState: MapViewState, size: MapSize): MapBounds {
  const [west, south, east, north] = viewport(viewState, size).getBounds()
  return { west, south, east, north }
}

export function splitBounds(bounds: MapBounds, maxSpan = 0.245): MapBounds[] {
  const columns = Math.max(1, Math.ceil((bounds.east - bounds.west) / maxSpan))
  const rows = Math.max(1, Math.ceil((bounds.north - bounds.south) / maxSpan))
  const width = (bounds.east - bounds.west) / columns
  const height = (bounds.north - bounds.south) / rows
  return Array.from({ length: columns * rows }, (_, index) => {
    const column = index % columns
    const row = Math.floor(index / columns)
    return { west: bounds.west + column * width, south: bounds.south + row * height, east: bounds.west + (column + 1) * width, north: bounds.south + (row + 1) * height }
  })
}

export function geometryBounds(geometry: Geometry | null | undefined): MapBounds | null {
  const coordinates: number[][] = []
  const visit = (value: unknown) => {
    if (!Array.isArray(value)) return
    if (typeof value[0] === 'number' && typeof value[1] === 'number') coordinates.push(value as number[])
    else value.forEach(visit)
  }
  if (geometry?.type === 'GeometryCollection') {
    const children = geometry.geometries.map(geometryBounds).filter((bounds): bounds is MapBounds => bounds !== null)
    if (!children.length) return null
    return {
      west: Math.min(...children.map((bounds) => bounds.west)), south: Math.min(...children.map((bounds) => bounds.south)),
      east: Math.max(...children.map((bounds) => bounds.east)), north: Math.max(...children.map((bounds) => bounds.north)),
    }
  }
  if (geometry) visit(geometry.coordinates)
  if (!coordinates.length) return null
  const lng = coordinates.map((point) => point[0]).filter(Number.isFinite)
  const lat = coordinates.map((point) => point[1]).filter(Number.isFinite)
  if (!lng.length || !lat.length) return null
  return { west: Math.min(...lng), south: Math.min(...lat), east: Math.max(...lng), north: Math.max(...lat) }
}

export function fitGeometry(viewState: MapViewState, size: MapSize, geometry: Geometry): MapViewState | null {
  const bounds = geometryBounds(geometry)
  if (!bounds) return null
  const fitted = viewport(viewState, size).fitBounds([[bounds.west, bounds.south], [bounds.east, bounds.north]], {
    padding: Math.min(80, Math.max(24, Math.round(Math.min(size.width, size.height) * 0.1))),
    maxZoom: 17,
  })
  return { ...viewState, longitude: fitted.longitude, latitude: fitted.latitude, zoom: fitted.zoom }
}
