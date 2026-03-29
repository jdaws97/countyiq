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

export default function LayerToggle({ layers, onToggle }: LayerToggleProps) {
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
    </div>
  )
}
