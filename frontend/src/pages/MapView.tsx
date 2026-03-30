import { useState, useEffect, useCallback, useMemo } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import { Map } from 'react-map-gl/maplibre'
import { DeckGL } from '@deck.gl/react'
import { GeoJsonLayer } from '@deck.gl/layers'
import type { PickingInfo } from '@deck.gl/core'
import Nav from '../components/Nav'
import LayerToggle, { type LayerConfig } from '../components/LayerToggle'

// Zoning color map by gen_zcode
const ZONING_COLORS: Record<string, [number, number, number, number]> = {
  'LDR':   [72, 187, 120, 100],   // green — low density residential
  'MDR':   [129, 178, 210, 100],   // light blue — medium density
  'HDR':   [66, 135, 245, 100],    // blue — high density
  'R':     [104, 159, 56, 100],    // olive — rural
  'RP':    [56, 142, 60, 100],     // dark green — resource protection
  'Cv/OS': [27, 94, 32, 100],      // forest green — conservation
  'I':     [158, 118, 66, 120],    // brown — industrial
  'HC':    [255, 152, 0, 100],     // orange — highway commercial
  'NC':    [255, 193, 7, 100],     // yellow — neighborhood commercial
  'MU':    [171, 71, 188, 100],    // purple — mixed use
}
const ZONING_DEFAULT: [number, number, number, number] = [124, 92, 191, 50]

const BASEMAP = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json'

const DEFAULT_VIEW = {
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

  const initialViewState = useMemo(() => {
    const lat = searchParams.get('lat')
    const lng = searchParams.get('lng')
    const zoom = searchParams.get('zoom')
    if (lat && lng) {
      return {
        ...DEFAULT_VIEW,
        latitude: parseFloat(lat),
        longitude: parseFloat(lng),
        zoom: zoom ? parseFloat(zoom) : 16,
      }
    }
    return DEFAULT_VIEW
  }, [searchParams])

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

  const [hoverInfo, setHoverInfo] = useState<PickingInfo | null>(null)

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
          lineWidthUnits: 'pixels' as const,
          pickable: true,
          onHover: (info: PickingInfo) => setHoverInfo(info.object ? info : null),
          autoHighlight: true,
          highlightColor: [61, 189, 111, 60],
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
          onHover: (info: PickingInfo) => setHoverInfo(info.object ? info : null),
          autoHighlight: true,
          highlightColor: [74, 127, 255, 120],
        })
      )
    }

    const zoningLayer = layers.find((l) => l.id === 'zoning')
    if (zoningLayer?.enabled && geoData.zoning) {
      result.push(
        new GeoJsonLayer({
          id: 'zoning',
          data: geoData.zoning,
          stroked: true,
          filled: true,
          getFillColor: (f: any) => {
            const code = f.properties?.gen_zcode ?? ''
            return ZONING_COLORS[code] ?? ZONING_DEFAULT
          },
          getLineColor: [255, 255, 255, 30],
          getLineWidth: 1,
          lineWidthUnits: 'pixels' as const,
          pickable: true,
          onHover: (info: PickingInfo) => setHoverInfo(info.object ? info : null),
          autoHighlight: true,
          highlightColor: [255, 255, 255, 40],
        })
      )
    }

    const penndotLayer = layers.find((l) => l.id === 'penndot_projects')
    if (penndotLayer?.enabled && geoData.penndot_projects) {
      result.push(
        new GeoJsonLayer({
          id: 'penndot_projects',
          data: geoData.penndot_projects,
          stroked: true,
          filled: true,
          getFillColor: [255, 165, 0, 200],
          getLineColor: [255, 165, 0, 255],
          getLineWidth: 3,
          lineWidthUnits: 'pixels' as const,
          getPointRadius: 8,
          pointRadiusUnits: 'pixels' as const,
          pickable: true,
          onHover: (info: PickingInfo) => setHoverInfo(info.object ? info : null),
          autoHighlight: true,
          highlightColor: [255, 200, 50, 100],
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
          initialViewState={initialViewState}
          controller={true}
          layers={deckLayers}
          style={{ position: 'absolute', inset: 0 }}
        >
          <Map
            mapStyle={BASEMAP}
            style={{ width: '100%', height: '100%' }}
          />
        </DeckGL>

        {/* Hover tooltip */}
        {hoverInfo?.object && hoverInfo.x != null && hoverInfo.y != null && (
          <div
            style={{
              position: 'absolute',
              left: hoverInfo.x + 12,
              top: hoverInfo.y + 12,
              background: 'var(--bg-panel)',
              border: '1px solid var(--border)',
              borderRadius: 6,
              padding: '10px 14px',
              pointerEvents: 'none',
              zIndex: 20,
              maxWidth: 320,
              boxShadow: '0 4px 12px rgba(0,0,0,0.4)',
            }}
          >
            <MapTooltip properties={hoverInfo.object.properties} />
          </div>
        )}
      </div>
    </div>
  )
}

function MapTooltip({ properties }: { properties: Record<string, any> }) {
  // PennDOT project
  if (properties.project_name) {
    return (
      <div style={{ fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--text-primary)' }}>
        <div style={{ fontWeight: 600, marginBottom: 4 }}>{properties.project_name}</div>
        {properties.description && (
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 4, lineHeight: 1.4 }}>
            {properties.description.length > 150 ? properties.description.slice(0, 150) + '...' : properties.description}
          </div>
        )}
        <div style={{ display: 'flex', gap: 12, fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
          {properties.status && <span style={{ color: 'var(--accent-green)' }}>{properties.status}</span>}
          {properties.municipality && <span>{properties.municipality}</span>}
        </div>
      </div>
    )
  }

  // Zoning
  if (properties.gen_zname || properties.zname) {
    return (
      <div style={{ fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--text-primary)' }}>
        <div style={{ fontWeight: 600, marginBottom: 2 }}>{properties.zname || properties.gen_zname}</div>
        <div style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
          {properties.gen_zcode && <span style={{ marginRight: 8 }}>{properties.gen_zcode}</span>}
          {properties.muni_name && <span>{properties.muni_name}</span>}
        </div>
      </div>
    )
  }

  // Municipality
  if (properties.muni_type) {
    return (
      <div style={{ fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--text-primary)' }}>
        <div style={{ fontWeight: 600 }}>{properties.name}</div>
        <div style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>{properties.muni_type}</div>
      </div>
    )
  }

  // Flood zone
  if (properties.fld_zone) {
    return (
      <div style={{ fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--text-primary)' }}>
        <div style={{ fontWeight: 600 }}>Zone {properties.fld_zone}</div>
        {properties.zone_subty && <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{properties.zone_subty}</div>}
        <div style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
          SFHA: {properties.sfha_tf === 'T' ? 'Yes' : 'No'}
        </div>
      </div>
    )
  }

  return null
}
