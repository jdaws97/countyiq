import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import type { HealthData } from '../types/ops'

export default function Nav() {
  const [sourcesActive, setSourcesActive] = useState<number | null>(null)
  const [healthAvailable, setHealthAvailable] = useState(true)

  useEffect(() => {
    fetch('/api/ops/health')
      .then((r) => {
        if (!r.ok) throw new Error(`Health request failed (${r.status})`)
        return r.json() as Promise<HealthData>
      })
      .then((data) => {
        const green = Object.values(data.sources)
          .filter((s) => s.status === 'green').length
        setSourcesActive(green)
        setHealthAvailable(true)
      })
      .catch((error) => {
        console.error('Failed to load nav health summary', error)
        setSourcesActive(null)
        setHealthAvailable(false)
      })
  }, [])

  return (
    <nav
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 32px',
        height: 56,
        borderBottom: '1px solid var(--border)',
        background: 'rgba(10, 14, 26, 0.85)',
        backdropFilter: 'blur(12px)',
        position: 'sticky',
        top: 0,
        zIndex: 100,
      }}
    >
      <Link to="/" style={{ display: 'flex', alignItems: 'center', gap: 12, textDecoration: 'none' }}>
        <div
          style={{
            width: 28,
            height: 28,
            border: '2px solid var(--accent-gold)',
            borderRadius: 4,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontFamily: 'var(--font-mono)',
            fontWeight: 700,
            fontSize: 11,
            color: 'var(--accent-gold)',
            letterSpacing: -0.5,
          }}
        >
          CIQ
        </div>
        <div>
          <div
            style={{
              fontFamily: 'var(--font-mono)',
              fontWeight: 600,
              fontSize: 15,
              letterSpacing: 0.5,
              color: 'var(--text-primary)',
            }}
          >
            CountyIQ
          </div>
          <div
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              color: 'var(--text-muted)',
              letterSpacing: 2,
              textTransform: 'uppercase',
            }}
          >
            York County &middot; PA
          </div>
        </div>
      </Link>

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          fontFamily: 'var(--font-mono)',
          fontSize: 11,
          color: 'var(--text-muted)',
        }}
      >
        <div
          style={{
            width: 6,
            height: 6,
            borderRadius: '50%',
            background: healthAvailable ? 'var(--accent-green)' : 'var(--accent-red)',
            boxShadow: healthAvailable ? '0 0 6px rgba(61, 189, 111, 0.5)' : '0 0 6px rgba(220, 76, 76, 0.5)',
            animation: 'pulse 3s ease-in-out infinite',
          }}
        />
        <span>{sourcesActive !== null ? `${sourcesActive} sources active` : healthAvailable ? 'loading...' : 'sources unavailable'}</span>
      </div>
    </nav>
  )
}
