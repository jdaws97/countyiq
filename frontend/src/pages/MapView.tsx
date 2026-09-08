import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import { Map, NavigationControl } from 'react-map-gl/maplibre'
import { DeckGL } from '@deck.gl/react'
import { GeoJsonLayer, ScatterplotLayer } from '@deck.gl/layers'
import type { PickingInfo, MapViewState } from '@deck.gl/core'
import type { Feature, Geometry } from 'geojson'
import LayerToggle, { type LayerConfig } from '../components/LayerToggle'
import WorkspaceShell from '../components/WorkspaceShell'
import { ButtonLink } from '../components/ui'
import { formatCurrency, formatCurrencyCompact, formatShortDate } from '../lib/format'
import { appendRadarCriteria, planStatusFor } from '../lib/radarFilters'
import EvidencePanel from '../components/EvidencePanel'
import { getPropertyClassLabel, getSchoolDistrictLabel } from '../lib/propertyLabels'
import { fitGeometry, splitBounds, urlView, visibleBounds, type MapSize } from '../lib/mapViewport'
import type {
  FloodZoneProperties,
  MunicipalityProperties,
  ParcelFeatureCollection,
  ParcelFeatureProperties,
  PenndotProjectProperties,
  ParcelSummary,
  RadarBboxItem,
  RadarBboxResponse,
  ZoningProperties,
} from '../types/api'

type RadarBasis = 'opportunity' | 'momentum' | 'readiness'
type ParcelFilter = 'all' | 'delinquent' | 'vacant' | 'vacant_delinquent' | 'radar'
interface RadarPoint {
  properties: {
    pidn: string
    radar_score: number
    top_signal: string | null
    radar_basis: RadarBasis
  }
  lng: number
  lat: number
}

type ParcelFeature = Feature<Geometry, ParcelFeatureProperties>
type ZoningFeature = Feature<Geometry, ZoningProperties>
type LoadStatus = 'idle' | 'loading' | 'ready' | 'error'
type ParcelMapData = ParcelFeatureCollection & {
  count?: number
  limit?: number
  truncated?: boolean
}
type TooltipProperties =
  | RadarPoint['properties']
  | ParcelFeatureProperties
  | PenndotProjectProperties
  | ZoningProperties
  | MunicipalityProperties
  | FloodZoneProperties

const ZONING_COLORS: Record<string, [number, number, number, number]> = {
  LDR: [72, 187, 120, 100], // green — low density residential
  MDR: [129, 178, 210, 100], // light blue — medium density
  HDR: [66, 135, 245, 100], // blue — high density
  R: [104, 159, 56, 100], // olive — rural
  RP: [56, 142, 60, 100], // dark green — resource protection
  'Cv/OS': [27, 94, 32, 100], // forest green — conservation
  I: [158, 118, 66, 120], // brown — industrial
  HC: [255, 152, 0, 100], // orange — highway commercial
  NC: [255, 193, 7, 100], // yellow — neighborhood commercial
  MU: [171, 71, 188, 100], // purple — mixed use
}
const ZONING_DEFAULT: [number, number, number, number] = [124, 92, 191, 50]

const BASEMAPS = {
  light: 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json',
  dark: 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json',
}

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

const STATIC_LAYER_IDS = ['municipalities', 'flood_zones', 'zoning', 'penndot_projects']

const URL_LAYER_MAP: Record<string, string> = {
  flood: 'flood_zones',
  zoning: 'zoning',
  penndot: 'penndot_projects',
  vacant: 'parcels',
  delinquent: 'parcels',
  radar: 'parcels',
}

const RADAR_MIN_ZOOM = 11
function radarColor(score: number): [number, number, number, number] {
  if (score >= 60) {
    return [61, 189, 111, 220]
  }
  if (score >= 40) {
    return [232, 181, 60, 220]
  }
  if (score >= 20) {
    return [96, 165, 250, 200]
  }
  return [148, 163, 184, 160]
}

export default function MapView() {
  const [searchParams] = useSearchParams()
  const [darkMap, setDarkMap] = useState(() => document.documentElement.dataset.theme === 'dark')
  useEffect(() => {
    const update = () => setDarkMap(document.documentElement.dataset.theme === 'dark')
    update()
    const observer = new MutationObserver(update)
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme'],
    })
    return () => observer.disconnect()
  }, [])

  const initialViewState = useMemo(() => {
    const layer = searchParams.get('layer')
    const linkedView = urlView(searchParams, DEFAULT_VIEW)
    if (linkedView !== DEFAULT_VIEW) {
      return linkedView
    }
    if (layer === 'vacant' || layer === 'delinquent') {
      return { ...DEFAULT_VIEW, zoom: 14 }
    }
    if (layer === 'radar') {
      return { ...DEFAULT_VIEW, zoom: 12 }
    }
    return DEFAULT_VIEW
  }, [searchParams])
  const [viewState, setViewState] = useState<MapViewState>(initialViewState)
  const [mapSize, setMapSize] = useState<MapSize>({ width: 1, height: 1 })

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

  const [highlightPidn, setHighlightPidn] = useState<string | null>(() =>
    searchParams.get('highlight'),
  )
  const parcelsEnabled = layers.find((layer) => layer.id === 'parcels')?.enabled
  const [parcelFilter, setParcelFilter] = useState<ParcelFilter>(() => {
    const layer = searchParams.get('layer')
    if (layer === 'vacant') {
      return 'vacant'
    }
    if (layer === 'delinquent') {
      return 'delinquent'
    }
    if (layer === 'radar') {
      return 'radar'
    }
    return 'all'
  })
  const [radarBasis] = useState<RadarBasis>(() =>
    searchParams.get('radar') === 'momentum'
      ? 'momentum'
      : searchParams.get('radar') === 'readiness'
        ? 'readiness'
        : 'opportunity',
  )
  const radarMinScore = searchParams.get('min_score') ?? '10'
  const radarMunicipality = searchParams.get('municipality') ?? ''
  const radarMinAcres = searchParams.get('min_acres') ?? ''
  const radarMaxAcres = searchParams.get('max_acres') ?? ''
  const radarParcelClass = searchParams.get('class') ?? ''
  const radarPlanStatus = planStatusFor(radarBasis, searchParams.get('plan_status'))
  const radarListParams = appendRadarCriteria(new URLSearchParams({ view: radarBasis }), {
    minScore: radarMinScore,
    municipality: radarMunicipality,
    minAcres: radarMinAcres,
    maxAcres: radarMaxAcres,
    parcelClass: radarParcelClass,
    planStatus: radarPlanStatus,
  })
  const [radarData, setRadarData] = useState<RadarPoint[] | null>(null)
  const [radarTruncated, setRadarTruncated] = useState(false)
  const [radarStatus, setRadarStatus] = useState<LoadStatus>('idle')

  const [geoData, setGeoData] = useState<Record<string, GeoJSON.FeatureCollection>>({})
  const [layerAvailability, setLayerAvailability] = useState<
    Record<string, Exclude<LoadStatus, 'idle'>>
  >({})
  const loadedLayers = useRef(new Set<string>())
  const enabledStaticLayers = layers
    .filter((layer) => layer.enabled && STATIC_LAYER_IDS.includes(layer.id))
    .map((layer) => layer.id)
    .join(',')
  const [parcelData, setParcelData] = useState<ParcelMapData | null>(null)
  const [parcelStatus, setParcelStatus] = useState<LoadStatus>('idle')
  const [currentZoom, setCurrentZoom] = useState(initialViewState.zoom)
  const [hoverInfo, setHoverInfo] = useState<PickingInfo | null>(null)

  const [selectedPidn, setSelectedPidn] = useState<string | null>(() =>
    searchParams.get('highlight'),
  )
  const [propertyReport, setPropertyReport] = useState<ParcelSummary | null>(null)
  const [reportLoading, setReportLoading] = useState(() => Boolean(searchParams.get('highlight')))
  const [reportFailed, setReportFailed] = useState(false)
  const panelOpen = selectedPidn !== null
  const adjacentPidns = useMemo(
    () =>
      new Set(
        (propertyReport?.source_explanation?.citation_evidence ?? [])
          .filter(
            (item) =>
              item.citation_key.includes(':adjacent_') && typeof item.details?.pidn === 'string',
          )
          .map((item) => String(item.details.pidn)),
      ),
    [propertyReport],
  )

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const viewStateRef = useRef<MapViewState | null>(null)
  const mapCanvasRef = useRef<HTMLDivElement | null>(null)
  const fittedHighlightRef = useRef<string | null>(null)
  const centeredHighlightRef = useRef<string | null>(null)
  const userNavigatedRef = useRef(false)
  const parcelRequestRef = useRef(0)
  const radarRequestRef = useRef(0)
  const parcelPendingKeyRef = useRef<string | null>(null)
  const radarPendingKeyRef = useRef<string | null>(null)
  const parcelLoadedKeyRef = useRef<string | null>(null)
  const radarLoadedKeyRef = useRef<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    enabledStaticLayers
      .split(',')
      .filter(Boolean)
      .forEach((id) => {
        if (loadedLayers.current.has(id)) {
          return
        }
        setLayerAvailability((prev) => ({ ...prev, [id]: 'loading' }))
        fetch(`/api/layers/${id}`, { signal: controller.signal })
          .then((r) => {
            if (!r.ok) {
              throw new Error(`${r.status}`)
            }
            return r.json()
          })
          .then((data) => {
            if (controller.signal.aborted) {
              return
            }
            loadedLayers.current.add(id)
            setGeoData((prev) => ({ ...prev, [id]: data }))
            setLayerAvailability((prev) => ({ ...prev, [id]: 'ready' }))
          })
          .catch(() => {
            if (!controller.signal.aborted) {
              setLayerAvailability((prev) => ({ ...prev, [id]: 'error' }))
              setLayers((prev) =>
                prev.map((layer) => (layer.id === id ? { ...layer, enabled: false } : layer)),
              )
            }
          })
      })
    return () => {
      controller.abort()
    }
  }, [enabledStaticLayers])

  const fetchRadar = useCallback(
    (vs: MapViewState) => {
      if (mapSize.width < 2 || mapSize.height < 2) {
        return
      }
      if (!vs || vs.zoom < RADAR_MIN_ZOOM) {
        ++radarRequestRef.current
        radarPendingKeyRef.current = null
        radarLoadedKeyRef.current = null
        setRadarData(null)
        setRadarTruncated(false)
        setRadarStatus('idle')
        return
      }
      const bounds = visibleBounds(vs, mapSize)
      const requestKey = [
        radarBasis,
        radarMinScore,
        radarMunicipality,
        radarMinAcres,
        radarMaxAcres,
        radarParcelClass,
        radarPlanStatus,
        bounds.west,
        bounds.south,
        bounds.east,
        bounds.north,
      ]
        .map((value) => (typeof value === 'number' ? value.toFixed(6) : value))
        .join(':')
      if (radarPendingKeyRef.current === requestKey || radarLoadedKeyRef.current === requestKey) {
        return
      }
      const requestId = ++radarRequestRef.current
      radarPendingKeyRef.current = requestKey
      radarLoadedKeyRef.current = null
      setRadarStatus('loading')
      const requests = splitBounds(bounds).map((bounds) => {
        const params = new URLSearchParams({
          west: bounds.west.toFixed(6),
          south: bounds.south.toFixed(6),
          east: bounds.east.toFixed(6),
          north: bounds.north.toFixed(6),
          view: radarBasis,
          min_score: radarMinScore,
        })
        if (radarMunicipality) {
          params.set('municipality', radarMunicipality)
        }
        if (radarMinAcres) {
          params.set('min_acres', radarMinAcres)
        }
        if (radarMaxAcres) {
          params.set('max_acres', radarMaxAcres)
        }
        if (radarParcelClass) {
          params.set('class', radarParcelClass)
        }
        params.set('plan_status', radarPlanStatus)
        return fetch(`/api/radar/development/bbox?${params}`).then((response) => {
          if (!response.ok) {
            throw new Error(`${response.status}`)
          }
          return response.json() as Promise<RadarBboxResponse>
        })
      })

      Promise.all(requests)
        .then((responses) => {
          if (requestId !== radarRequestRef.current) {
            return
          }
          const seen = new Set<string>()
          setRadarData(
            responses
              .flatMap((response) => response.parcels || [])
              .filter((item: RadarBboxItem) => item.lng != null && item.lat != null)
              .filter((item: RadarBboxItem) => {
                if (seen.has(item.pidn)) {
                  return false
                }
                seen.add(item.pidn)
                return true
              })
              .map((item: RadarBboxItem) => ({
                properties: {
                  pidn: item.pidn,
                  radar_score: Number(item.score),
                  top_signal: item.top_signal,
                  radar_basis: radarBasis,
                },
                lng: Number(item.lng),
                lat: Number(item.lat),
              })),
          )
          setRadarTruncated(responses.some((response) => response.truncated))
          radarLoadedKeyRef.current = requestKey
          setRadarStatus('ready')
        })
        .catch(() => {
          if (requestId === radarRequestRef.current) {
            setRadarData(null)
            setRadarTruncated(false)
            setRadarStatus('error')
          }
        })
        .finally(() => {
          if (requestId === radarRequestRef.current) {
            radarPendingKeyRef.current = null
          }
        })
    },
    [
      radarBasis,
      radarMinScore,
      radarMunicipality,
      radarMinAcres,
      radarMaxAcres,
      radarParcelClass,
      radarPlanStatus,
      mapSize,
    ],
  )

  const fetchParcels = useCallback(
    (vs: MapViewState) => {
      if (mapSize.width < 2 || mapSize.height < 2) {
        return
      }
      if (parcelFilter === 'radar') {
        fetchRadar(vs)
      } else {
        ++radarRequestRef.current
        radarPendingKeyRef.current = null
        radarLoadedKeyRef.current = null
        setRadarData(null)
        setRadarTruncated(false)
        setRadarStatus('idle')
      }
      if (!vs || vs.zoom < MIN_PARCEL_ZOOM) {
        ++parcelRequestRef.current
        parcelPendingKeyRef.current = null
        parcelLoadedKeyRef.current = null
        setParcelData(null)
        setParcelStatus('idle')
        return
      }

      const bounds = visibleBounds(vs, mapSize)
      const requestKey = [parcelFilter, bounds.west, bounds.south, bounds.east, bounds.north]
        .map((value) => (typeof value === 'number' ? value.toFixed(6) : value))
        .join(':')
      if (parcelPendingKeyRef.current === requestKey || parcelLoadedKeyRef.current === requestKey) {
        return
      }
      const requestId = ++parcelRequestRef.current
      parcelPendingKeyRef.current = requestKey
      parcelLoadedKeyRef.current = null
      setParcelStatus('loading')

      const bboxLayer =
        parcelFilter === 'delinquent'
          ? 'delinquent'
          : parcelFilter === 'vacant'
            ? 'vacant'
            : parcelFilter === 'vacant_delinquent'
              ? 'vacant_delinquent'
              : null
      Promise.all(
        splitBounds(bounds).map((part) => {
          const params = new URLSearchParams({
            west: part.west.toFixed(6),
            south: part.south.toFixed(6),
            east: part.east.toFixed(6),
            north: part.north.toFixed(6),
          })
          if (bboxLayer) {
            params.set('layer', bboxLayer)
          }
          return fetch(`/api/parcels/bbox?${params}`).then((r) => {
            if (!r.ok) {
              throw new Error(`${r.status}`)
            }
            return r.json() as Promise<ParcelMapData>
          })
        }),
      )
        .then((responses) => {
          if (requestId !== parcelRequestRef.current) {
            return
          }
          const seen = new Set<string>()
          const data: ParcelMapData = {
            type: 'FeatureCollection',
            features: responses
              .flatMap((response) => response.features)
              .filter((feature) => {
                const pidn = feature.properties?.pidn
                if (!pidn || seen.has(pidn)) {
                  return false
                }
                seen.add(pidn)
                return true
              }),
            truncated: responses.some((response) => response.truncated),
          }
          if (parcelFilter === 'delinquent' || parcelFilter === 'vacant_delinquent') {
            setParcelData({
              ...data,
              features: data.features.filter(
                (feature) => feature.properties?.has_tax_delinquency === true,
              ),
            })
          } else {
            setParcelData(data)
          }
          parcelLoadedKeyRef.current = requestKey
          setParcelStatus('ready')
        })
        .catch(() => {
          if (requestId !== parcelRequestRef.current) {
            return
          }
          setParcelData(null)
          setParcelStatus('error')
        })
        .finally(() => {
          if (requestId === parcelRequestRef.current) {
            parcelPendingKeyRef.current = null
          }
        })
    },
    [parcelFilter, fetchRadar, mapSize],
  )

  const onViewStateChange = useCallback(
    ({
      viewState,
      interactionState,
    }: {
      viewState: MapViewState
      interactionState?: Record<string, boolean>
    }) => {
      viewStateRef.current = viewState
      setViewState(viewState)
      if (interactionState && Object.values(interactionState).some(Boolean)) {
        userNavigatedRef.current = true
      }
      setCurrentZoom(viewState.zoom)

      if (viewState.zoom < MIN_PARCEL_ZOOM) {
        ++parcelRequestRef.current
        parcelPendingKeyRef.current = null
        parcelLoadedKeyRef.current = null
        setParcelStatus('idle')
        setParcelData(null)
        setHoverInfo(null)
        setSelectedPidn(null)
        setPropertyReport(null)
        setReportLoading(false)
        setReportFailed(false)
      }

      if (debounceRef.current) {
        clearTimeout(debounceRef.current)
      }
      debounceRef.current = setTimeout(() => {
        const parcelsEnabled = layers.find((l) => l.id === 'parcels')?.enabled
        if (parcelsEnabled && viewStateRef.current) {
          fetchParcels(viewStateRef.current)
        }
      }, 300)
    },
    [fetchParcels, layers],
  )

  useEffect(
    () => () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current)
      }
      ++parcelRequestRef.current
      ++radarRequestRef.current
      parcelPendingKeyRef.current = null
      radarPendingKeyRef.current = null
      parcelLoadedKeyRef.current = null
      radarLoadedKeyRef.current = null
    },
    [],
  )

  useEffect(() => {
    const vs = viewStateRef.current || initialViewState
    const minZoom = parcelFilter === 'radar' ? RADAR_MIN_ZOOM : MIN_PARCEL_ZOOM
    if (!parcelsEnabled || (vs.zoom ?? 0) < minZoom) {
      return
    }
    // Deferred a tick: fetchParcels sets state, which must not happen
    // synchronously inside the effect; the timer also coalesces rapid
    // filter flips.
    const timer = setTimeout(() => fetchParcels(vs as MapViewState), 0)
    return () => clearTimeout(timer)
  }, [parcelFilter, mapSize, parcelsEnabled]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const canvas = mapCanvasRef.current
    if (!canvas) {
      return
    }
    const update = () => setMapSize({ width: canvas.clientWidth, height: canvas.clientHeight })
    update()
    const observer = new ResizeObserver(update)
    observer.observe(canvas)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    if (
      !highlightPidn ||
      userNavigatedRef.current ||
      centeredHighlightRef.current === highlightPidn ||
      !parcelData
    ) {
      return
    }
    if (mapSize.width < 2 || mapSize.height < 2) {
      return
    }
    const feature = parcelData.features.find((item) => item.properties?.pidn === highlightPidn)
    if (!feature?.geometry) {
      return
    }
    const panel = mapCanvasRef.current?.querySelector<HTMLElement>('.map-property-panel')
    const panelIsBelow = panel && panel.clientWidth >= mapSize.width - 1
    const obscured =
      panelOpen && panel
        ? panelIsBelow
          ? { bottom: panel.clientHeight }
          : { right: panel.clientWidth }
        : {}
    const fitted = fitGeometry(
      viewStateRef.current || viewState,
      mapSize,
      feature.geometry,
      obscured,
    )
    if (!fitted) {
      return
    }
    const timer = window.setTimeout(() => {
      if (userNavigatedRef.current) {
        return
      }
      fittedHighlightRef.current = highlightPidn
      viewStateRef.current = fitted
      setViewState(fitted)
      setCurrentZoom(fitted.zoom)
      fetchParcels(fitted)
    }, 0)
    return () => window.clearTimeout(timer)
  }, [highlightPidn, parcelData, mapSize, viewState, fetchParcels, panelOpen])

  useEffect(() => {
    if (!selectedPidn) {
      return
    }
    let cancelled = false
    const controller = new AbortController()
    fetch(`/api/parcels/${encodeURIComponent(selectedPidn)}/summary`, {
      signal: controller.signal,
    })
      .then((r) => {
        if (!r.ok) {
          throw new Error(`${r.status}`)
        }
        return r.json()
      })
      .then((data: ParcelSummary) => {
        if (!cancelled) {
          setPropertyReport(data)
          const parcel = data.parcel
          if (
            highlightPidn &&
            !userNavigatedRef.current &&
            centeredHighlightRef.current !== highlightPidn &&
            parcel.lat != null &&
            parcel.lng != null
          ) {
            const fitted = {
              ...(viewStateRef.current || viewState),
              latitude: parcel.lat,
              longitude: parcel.lng,
              zoom: 16,
            }
            centeredHighlightRef.current = highlightPidn
            viewStateRef.current = fitted
            setViewState(fitted)
            setCurrentZoom(fitted.zoom)
            fetchParcels(fitted)
          }
        }
      })
      .catch(() => {
        if (!cancelled) {
          setPropertyReport(null)
          setReportFailed(true)
        }
      })
      .finally(() => {
        if (!cancelled) {
          setReportLoading(false)
        }
      })
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [fetchParcels, highlightPidn, selectedPidn, viewState])

  const handleToggle = useCallback((id: string) => {
    setLayers((prev) => prev.map((l) => (l.id === id ? { ...l, enabled: !l.enabled } : l)))
  }, [])

  const selectParcel = useCallback(
    (pidn: string) => {
      if (pidn === selectedPidn) {
        return
      }
      setHighlightPidn(null)
      setSelectedPidn(pidn)
      setPropertyReport(null)
      setReportFailed(false)
      setReportLoading(true)
      setHoverInfo(null)
    },
    [selectedPidn],
  )

  const handleParcelClick = useCallback(
    (info: PickingInfo) => {
      const pidn = info.object?.properties?.pidn
      if (pidn) {
        selectParcel(pidn)
      }
    },
    [selectParcel],
  )

  const closePanel = useCallback(() => {
    setSelectedPidn(null)
    setPropertyReport(null)
    setReportLoading(false)
    setReportFailed(false)
  }, [])

  useEffect(() => {
    if (!panelOpen) {
      return
    }
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        closePanel()
      }
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [closePanel, panelOpen])

  const deckLayers = useMemo(() => {
    const result = []
    const foregroundLayers = []

    const parcelsLayer = layers.find((l) => l.id === 'parcels')
    if (parcelsLayer?.enabled && parcelData && currentZoom >= MIN_PARCEL_ZOOM) {
      foregroundLayers.push(
        new GeoJsonLayer<ParcelFeatureProperties>({
          id: 'parcels',
          data: parcelData,
          stroked: true,
          filled: true,
          getFillColor: (f: ParcelFeature) => {
            const pidn = f.properties?.pidn
            if (selectedPidn && pidn === selectedPidn) {
              return [15, 91, 98, 65]
            }
            if (highlightPidn && pidn === highlightPidn) {
              return [216, 169, 75, 65]
            }
            if (pidn && adjacentPidns.has(pidn)) {
              return [216, 169, 75, 95]
            }
            if (parcelFilter === 'vacant_delinquent') {
              return [216, 169, 75, 150]
            }
            if (parcelFilter === 'vacant') {
              return [61, 189, 111, 120]
            }
            if (parcelFilter === 'delinquent') {
              return [224, 82, 82, 120]
            }
            return [96, 165, 250, 40]
          },
          getLineColor: (f: ParcelFeature) => {
            const pidn = f.properties?.pidn
            if (selectedPidn && pidn === selectedPidn) {
              return [15, 91, 98, 255]
            }
            if (highlightPidn && pidn === highlightPidn) {
              return [174, 115, 19, 255]
            }
            if (pidn && adjacentPidns.has(pidn)) {
              return [174, 115, 19, 230]
            }
            if (parcelFilter === 'vacant_delinquent') {
              return [216, 169, 75, 230]
            }
            if (parcelFilter === 'vacant') {
              return [61, 189, 111, 150]
            }
            return [96, 165, 250, 100]
          },
          getLineWidth: (f: ParcelFeature) => {
            const pidn = f.properties?.pidn
            if (selectedPidn && pidn === selectedPidn) {
              return 3
            }
            if (highlightPidn && pidn === highlightPidn) {
              return 3
            }
            return 1
          },
          lineWidthUnits: 'pixels' as const,
          pickable: true,
          onHover: (info: PickingInfo) => setHoverInfo(info.object ? info : null),
          onClick: handleParcelClick,
          autoHighlight: true,
          highlightColor: [255, 255, 255, 60],
          updateTriggers: {
            getFillColor: [parcelFilter, highlightPidn, selectedPidn, adjacentPidns],
            getLineColor: [parcelFilter, highlightPidn, selectedPidn, adjacentPidns],
            getLineWidth: [highlightPidn, selectedPidn],
          },
        }),
      )
    }

    if (
      parcelsLayer?.enabled &&
      parcelFilter === 'radar' &&
      radarData &&
      currentZoom >= RADAR_MIN_ZOOM
    ) {
      foregroundLayers.push(
        new ScatterplotLayer<RadarPoint>({
          id: 'radar-points',
          data: radarData,
          getPosition: (d: RadarPoint) => [d.lng, d.lat],
          getFillColor: (d: RadarPoint) => radarColor(d.properties.radar_score),
          getRadius: (d: RadarPoint) => 18 + d.properties.radar_score * 0.6,
          radiusUnits: 'meters' as const,
          radiusMinPixels: 3,
          radiusMaxPixels: 14,
          stroked: true,
          getLineColor: [10, 14, 26, 160],
          lineWidthMinPixels: 1,
          pickable: true,
          onHover: (info: PickingInfo) => setHoverInfo(info.object ? info : null),
          onClick: (info: PickingInfo) => {
            const pidn = (info.object as RadarPoint | undefined)?.properties?.pidn
            if (pidn) {
              selectParcel(pidn)
            }
          },
        }),
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
          getFillColor: darkMap ? [61, 189, 111, 16] : [70, 106, 91, 8],
          getLineColor: darkMap ? [106, 168, 133, 150] : [70, 106, 91, 140],
          getLineWidth: 1,
          lineWidthUnits: 'pixels' as const,
          pickable: true,
          onHover: (info: PickingInfo) => setHoverInfo(info.object ? info : null),
          autoHighlight: true,
          highlightColor: [61, 189, 111, 60],
        }),
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
        }),
      )
    }

    const zoningLayer = layers.find((l) => l.id === 'zoning')
    if (zoningLayer?.enabled && geoData.zoning) {
      result.push(
        new GeoJsonLayer<ZoningProperties>({
          id: 'zoning',
          data: geoData.zoning,
          stroked: true,
          filled: true,
          getFillColor: (f: ZoningFeature) => {
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
        }),
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
        }),
      )
    }

    // Reference polygons remain visible underneath parcels without intercepting
    // parcel picking. Deck.gl resolves pointer hits from the last drawn layer.
    return [...result, ...foregroundLayers]
  }, [
    layers,
    geoData,
    parcelData,
    radarData,
    currentZoom,
    handleParcelClick,
    parcelFilter,
    highlightPidn,
    selectedPidn,
    adjacentPidns,
    selectParcel,
    darkMap,
  ])

  const showRadarZoomHint =
    parcelsEnabled &&
    parcelFilter === 'radar' &&
    currentZoom >= RADAR_MIN_ZOOM &&
    currentZoom < MIN_PARCEL_ZOOM
  const showZoomMessage = parcelsEnabled && currentZoom < MIN_PARCEL_ZOOM && !showRadarZoomHint
  const parcelCount = parcelData?.features.length ?? 0
  const mapStatus: LoadStatus =
    parcelStatus === 'error' || (parcelFilter === 'radar' && radarStatus === 'error')
      ? 'error'
      : parcelStatus === 'loading' || (parcelFilter === 'radar' && radarStatus === 'loading')
        ? 'loading'
        : parcelStatus
  const retryParcels = () => {
    const viewState = viewStateRef.current || initialViewState
    fetchParcels(viewState as MapViewState)
  }

  return (
    <WorkspaceShell wide className="map-shell">
      <div
        ref={mapCanvasRef}
        className="map-canvas"
        data-panel-open={panelOpen}
        style={{ position: 'relative', flex: 1 }}
      >
        <Link
          className="map-back-link"
          to="/search"
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
          Find a property
        </Link>

        <LayerToggle layers={layers} onToggle={handleToggle} availability={layerAvailability} />

        {parcelFilter === 'radar' && (
          <div
            style={{
              position: 'absolute',
              top: 76,
              right: 16,
              zIndex: 10,
              display: 'grid',
              gap: 6,
              maxWidth: 340,
              padding: 12,
              background: 'var(--bg-panel)',
              border: '1px solid var(--border)',
              borderRadius: 8,
              boxShadow: 'var(--shadow-card)',
              fontSize: 12,
            }}
          >
            <strong>Radar screen</strong>
            <span>
              {radarBasis} · score {radarMinScore}+ · {radarPlanStatus} recorded linked plan
              {radarMunicipality ? ` · ${radarMunicipality}` : ''}
              {radarMinAcres ? ` · ${radarMinAcres}+ acres` : ''}
              {radarMaxAcres ? ` · up to ${radarMaxAcres} acres` : ''}
              {radarParcelClass ? ` · class ${radarParcelClass}` : ''}
            </span>
            <Link to={`/radar?${radarListParams}`}>Return to screening list</Link>
          </div>
        )}

        {parcelsEnabled && currentZoom >= MIN_PARCEL_ZOOM && mapStatus !== 'idle' && (
          <div className="map-data-status" data-state={mapStatus} role="status" aria-live="polite">
            {mapStatus === 'loading' && (
              <span>{parcelFilter === 'radar' ? 'Loading map data…' : 'Loading parcels…'}</span>
            )}
            {mapStatus === 'error' && (
              <>
                <span>
                  {radarStatus === 'error' ? 'Radar data unavailable' : 'Parcel data unavailable'}
                </span>
                <button type="button" onClick={retryParcels}>
                  Retry
                </button>
              </>
            )}
            {mapStatus === 'ready' && (
              <span>
                {parcelCount === 0
                  ? 'No parcels in this view'
                  : `${parcelCount.toLocaleString()} parcel${parcelCount === 1 ? '' : 's'} in view`}
                {parcelFilter === 'radar' && radarData
                  ? ` · ${radarData.length.toLocaleString()}${radarTruncated ? '+' : ''} radar results`
                  : ''}
                {parcelData?.truncated ? ' · zoom in for the complete set' : ''}
              </span>
            )}
          </div>
        )}

        {showRadarZoomHint && (
          <div
            className="map-filter-bar"
            style={{
              position: 'absolute',
              bottom: 24,
              left: '50%',
              transform: 'translateX(-50%)',
              zIndex: 10,
              display: 'flex',
              gap: 8,
              alignItems: 'center',
              background: 'var(--bg-panel)',
              border: '1px solid var(--border)',
              borderRadius: 8,
              padding: '6px 10px',
              boxShadow: '0 4px 16px rgba(0,0,0,0.4)',
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              color: 'var(--text-secondary)',
            }}
          >
            <button
              type="button"
              aria-pressed={parcelFilter === 'radar'}
              onClick={() => {
                if (radarStatus === 'error') {
                  retryParcels()
                }
              }}
              style={{
                padding: '6px 14px',
                borderRadius: 6,
                border: 'none',
                cursor: 'pointer',
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                letterSpacing: 0.5,
                background: parcelFilter === 'radar' ? 'var(--accent-cyan)' : 'transparent',
                color: parcelFilter === 'radar' ? '#0a0e1a' : 'var(--text-secondary)',
                fontWeight: parcelFilter === 'radar' ? 700 : 400,
              }}
            >
              Radar ({radarBasis})
            </button>
            <span>
              {radarStatus === 'loading'
                ? 'Loading radar…'
                : radarStatus === 'error'
                  ? 'Radar unavailable · retry'
                  : `${(radarData?.length ?? 0).toLocaleString()}${radarTruncated ? '+' : ''} results · zoom in for parcel outlines`}
            </span>
          </div>
        )}

        {currentZoom >= MIN_PARCEL_ZOOM && (
          <label className="map-filter-bar map-screen-control">
            Show on map
            <select
              value={parcelFilter}
              onChange={(event) => {
                setParcelFilter(event.target.value as ParcelFilter)
                setParcelData(null)
              }}
            >
              <option value="all">All properties</option>
              <option value="radar">Property shortlist</option>
              <option value="delinquent">Tax-claim listings</option>
              <option value="vacant">Vacancy screening</option>
              <option value="vacant_delinquent">Vacancy & tax-claim screening</option>
            </select>
          </label>
        )}

        {parcelsEnabled &&
          currentZoom >= (parcelFilter === 'radar' ? RADAR_MIN_ZOOM : MIN_PARCEL_ZOOM) && (
            <MapLegend filter={parcelFilter} />
          )}

        {showZoomMessage && (
          <div
            className="map-zoom-message"
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
            Zoom in to explore parcel boundaries
          </div>
        )}

        <DeckGL
          viewState={viewState}
          controller={true}
          // Synchronous picking can delay pointer-up on slower devices. Keep
          // Deck's movement threshold so panning still cannot select a parcel.
          eventRecognizerOptions={{ click: { time: 1000 } }}
          layers={deckLayers}
          onViewStateChange={onViewStateChange as never}
          getCursor={({ isDragging, isHovering }) =>
            isDragging ? 'grabbing' : isHovering ? 'pointer' : 'grab'
          }
          style={{ position: 'absolute', inset: '0' }}
        >
          <Map
            mapStyle={darkMap ? BASEMAPS.dark : BASEMAPS.light}
            style={{ width: '100%', height: '100%' }}
          >
            <NavigationControl position="bottom-right" showCompass={false} />
          </Map>
        </DeckGL>

        {hoverInfo?.object && hoverInfo.x != null && hoverInfo.y != null && (
          <div
            className="map-tooltip"
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
            <MapTooltip properties={hoverInfo.object.properties as TooltipProperties} />
          </div>
        )}

        <div
          className="map-property-panel"
          data-open={panelOpen}
          role={panelOpen ? 'region' : undefined}
          aria-label={panelOpen ? 'Selected parcel details' : undefined}
          aria-hidden={!panelOpen}
          style={{
            position: 'absolute',
            top: 0,
            right: 0,
            bottom: 0,
            width: 360,
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
              failed={reportFailed}
              onClose={closePanel}
            />
          )}
        </div>
      </div>
    </WorkspaceShell>
  )
}

function MapLegend({ filter }: { filter: ParcelFilter }) {
  const items =
    filter === 'radar'
      ? [
          { label: 'High score · 60+', color: 'rgba(61,189,111,0.86)' },
          { label: 'Medium · 40–59', color: 'rgba(232,181,60,0.86)' },
          { label: 'Lower · 20–39', color: 'rgba(96,165,250,0.78)' },
          { label: 'Under 20', color: 'rgba(148,163,184,0.63)' },
        ]
      : filter === 'vacant'
        ? [{ label: 'Vacancy screen · verify current use', color: 'rgba(61,189,111,0.72)' }]
        : filter === 'vacant_delinquent'
          ? [{ label: 'Vacancy screen + tax delinquency signal', color: 'rgba(216,169,75,0.82)' }]
          : filter === 'delinquent'
            ? [{ label: 'Tax delinquency signal', color: 'rgba(224,82,82,0.78)' }]
            : [{ label: 'Parcel', color: 'rgba(96,165,250,0.55)' }]

  return (
    <div className="map-legend" aria-label="Map legend">
      {items.map((item) => (
        <div key={item.label} className="map-legend-item">
          <span style={{ background: item.color }} />
          {item.label}
        </div>
      ))}
    </div>
  )
}

function PropertyPanel({
  report,
  loading,
  failed,
  onClose,
}: {
  report: ParcelSummary | null
  loading: boolean
  failed: boolean
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
          {failed ? 'Property data unavailable' : 'No property selected'}
        </div>
      </div>
    )
  }

  const {
    parcel: p,
    tax_delinquency: tax,
    flood_zone: flood,
    structures,
    development_momentum: radar,
  } = report

  return (
    <div className="map-parcel-summary">
      <div className="map-parcel-heading">
        <div>
          <h2>{p.propadr || 'Address unavailable'}</h2>
          {p.owner_id ? (
            <Link to={`/entity/${p.owner_id}`}>{p.owner_full || 'Recorded owner'}</Link>
          ) : (
            <p>{p.owner_full || 'Owner not displayed'}</p>
          )}
          <p className="map-parcel-location">
            {p.municipality} · {getPropertyClassLabel(p.class) || 'Property'}
          </p>
        </div>
        <CloseButton onClick={onClose} />
      </div>
      <ButtonLink className="map-parcel-report" tone="primary" to={`/property/${p.pidn}`}>
        Open property report →
      </ButtonLink>
      {radar?.top_signal && (
        <div className="map-parcel-signals">
          <h3>Recorded context</h3>
          <p>{radar.top_signal}</p>
        </div>
      )}
      {(report.source_explanation?.citation_evidence ?? []).some((item) =>
        item.citation_key.includes(':adjacent_'),
      ) && (
        <div className="map-investigation-context">
          <h3>Adjoining · same recorded owner</h3>
          <p>Gold parcels mark the adjoining ownership records currently visible on the map.</p>
          {(report.source_explanation?.citation_evidence ?? [])
            .filter((item) => item.citation_key.includes(':adjacent_'))
            .map((item) => (
              <div key={item.evidence_id}>
                <Link to={`/property/${encodeURIComponent(String(item.details.pidn))}`}>
                  {String(item.details.address ?? item.details.pidn)}
                </Link>
                {typeof item.details.last_recorded_sale_date === 'string' && (
                  <p>Recorded sale {formatShortDate(item.details.last_recorded_sale_date)}</p>
                )}
                <EvidencePanel items={[item]} title="View ownership source" />
              </div>
            ))}
        </div>
      )}
      {radar?.signals?.nearby_subdivision && (
        <div className="map-investigation-context">
          <h3>Nearby planning record</h3>
          <p>{radar.signals.nearby_subdivision.presentation?.summary}</p>
          <p>This is a nearby inventory point; it does not establish a project on this property.</p>
          {radar.signals.nearby_subdivision.evidence_receipt && (
            <EvidencePanel
              items={[radar.signals.nearby_subdivision.evidence_receipt]}
              title="View planning source"
            />
          )}
        </div>
      )}
      <div className="map-parcel-facts">
        <DataField label="Acres" value={p.acres != null ? Number(p.acres).toFixed(2) : '—'} />
        <DataField label="Assessed value" value={formatCurrency(p.aprtotal)} />
        <DataField label="Recorded sale" value={formatCurrency(p.price)} />
        <DataField label="Sale date" value={formatShortDate(p.saledt) || '—'} />
      </div>
      <ul className="map-parcel-context">
        <li>
          {tax.is_delinquent
            ? 'Delinquency signal detected; review the tax records.'
            : tax.detail_available
              ? 'No delinquency found in loaded records.'
              : 'Detailed tax records are unavailable.'}
        </li>
        <li>
          {flood.in_flood_zone
            ? `Mapped FEMA flood hazard overlap${flood.zone ? ` · Zone ${flood.zone}` : ''}.`
            : 'No mapped FEMA flood hazard overlap.'}
        </li>
        <li>
          {structures.likely_vacant
            ? 'Vacancy screen: no mapped building footprint. Verify current use.'
            : `${structures.count} mapped building ${structures.count === 1 ? 'footprint' : 'footprints'}.`}
        </li>
      </ul>
      <p className="map-parcel-id">PIDN {p.pidn}</p>
    </div>
  )
}

function CloseButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      aria-label="Close parcel details"
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
      <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
        <path
          d="M2 2L10 10M10 2L2 10"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
        />
      </svg>
    </button>
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

const formatCost = (cost: number | null) => formatCurrencyCompact(cost, { allowThousands: true })

function formatDate(d: string | null): string {
  if (!d) {
    return ''
  }
  try {
    return new Date(d).toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
  } catch {
    return d
  }
}

function MapTooltip({ properties }: { properties: TooltipProperties }) {
  if ('radar_score' in properties) {
    const p = properties
    return (
      <div style={{ fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--text-primary)' }}>
        <div style={{ fontWeight: 600, marginBottom: 2 }}>
          {p.radar_basis === 'momentum'
            ? 'Momentum'
            : p.radar_basis === 'readiness'
              ? 'Site screening'
              : 'Opportunity'}{' '}
          score {p.radar_score}
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 4 }}>
          {p.top_signal || 'No headline signal'}
        </div>
        <div style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
          {p.pidn}
        </div>
        <div style={{ fontSize: 9, color: 'var(--text-muted)', marginTop: 4 }}>
          Click for details
        </div>
      </div>
    )
  }

  if ('pidn' in properties && properties.pidn) {
    const p = properties
    const schoolName = getSchoolDistrictLabel(p.school_dis ?? null)
    const className = getPropertyClassLabel(p.class)
    return (
      <div style={{ fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--text-primary)' }}>
        <div style={{ fontWeight: 600, marginBottom: 2 }}>
          {p.owner_full || 'Owner not displayed'}
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 4 }}>
          {p.propadr || 'No address'}
        </div>
        <div
          style={{
            display: 'flex',
            gap: 8,
            flexWrap: 'wrap',
            fontSize: 11,
            fontFamily: 'var(--font-mono)',
          }}
        >
          {p.aprtotal != null && (
            <span style={{ color: 'var(--accent-blue)' }}>{formatCurrency(p.aprtotal)}</span>
          )}
          {className && <span style={{ color: 'var(--text-muted)' }}>{className}</span>}
          {schoolName && <span style={{ color: 'var(--text-muted)' }}>{schoolName}</span>}
        </div>
        {p.has_tax_delinquency && (
          <div
            style={{
              fontSize: 11,
              fontFamily: 'var(--font-mono)',
              color: 'var(--accent-red)',
              marginTop: 4,
            }}
          >
            Delinquency signal detected
          </div>
        )}
        <div style={{ fontSize: 9, color: 'var(--text-muted)', marginTop: 4 }}>
          Click for details
        </div>
      </div>
    )
  }

  if ('project_name' in properties && properties.project_name) {
    const p = properties
    const statusColor = p.under_construction === 'Y' ? 'var(--accent-gold)' : 'var(--accent-green)'
    const statusLabel = p.act89_status || p.status || ''
    return (
      <div style={{ fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--text-primary)' }}>
        <div style={{ fontWeight: 600, marginBottom: 4 }}>{p.project_name}</div>
        {p.location_desc && (
          <div
            style={{
              fontSize: 12,
              color: 'var(--text-secondary)',
              marginBottom: 6,
              lineHeight: 1.4,
            }}
          >
            {p.location_desc}
          </div>
        )}
        {!p.location_desc && p.description && (
          <div
            style={{
              fontSize: 12,
              color: 'var(--text-secondary)',
              marginBottom: 6,
              lineHeight: 1.4,
            }}
          >
            {p.description}
          </div>
        )}
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: '6px 14px',
            fontSize: 11,
            fontFamily: 'var(--font-mono)',
            color: 'var(--text-muted)',
            marginBottom: 4,
          }}
        >
          <span style={{ color: statusColor, fontWeight: 600 }}>{statusLabel}</span>
          {p.project_type && <span>{p.project_type}</span>}
        </div>
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: '6px 14px',
            fontSize: 11,
            fontFamily: 'var(--font-mono)',
            color: 'var(--text-muted)',
          }}
        >
          {p.start_date && <span>Start: {formatDate(p.start_date)}</span>}
          {p.end_date && <span>End: {formatDate(p.end_date)}</span>}
          {p.cost != null && (
            <span style={{ color: 'var(--accent-blue)' }}>{formatCost(p.cost)}</span>
          )}
        </div>
        {p.project_manager && (
          <div
            style={{
              fontSize: 10,
              fontFamily: 'var(--font-mono)',
              color: 'var(--text-muted)',
              marginTop: 6,
              borderTop: '1px solid var(--border)',
              paddingTop: 6,
            }}
          >
            PM: {p.project_manager}
          </div>
        )}
      </div>
    )
  }

  if ('gen_zname' in properties || 'zname' in properties) {
    const p = properties as ZoningProperties
    return (
      <div style={{ fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--text-primary)' }}>
        <div style={{ fontWeight: 600, marginBottom: 2 }}>{p.zname || p.gen_zname}</div>
        <div style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
          {p.gen_zcode && <span style={{ marginRight: 8 }}>{p.gen_zcode}</span>}
          {p.muni_name && <span>{p.muni_name}</span>}
        </div>
      </div>
    )
  }

  if ('muni_type' in properties && properties.muni_type) {
    const p = properties
    return (
      <div style={{ fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--text-primary)' }}>
        <div style={{ fontWeight: 600 }}>{p.name}</div>
        <div style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
          {p.muni_type}
        </div>
      </div>
    )
  }

  if ('fld_zone' in properties && properties.fld_zone) {
    const p = properties
    return (
      <div style={{ fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--text-primary)' }}>
        <div style={{ fontWeight: 600 }}>Zone {p.fld_zone}</div>
        {p.zone_subty && (
          <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{p.zone_subty}</div>
        )}
        <div style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
          SFHA: {p.sfha_tf === 'T' ? 'Yes' : 'No'}
        </div>
      </div>
    )
  }

  return null
}
