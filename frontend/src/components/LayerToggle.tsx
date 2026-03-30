interface LayerConfig {
  id: string
  name: string
  color: string
  enabled: boolean
}

interface LayerToggleProps {
  layers: LayerConfig[]
  onToggle: (id: string) => void
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

export default function LayerToggle({ layers, onToggle }: LayerToggleProps) {
  const zoningEnabled = layers.find(l => l.id === 'zoning')?.enabled ?? false
  return (
    <div
      style={{
        position: 'absolute',
        top: 16,
        right: 16,
        zIndex: 10,
        background: 'var(--bg-panel)',
        border: '1px solid var(--border)',
        borderRadius: 8,
        padding: '12px 16px',
        minWidth: 180,
        boxShadow: '0 4px 24px rgba(0, 0, 0, 0.4)',
      }}
    >
      <div
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 10,
          fontWeight: 600,
          letterSpacing: 2,
          textTransform: 'uppercase',
          color: 'var(--text-muted)',
          marginBottom: 10,
        }}
      >
        Layers
      </div>
      {layers.map((layer) => (
        <label
          key={layer.id}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '5px 0',
            cursor: 'pointer',
            fontFamily: 'var(--font-sans)',
            fontSize: 13,
            color: layer.enabled ? 'var(--text-primary)' : 'var(--text-secondary)',
            transition: 'color 0.15s',
          }}
        >
          <input
            type="checkbox"
            checked={layer.enabled}
            onChange={() => onToggle(layer.id)}
            style={{ display: 'none' }}
          />
          <span
            style={{
              width: 14,
              height: 14,
              borderRadius: 3,
              border: `1.5px solid ${layer.enabled ? layer.color : 'var(--text-muted)'}`,
              background: layer.enabled ? layer.color : 'transparent',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              transition: 'all 0.15s',
              flexShrink: 0,
            }}
          >
            {layer.enabled && (
              <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
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
            style={{
              width: 8,
              height: 8,
              borderRadius: 2,
              background: layer.color,
              opacity: layer.enabled ? 1 : 0.4,
              flexShrink: 0,
              transition: 'opacity 0.15s',
            }}
          />
          {layer.name}
        </label>
      ))}

      {/* Zoning legend */}
      {zoningEnabled && (
        <div style={{ marginTop: 10, paddingTop: 10, borderTop: '1px solid var(--border)' }}>
          <div style={{
            fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: 1.5,
            textTransform: 'uppercase' as const, color: 'var(--text-muted)', marginBottom: 6,
          }}>
            Zoning Legend
          </div>
          {ZONING_LEGEND.map(z => (
            <div key={z.code} style={{
              display: 'flex', alignItems: 'center', gap: 6, padding: '2px 0',
              fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-secondary)',
            }}>
              <span style={{
                width: 10, height: 10, borderRadius: 2, flexShrink: 0,
                background: z.color, opacity: 0.7,
              }} />
              <span style={{ color: 'var(--text-muted)', width: 36 }}>{z.code}</span>
              <span>{z.name}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
