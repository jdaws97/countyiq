import { useState, useEffect, useCallback, useMemo } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import { Map } from 'react-map-gl/maplibre'
import { DeckGL } from '@deck.gl/react'
import { GeoJsonLayer } from '@deck.gl/layers'
import Nav from '../components/Nav'
import LayerToggle, { type LayerConfig } from '../components/LayerToggle'

const BASEMAP = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json'

const INITIAL_VIEW_STATE = {
  longitude: -76.73,
  latitude: 39.92,
  zoom: 10,
  pitch: 0,
  bearing: 0,
}

const LAYER_DEFS: { id: string; name: string; color: string; defaultOn: boolean }[] = [
  { id: 'municipalities', name: 'Municipalities', color: '#3dbd6f', defaultOn: true },
  { id: 'flood_zones', name: 'Flood Zones', color: '#4a7fff', defaultOn: false },
  { id: 'zoning', name: 'Zoning', color: '#7c5cbf', defaultOn: false },
  { id: 'penndot_projects', name: 'PennDOT Projects', color: '#ffa500', defaultOn: false },
]

const URL_LAYER_MAP: Record<string, string> = {
  flood: 'flood_zones',
}

export default function MapView() {
  const [searchParams] = useSearchParams()

  const [layers, setLayers] = useState<LayerConfig[]>(() => {
    const urlLayer = searchParams.get('layer')
    const enabledFromUrl = urlLayer ? URL_LAYER_MAP[urlLayer] : null

    return LAYER_DEFS.map((def) => ({
      id: def.id,
      name: def.name,
      color: def.color,
      enabled: def.defaultOn || def.id === enabledFromUrl,
    }))
  })

  const [geoData, setGeoData] = useState<Record<string, GeoJSON.FeatureCollection>>({})

  useEffect(() => {
    LAYER_DEFS.forEach((def) => {
      fetch(`/api/layers/${def.id}`)
        .then((r) => {
          if (!r.ok) throw new Error(`${r.status}`)
          return r.json()
        })
        .then((data) => {
          setGeoData((prev) => ({ ...prev, [def.id]: data }))
        })
        .catch(() => {
          // Layer data unavailable -- leave empty
        })
    })
  }, [])

  const handleToggle = useCallback((id: string) => {
    setLayers((prev) =>
      prev.map((l) => (l.id === id ? { ...l, enabled: !l.enabled } : l))
    )
  }, [])

  const deckLayers = useMemo(() => {
    const result = []

    const municipalitiesLayer = layers.find((l) => l.id === 'municipalities')
    if (municipalitiesLayer?.enabled && geoData.municipalities) {
      result.push(
        new GeoJsonLayer({
          id: 'municipalities',
          data: geoData.municipalities,
          stroked: true,
          filled: true,
          getFillColor: [61, 189, 111, 30],
          getLineColor: [61, 189, 111, 200],
          getLineWidth: 2,
          lineWidthUnits: 'pixels',
          pickable: true,
        })
      )
    }

    const floodLayer = layers.find((l) => l.id === 'flood_zones')
    if (floodLayer?.enabled && geoData.flood_zones) {
      result.push(
        new GeoJsonLayer({
          id: 'flood_zones',
          data: geoData.flood_zones,
          stroked: false,
          filled: true,
          getFillColor: [74, 127, 255, 80],
          pickable: true,
        })
      )
    }

    const zoningLayer = layers.find((l) => l.id === 'zoning')
    if (zoningLayer?.enabled && geoData.zoning) {
      result.push(
        new GeoJsonLayer({
          id: 'zoning',
          data: geoData.zoning,
          stroked: false,
          filled: true,
          getFillColor: [124, 92, 191, 50],
          pickable: true,
        })
      )
    }

    const penndotLayer = layers.find((l) => l.id === 'penndot_projects')
    if (penndotLayer?.enabled && geoData.penndot_projects) {
      result.push(
        new GeoJsonLayer({
          id: 'penndot_projects',
          data: geoData.penndot_projects,
          stroked: false,
          filled: true,
          getFillColor: [255, 165, 0, 200],
          getPointRadius: 6,
          pointRadiusUnits: 'pixels',
          pickable: true,
        })
      )
    }

    return result
  }, [layers, geoData])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      <Nav />
      <div style={{ position: 'relative', flex: 1 }}>
        <Link
          to="/"
          style={{
            position: 'absolute',
            top: 16,
            left: 16,
            zIndex: 10,
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            padding: '6px 12px',
            background: 'var(--bg-panel)',
            border: '1px solid var(--border)',
            borderRadius: 6,
            fontFamily: 'var(--font-mono)',
            fontSize: 12,
            color: 'var(--text-secondary)',
            textDecoration: 'none',
            transition: 'color 0.15s, border-color 0.15s',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.color = 'var(--text-primary)'
            e.currentTarget.style.borderColor = 'var(--border-active)'
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.color = 'var(--text-secondary)'
            e.currentTarget.style.borderColor = 'var(--border)'
          }}
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path
              d="M9 2L4 7L9 12"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          Back to Home
        </Link>

        <LayerToggle layers={layers} onToggle={handleToggle} />

        <DeckGL
          initialViewState={INITIAL_VIEW_STATE}
          controller={true}
          layers={deckLayers}
          style={{ position: 'absolute', inset: 0 }}
        >
          <Map
            mapStyle={BASEMAP}
            style={{ width: '100%', height: '100%' }}
          />
        </DeckGL>
      </div>
    </div>
  )
}
