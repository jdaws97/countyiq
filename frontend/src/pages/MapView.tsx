import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import { Map } from 'react-map-gl/maplibre'
import { DeckGL } from '@deck.gl/react'
import { GeoJsonLayer } from '@deck.gl/layers'
import type { PickingInfo, MapViewState } from '@deck.gl/core'
import Nav from '../components/Nav'
import LayerToggle, { type LayerConfig } from '../components/LayerToggle'

// ---------- Types ----------

interface ParcelProperties {
  pidn: string
  owner_full: string
  propadr: string
  aprtotal: number | null
  municipality: string
  class: string
  saledt: string | null
  price: number | null
  delinquent_total: number | null
  years_delinquent: number | null
}

interface PropertyReport {
  parcel: Record<string, any>
  tax_delinquency: {
    is_delinquent: boolean
    total_owed: number
    records: Array<{ year: number; amount: number; status: string }>
  }
  flood_zone: {
    in_flood_zone: boolean
    zone: string | null
    sfha: boolean
  }
  structures: {
    count: number
    likely_vacant: boolean
  }
}

// ---------- Constants ----------

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

const MIN_PARCEL_ZOOM = 13

const LAYER_DEFS: { id: string; name: string; color: string; defaultOn: boolean }[] = [
  { id: 'parcels', name: 'Parcels', color: '#60a5fa', defaultOn: true },
  { id: 'municipalities', name: 'Municipalities', color: '#3dbd6f', defaultOn: true },
  { id: 'flood_zones', name: 'Flood Zones', color: '#4a7fff', defaultOn: false },
  { id: 'zoning', name: 'Zoning', color: '#7c5cbf', defaultOn: false },
  { id: 'penndot_projects', name: 'PennDOT Projects', color: '#ffa500', defaultOn: false },
]

// Layers that come from static /api/layers/ endpoint (not parcels)
const STATIC_LAYER_IDS = ['municipalities', 'flood_zones', 'zoning', 'penndot_projects']

const URL_LAYER_MAP: Record<string, string> = {
  flood: 'flood_zones',
  penndot: 'penndot_projects',
  vacant: 'parcels',
  delinquent: 'parcels',
}

// ---------- Component ----------

export default function MapView() {
  const [searchParams] = useSearchParams()

  const initialViewState = useMemo(() => {
    const lat = searchParams.get('lat')
    const lng = searchParams.get('lng')
    const zoom = searchParams.get('zoom')
    const layer = searchParams.get('layer')
    if (lat && lng) {
      return {
        ...DEFAULT_VIEW,
        latitude: parseFloat(lat),
        longitude: parseFloat(lng),
        zoom: zoom ? parseFloat(zoom) : 16,
      }
    }
    // Auto-zoom in for parcel-dependent layers
    if (layer === 'vacant' || layer === 'delinquent') {
      return { ...DEFAULT_VIEW, zoom: 14 }
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

  const [parcelFilter, setParcelFilter] = useState<'all' | 'delinquent' | 'vacant' | 'vacant_delinquent'>(
    () => {
      const layer = searchParams.get('layer')
      if (layer === 'vacant') return 'vacant'
      if (layer === 'delinquent') return 'delinquent'
      return 'all'
    }
  )

  const [geoData, setGeoData] = useState<Record<string, GeoJSON.FeatureCollection>>({})
  const [parcelData, setParcelData] = useState<GeoJSON.FeatureCollection | null>(null)
  const [currentZoom, setCurrentZoom] = useState(initialViewState.zoom)
  const [hoverInfo, setHoverInfo] = useState<PickingInfo | null>(null)

  // Property report card
  const [selectedPidn, setSelectedPidn] = useState<string | null>(null)
  const [propertyReport, setPropertyReport] = useState<PropertyReport | null>(null)
  const [reportLoading, setReportLoading] = useState(false)
  const [panelOpen, setPanelOpen] = useState(false)

  // Debounce refs for parcel fetching
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const viewStateRef = useRef<MapViewState | null>(null)

  // Load static layers
  useEffect(() => {
    STATIC_LAYER_IDS.forEach((id) => {
      fetch(`/api/layers/${id}`)
        .then((r) => {
          if (!r.ok) throw new Error(`${r.status}`)
          return r.json()
        })
        .then((data) => {
          setGeoData((prev) => ({ ...prev, [id]: data }))
        })
        .catch(() => {
          // Layer data unavailable -- leave empty
        })
    })
  }, [])

  // Fetch parcels on viewport change (debounced)
  const fetchParcels = useCallback((vs: MapViewState) => {
    if (!vs || vs.zoom < MIN_PARCEL_ZOOM) {
      setParcelData(null)
      return
    }

    // Approximate bbox from center + zoom
    // At zoom 13, roughly 0.05 degrees visible; scale by zoom level
    const degPerPixel = 360 / (512 * Math.pow(2, vs.zoom))
    // Assume ~1000px viewport width/height as reasonable estimate
    const halfW = degPerPixel * 600
    const halfH = degPerPixel * 400

    const west = vs.longitude - halfW
    const east = vs.longitude + halfW
    const south = vs.latitude - halfH
    const north = vs.latitude + halfH

    const bboxLayer = (parcelFilter === 'vacant' || parcelFilter === 'vacant_delinquent') ? 'vacant' : 'delinquent'
    const url = `/api/parcels/bbox?west=${west.toFixed(6)}&south=${south.toFixed(6)}&east=${east.toFixed(6)}&north=${north.toFixed(6)}&layer=${bboxLayer}`

    fetch(url)
      .then((r) => {
        if (!r.ok) throw new Error(`${r.status}`)
        return r.json()
      })
      .then((data: GeoJSON.FeatureCollection) => {
        if (parcelFilter === 'vacant_delinquent') {
          data.features = data.features.filter(
            (f: any) => f.properties?.delinquent_total && parseFloat(f.properties.delinquent_total) > 0
          )
        }
        setParcelData(data)
      })
      .catch(() => {
        // Parcel data unavailable
      })
  }, [parcelFilter])

  const onViewStateChange = useCallback(
    ({ viewState }: { viewState: MapViewState }) => {
      viewStateRef.current = viewState
      setCurrentZoom(viewState.zoom)

      // Clear hover/selection when zooming out past parcel threshold
      if (viewState.zoom < MIN_PARCEL_ZOOM) {
        setHoverInfo(null)
        setSelectedPidn(null)
        setPropertyReport(null)
      }

      if (debounceRef.current) clearTimeout(debounceRef.current)
      debounceRef.current = setTimeout(() => {
        const parcelsEnabled = layers.find((l) => l.id === 'parcels')?.enabled
        if (parcelsEnabled && viewStateRef.current) {
          fetchParcels(viewStateRef.current)
        }
      }, 300)
    },
    [fetchParcels, layers]
  )

  // Fetch parcels on mount and when filter changes
  useEffect(() => {
    const parcelsEnabled = layers.find((l) => l.id === 'parcels')?.enabled
    const vs = viewStateRef.current || initialViewState
    if (parcelsEnabled && (vs.zoom ?? 0) >= MIN_PARCEL_ZOOM) {
      fetchParcels(vs as MapViewState)
    }
  }, [parcelFilter]) // eslint-disable-line react-hooks/exhaustive-deps

  // Fetch property report when a parcel is clicked
  useEffect(() => {
    if (!selectedPidn) {
      setPanelOpen(false)
      setPropertyReport(null)
      return
    }

    setReportLoading(true)
    setPanelOpen(true)

    fetch(`/api/parcels/${selectedPidn}`)
      .then((r) => {
        if (!r.ok) throw new Error(`${r.status}`)
        return r.json()
      })
      .then((data: PropertyReport) => {
        setPropertyReport(data)
        setReportLoading(false)
      })
      .catch(() => {
        setReportLoading(false)
      })
  }, [selectedPidn])

  const handleToggle = useCallback((id: string) => {
    setLayers((prev) =>
      prev.map((l) => (l.id === id ? { ...l, enabled: !l.enabled } : l))
    )
  }, [])

  const handleParcelClick = useCallback((info: PickingInfo) => {
    const pidn = info.object?.properties?.pidn
    if (pidn) {
      setSelectedPidn(pidn)
    }
  }, [])

  const closePanel = useCallback(() => {
    setSelectedPidn(null)
    setPanelOpen(false)
    setPropertyReport(null)
  }, [])

  const deckLayers = useMemo(() => {
    const result = []

    // Parcels layer (rendered first so it's below other layers)
    const parcelsLayer = layers.find((l) => l.id === 'parcels')
    if (parcelsLayer?.enabled && parcelData && currentZoom >= MIN_PARCEL_ZOOM) {
      result.push(
        new GeoJsonLayer({
          id: 'parcels',
          data: parcelData,
          stroked: true,
          filled: true,
          getFillColor: (f: any) => {
            if (parcelFilter === 'vacant') return [61, 189, 111, 120]
            const delinquent = f.properties?.delinquent_total
            if (delinquent && delinquent > 0) return [224, 82, 82, 120]
            return [96, 165, 250, 40]
          },
          getLineColor: parcelFilter === 'vacant' ? [61, 189, 111, 150] as any : [96, 165, 250, 100] as any,
          getLineWidth: 1,
          lineWidthUnits: 'pixels' as const,
          pickable: true,
          onHover: (info: PickingInfo) => setHoverInfo(info.object ? info : null),
          onClick: handleParcelClick,
          autoHighlight: true,
          highlightColor: [255, 255, 255, 60],
          updateTriggers: {
            getFillColor: [parcelData],
          },
        })
      )
    }

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
  }, [layers, geoData, parcelData, currentZoom, handleParcelClick, parcelFilter])

  const parcelsEnabled = layers.find((l) => l.id === 'parcels')?.enabled
  const showZoomMessage = parcelsEnabled && currentZoom < MIN_PARCEL_ZOOM

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

        {/* Parcel Filter Bar */}
        {currentZoom >= MIN_PARCEL_ZOOM && (
          <div style={{
            position: 'absolute', bottom: 24, left: '50%', transform: 'translateX(-50%)',
            zIndex: 10, display: 'flex', gap: 2,
            background: 'var(--bg-panel)', border: '1px solid var(--border)',
            borderRadius: 8, padding: 4, boxShadow: '0 4px 16px rgba(0,0,0,0.4)',
          }}>
            {([
              { key: 'all', label: 'All Parcels', color: 'var(--accent-blue)' },
              { key: 'delinquent', label: 'Delinquent', color: 'var(--accent-red)' },
              { key: 'vacant', label: 'Vacant', color: 'var(--accent-green)' },
              { key: 'vacant_delinquent', label: 'Vacant + Delinquent', color: 'var(--accent-gold)' },
            ] as const).map(f => (
              <button key={f.key} onClick={() => { setParcelFilter(f.key); setParcelData(null) }} style={{
                padding: '6px 14px', borderRadius: 6, border: 'none', cursor: 'pointer',
                fontFamily: 'var(--font-mono)', fontSize: 11, letterSpacing: 0.5,
                background: parcelFilter === f.key ? f.color : 'transparent',
                color: parcelFilter === f.key ? '#0a0e1a' : 'var(--text-secondary)',
                fontWeight: parcelFilter === f.key ? 700 : 400,
                transition: 'all 0.15s',
              }}>
                {f.label}
              </button>
            ))}
          </div>
        )}

        {/* Legend */}
        {currentZoom >= MIN_PARCEL_ZOOM && (
          <div style={{
            position: 'absolute', bottom: 24, left: 16, zIndex: 10,
            background: 'var(--bg-panel)', border: '1px solid var(--border)',
            borderRadius: 6, padding: '8px 12px', boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
            fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
              <span style={{ width: 10, height: 10, borderRadius: 2, background: 'rgba(96,165,250,0.5)' }} />
              Normal Parcel
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
              <span style={{ width: 10, height: 10, borderRadius: 2, background: 'rgba(224,82,82,0.7)' }} />
              Tax Delinquent
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ width: 10, height: 10, borderRadius: 2, background: 'rgba(61,189,111,0.7)' }} />
              Vacant Land
            </div>
          </div>
        )}

        {/* Zoom-in message */}
        {showZoomMessage && (
          <div
            style={{
              position: 'absolute',
              bottom: 32,
              left: '50%',
              transform: 'translateX(-50%)',
              zIndex: 10,
              background: 'var(--bg-panel)',
              border: '1px solid var(--border)',
              borderRadius: 8,
              padding: '8px 18px',
              fontFamily: 'var(--font-mono)',
              fontSize: 12,
              color: 'var(--text-secondary)',
              boxShadow: '0 4px 16px rgba(0,0,0,0.4)',
              letterSpacing: 0.3,
            }}
          >
            Zoom in to see parcels
          </div>
        )}

        <DeckGL
          initialViewState={initialViewState}
          controller={true}
          layers={deckLayers}
          onViewStateChange={onViewStateChange as any}
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

        {/* Property Report Card Side Panel */}
        <div
          style={{
            position: 'absolute',
            top: 0,
            right: 0,
            bottom: 0,
            width: 320,
            zIndex: 25,
            background: 'var(--bg-panel)',
            borderLeft: '1px solid var(--border)',
            boxShadow: '-4px 0 24px rgba(0,0,0,0.5)',
            transform: panelOpen ? 'translateX(0)' : 'translateX(100%)',
            transition: 'transform 0.3s ease',
            overflowY: 'auto',
            overflowX: 'hidden',
          }}
        >
          {panelOpen && (
            <PropertyPanel
              report={propertyReport}
              loading={reportLoading}
              onClose={closePanel}
            />
          )}
        </div>
      </div>
    </div>
  )
}

// ---------- Property Report Card Panel ----------

const SCHOOL_DISTRICTS: Record<string, string> = {
  '002': 'Central York', '004': 'Dallastown', '006': 'Dover',
  '008': 'Eastern York', '010': 'Hanover', '012': 'Northeastern',
  '014': 'Northern York', '016': 'Red Lion', '018': 'South Eastern',
  '020': 'South Western', '022': 'Southern York', '024': 'Spring Grove',
  '026': 'West Shore', '028': 'West York', '030': 'York Suburban',
  '17F': 'York City', '17G': 'York City', '17L': 'York City', '17N': 'York City',
}

const CLASS_NAMES: Record<string, string> = {
  'R': 'Residential', 'C': 'Commercial', 'I': 'Industrial',
  'F': 'Farm', 'E': 'Exempt', 'A': 'Agricultural', 'U': 'Utility',
}

function PropertyPanel({
  report,
  loading,
  onClose,
}: {
  report: PropertyReport | null
  loading: boolean
  onClose: () => void
}) {
  if (loading) {
    return (
      <div style={{ padding: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <CloseButton onClick={onClose} />
        </div>
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 12,
            color: 'var(--text-muted)',
            marginTop: 40,
            textAlign: 'center',
            animation: 'pulse 1.5s ease-in-out infinite',
          }}
        >
          Loading property data...
        </div>
      </div>
    )
  }

  if (!report) {
    return (
      <div style={{ padding: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <CloseButton onClick={onClose} />
        </div>
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 12,
            color: 'var(--text-muted)',
            marginTop: 40,
            textAlign: 'center',
          }}
        >
          Property data unavailable
        </div>
      </div>
    )
  }

  const { parcel: p, tax_delinquency: tax, flood_zone: flood, structures } = report

  return (
    <div style={{ padding: 20 }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              fontFamily: 'var(--font-sans)',
              fontSize: 17,
              fontWeight: 700,
              color: 'var(--text-primary)',
              lineHeight: 1.3,
              marginBottom: 4,
            }}
          >
            {p.owner_full || 'Unknown Owner'}
          </div>
          <div
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 12,
              color: 'var(--text-secondary)',
              lineHeight: 1.4,
            }}
          >
            {p.propadr || 'No address'}
          </div>
          {p.municipality && (
            <span
              style={{
                display: 'inline-block',
                marginTop: 8,
                padding: '2px 10px',
                background: 'rgba(96, 165, 250, 0.15)',
                border: '1px solid rgba(96, 165, 250, 0.3)',
                borderRadius: 100,
                fontFamily: 'var(--font-mono)',
                fontSize: 10,
                fontWeight: 500,
                color: '#60a5fa',
                letterSpacing: 0.5,
              }}
            >
              {p.municipality}
            </span>
          )}
        </div>
        <CloseButton onClick={onClose} />
      </div>

      <Divider />

      {/* Assessment & Sale */}
      <SectionTitle>Assessment & Sale</SectionTitle>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px 16px' }}>
        <DataField label="Assessed Total" value={fmtDollar(p.aprtotal)} accent />
        <DataField label="Acres" value={p.acres ? Number(p.acres).toFixed(2) : '--'} />
        <DataField label="Sale Date" value={p.saledt || '--'} />
        <DataField label="Sale Price" value={fmtDollar(p.price)} />
        {p.prev_price && <DataField label="Prev Price" value={fmtDollar(p.prev_price)} />}
        <DataField label="Class" value={CLASS_NAMES[p.class] || p.class || '--'} />
      </div>
      {(p.aprland || p.aprbldg) && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px 16px', marginTop: 8 }}>
          <DataField label="Land" value={fmtDollar(p.aprland)} />
          <DataField label="Building" value={fmtDollar(p.aprbldg)} />
        </div>
      )}

      {/* Property Details — only show if we have data beyond the basics */}
      {(p.yrblt || p.style || p.num_stories || p.res_living_area || p.luc) && (
        <>
          <Divider />
          <SectionTitle>Property Details</SectionTitle>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px 16px' }}>
            {p.yrblt && <DataField label="Year Built" value={p.yrblt} />}
            {p.style && <DataField label="Style" value={p.style} />}
            {p.num_stories && <DataField label="Stories" value={p.num_stories} />}
            {p.res_living_area && <DataField label="Living Area" value={`${Number(p.res_living_area).toLocaleString()} sf`} />}
            {p.luc && <DataField label="LUC" value={p.luc} />}
            {p.heatsys && <DataField label="Heat" value={p.heatsys} />}
          </div>
        </>
      )}

      {/* School District + Deed */}
      {(p.school_dis || p.deed_bk) && (
        <>
          <Divider />
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px 16px' }}>
            {p.school_dis && <DataField label="School District" value={SCHOOL_DISTRICTS[p.school_dis] || p.school_dis} />}
            {p.deed_bk && <DataField label="Deed" value={`${p.deed_bk}/${p.deed_pg}`} />}
          </div>
        </>
      )}

      <Divider />

      {/* Tax Status */}
      <SectionTitle>Tax Status</SectionTitle>
      {tax.is_delinquent ? (
        <div>
          <span
            style={{
              display: 'inline-block',
              padding: '3px 10px',
              background: 'rgba(224, 82, 82, 0.15)',
              border: '1px solid rgba(224, 82, 82, 0.3)',
              borderRadius: 4,
              fontFamily: 'var(--font-mono)',
              fontSize: 12,
              fontWeight: 600,
              color: 'var(--accent-red)',
            }}
          >
            Delinquent &mdash; {fmtDollar(tax.total_owed)}
          </span>
          {tax.records && tax.records.length > 0 && (
            <div style={{ marginTop: 10 }}>
              {tax.records.map((rec) => (
                <div
                  key={rec.year}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    padding: '4px 0',
                    borderBottom: '1px solid var(--border)',
                    fontFamily: 'var(--font-mono)',
                    fontSize: 11,
                  }}
                >
                  <span style={{ color: 'var(--text-secondary)' }}>{rec.year}</span>
                  <span style={{ color: 'var(--accent-red)' }}>{fmtDollar(rec.amount)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : (
        <span
          style={{
            display: 'inline-block',
            padding: '3px 10px',
            background: 'rgba(61, 189, 111, 0.15)',
            border: '1px solid rgba(61, 189, 111, 0.3)',
            borderRadius: 4,
            fontFamily: 'var(--font-mono)',
            fontSize: 12,
            fontWeight: 600,
            color: 'var(--accent-green)',
          }}
        >
          Current
        </span>
      )}

      <Divider />

      {/* Flood Risk */}
      <SectionTitle>Flood Risk</SectionTitle>
      {flood.in_flood_zone ? (
        <div>
          <span
            style={{
              display: 'inline-block',
              padding: '3px 10px',
              background: 'rgba(74, 127, 255, 0.15)',
              border: '1px solid rgba(74, 127, 255, 0.3)',
              borderRadius: 4,
              fontFamily: 'var(--font-mono)',
              fontSize: 12,
              fontWeight: 500,
              color: 'var(--accent-blue)',
            }}
          >
            Zone {flood.zone}
          </span>
          {flood.sfha && (
            <span
              style={{
                display: 'inline-block',
                marginLeft: 8,
                fontFamily: 'var(--font-mono)',
                fontSize: 10,
                color: 'var(--accent-gold)',
              }}
            >
              SFHA
            </span>
          )}
        </div>
      ) : (
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 12,
            color: 'var(--text-muted)',
          }}
        >
          Not in flood zone
        </div>
      )}

      <Divider />

      {/* Structures */}
      <SectionTitle>Structures</SectionTitle>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <DataField label="Count" value={String(structures.count)} />
        {structures.likely_vacant && (
          <span
            style={{
              padding: '2px 8px',
              background: 'rgba(212, 168, 67, 0.15)',
              border: '1px solid rgba(212, 168, 67, 0.3)',
              borderRadius: 4,
              fontFamily: 'var(--font-mono)',
              fontSize: 10,
              fontWeight: 600,
              color: 'var(--accent-gold)',
            }}
          >
            Likely Vacant
          </span>
        )}
      </div>

      {/* PIDN footer */}
      <div
        style={{
          marginTop: 20,
          paddingTop: 12,
          borderTop: '1px solid var(--border)',
          fontFamily: 'var(--font-mono)',
          fontSize: 10,
          color: 'var(--text-muted)',
          letterSpacing: 0.5,
        }}
      >
        PIDN: {report.parcel.pidn}
      </div>
      <Link to={`/property/${report.parcel.pidn}`} style={{
        display: 'block', textAlign: 'center', marginTop: 12,
        padding: '8px', borderRadius: 4,
        fontFamily: 'var(--font-mono)', fontSize: 11,
        color: 'var(--accent-blue)', border: '1px solid var(--border)',
        textDecoration: 'none',
      }}>
        View Full Property Report &rarr;
      </Link>
    </div>
  )
}

// ---------- Panel Sub-components ----------

function CloseButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        background: 'none',
        border: '1px solid var(--border)',
        borderRadius: 4,
        width: 28,
        height: 28,
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: 'var(--text-muted)',
        flexShrink: 0,
        transition: 'color 0.15s, border-color 0.15s',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.color = 'var(--text-primary)'
        e.currentTarget.style.borderColor = 'var(--border-active)'
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.color = 'var(--text-muted)'
        e.currentTarget.style.borderColor = 'var(--border)'
      }}
    >
      <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
        <path d="M2 2L10 10M10 2L2 10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    </button>
  )
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        fontFamily: 'var(--font-mono)',
        fontSize: 10,
        fontWeight: 600,
        letterSpacing: 1.5,
        textTransform: 'uppercase',
        color: 'var(--text-muted)',
        marginBottom: 8,
      }}
    >
      {children}
    </div>
  )
}

function DataField({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div>
      <div
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 9,
          color: 'var(--text-muted)',
          letterSpacing: 0.5,
          marginBottom: 2,
          textTransform: 'uppercase',
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 13,
          color: accent ? 'var(--text-primary)' : 'var(--text-secondary)',
          fontWeight: accent ? 600 : 400,
        }}
      >
        {value}
      </div>
    </div>
  )
}

function Divider() {
  return (
    <div
      style={{
        height: 1,
        background: 'var(--border)',
        margin: '14px 0',
      }}
    />
  )
}

// ---------- Formatters ----------

function fmtDollar(val: number | string | null | undefined): string {
  if (val == null) return '--'
  const n = typeof val === 'string' ? parseFloat(val) : val
  if (isNaN(n)) return '--'
  return '$' + n.toLocaleString('en-US', { maximumFractionDigits: 0 })
}

function fmtDate(d: string | null | undefined): string {
  if (!d) return '--'
  try {
    return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
  } catch {
    return d
  }
}

function formatCost(cost: number | null): string {
  if (!cost) return ''
  if (cost >= 1_000_000) return `$${(cost / 1_000_000).toFixed(1)}M`
  if (cost >= 1_000) return `$${(cost / 1_000).toFixed(0)}K`
  return `$${cost.toLocaleString()}`
}

function formatDate(d: string | null): string {
  if (!d) return ''
  try {
    return new Date(d).toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
  } catch { return d }
}

// ---------- Map Tooltip ----------

function MapTooltip({ properties }: { properties: Record<string, any> }) {
  // Parcel tooltip
  if (properties.pidn) {
    return (
      <div style={{ fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--text-primary)' }}>
        <div style={{ fontWeight: 600, marginBottom: 2 }}>{properties.owner_full || 'Unknown Owner'}</div>
        <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 4 }}>
          {properties.propadr || 'No address'}
        </div>
        {properties.aprtotal != null && (
          <div style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--accent-blue)' }}>
            {fmtDollar(properties.aprtotal)}
          </div>
        )}
      </div>
    )
  }

  // PennDOT project
  if (properties.project_name) {
    const statusColor = properties.under_construction === 'Y' ? 'var(--accent-gold)' : 'var(--accent-green)'
    const statusLabel = properties.act89_status || properties.status || ''
    return (
      <div style={{ fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--text-primary)' }}>
        <div style={{ fontWeight: 600, marginBottom: 4 }}>{properties.project_name}</div>
        {properties.location_desc && (
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6, lineHeight: 1.4 }}>
            {properties.location_desc}
          </div>
        )}
        {!properties.location_desc && properties.description && (
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6, lineHeight: 1.4 }}>
            {properties.description}
          </div>
        )}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px 14px', fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', marginBottom: 4 }}>
          <span style={{ color: statusColor, fontWeight: 600 }}>{statusLabel}</span>
          {properties.project_type && <span>{properties.project_type}</span>}
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px 14px', fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
          {properties.start_date && <span>Start: {formatDate(properties.start_date)}</span>}
          {properties.end_date && <span>End: {formatDate(properties.end_date)}</span>}
          {properties.cost && <span style={{ color: 'var(--accent-blue)' }}>{formatCost(properties.cost)}</span>}
        </div>
        {properties.project_manager && (
          <div style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', marginTop: 6, borderTop: '1px solid var(--border)', paddingTop: 6 }}>
            PM: {properties.project_manager}
          </div>
        )}
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
