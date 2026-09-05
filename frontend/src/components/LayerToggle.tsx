import { useState } from 'react'

interface LayerConfig {
  id: string
  name: string
  color: string
  enabled: boolean
}

interface LayerToggleProps {
  layers: LayerConfig[]
  onToggle: (id: string) => void
  availability?: Record<string, 'loading' | 'ready' | 'error'>
}

export type { LayerConfig }

const ZONING_LEGEND = [
  { code: 'LDR', name: 'Low Density Residential', color: '#48bb78' },
  { code: 'MDR', name: 'Medium Density Residential', color: '#81b2d2' },
  { code: 'HDR', name: 'High Density Residential', color: '#4287f5' },
  { code: 'R', name: 'Rural', color: '#689f38' },
  { code: 'RP', name: 'Resource Protection', color: '#388e3c' },
  { code: 'Cv/OS', name: 'Conservation/Open Space', color: '#1b5e20' },
  { code: 'I', name: 'Industrial', color: '#9e7642' },
  { code: 'HC', name: 'Highway Commercial', color: '#ff9800' },
  { code: 'NC', name: 'Neighborhood Commercial', color: '#ffc107' },
  { code: 'MU', name: 'Mixed Use', color: '#ab47bc' },
]

export default function LayerToggle({ layers, onToggle, availability = {} }: LayerToggleProps) {
  const [expanded, setExpanded] = useState(false)
  const zoningEnabled = layers.find((layer) => layer.id === 'zoning')?.enabled ?? false

  return (
    <section
      className="layer-toggle"
      data-expanded={expanded}
      aria-label="Map layers"
      onKeyDown={(event) => {
        if (event.key === 'Escape') setExpanded(false)
      }}
    >
      <button
        type="button"
        className="layer-toggle-summary"
        aria-expanded={expanded}
        aria-controls="map-layer-options"
        onClick={() => setExpanded((current) => !current)}
      >
        <span>Map layers</span>
        <span>{layers.filter((layer) => layer.enabled).length} on · {expanded ? 'close' : 'configure'}</span>
      </button>

      <div id="map-layer-options" className="layer-toggle-content">
        <div className="layer-toggle-heading">Layers</div>
        {layers.map((layer) => {
          const layerStatus = availability[layer.id]
          const unavailable = layerStatus === 'error'

          return (
            <label
              key={layer.id}
              className="layer-toggle-option"
              data-unavailable={unavailable}
            >
              <input
                className="layer-toggle-checkbox"
                type="checkbox"
                checked={layer.enabled}
                disabled={unavailable}
                onChange={() => onToggle(layer.id)}
              />
              <span
                className="layer-toggle-check"
                style={{
                  borderColor: layer.enabled ? layer.color : 'var(--text-muted)',
                  background: layer.enabled ? layer.color : 'transparent',
                }}
              >
                {layer.enabled && (
                  <svg width="10" height="10" viewBox="0 0 10 10" fill="none" aria-hidden="true">
                    <path
                      d="M2 5.5L4 7.5L8 3"
                      stroke="rgba(0,0,0,0.7)"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                )}
              </span>
              <span
                className="layer-toggle-color"
                aria-hidden="true"
                style={{
                  background: layer.color,
                  opacity: layer.enabled ? 1 : 0.4,
                }}
              />
              <span className="layer-toggle-name">
                {layer.name}
                {layerStatus === 'loading' && <small>Loading</small>}
                {unavailable && <small>Unavailable</small>}
              </span>
            </label>
          )
        })}

        {zoningEnabled && availability.zoning !== 'error' && (
          <div className="zoning-legend">
            <div className="zoning-legend-heading">Zoning legend</div>
            {ZONING_LEGEND.map((zone) => (
              <div key={zone.code} className="zoning-legend-row">
                <span className="zoning-legend-color" style={{ background: zone.color }} />
                <span className="zoning-legend-code">{zone.code}</span>
                <span>{zone.name}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  )
}
