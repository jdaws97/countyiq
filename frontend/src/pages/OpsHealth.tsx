import { useEffect, useState } from 'react'
import PageShell from '../components/PageShell'
import type { HealthData, OverallHealthStatus } from '../types/ops'

function formatSourceName(key: string): string {
  return key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

const OVERALL_COLORS: Record<OverallHealthStatus, { bg: string; text: string; label: string }> = {
  green:  { bg: 'rgba(61, 189, 111, 0.15)',  text: '#3dbd6f', label: 'All Systems Go' },
  yellow: { bg: 'rgba(212, 168, 67, 0.15)',  text: '#d4a843', label: 'Degraded' },
  red:    { bg: 'rgba(224, 82, 82, 0.15)',   text: '#e05252', label: 'Incident' },
}

export default function OpsHealth() {
  const [health, setHealth] = useState<HealthData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/ops/health')
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then((data: HealthData) => {
        setHealth(data)
        setLoading(false)
      })
      .catch((err) => {
        setError(err.message)
        setLoading(false)
      })
  }, [])

  const overall = health?.overall ?? 'green'
  const overallStyle = OVERALL_COLORS[overall] ?? OVERALL_COLORS.green
  const sourceEntries = health ? Object.entries(health.sources) : []

  return (
    <PageShell maxWidth={1200}>
        {/* Page header */}
        <div
          style={{
            marginBottom: 48,
            animation: 'fadeUp 0.4s ease both',
            display: 'flex',
            alignItems: 'flex-start',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: 16,
          }}
        >
          <div>
            <div
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                letterSpacing: 3,
                textTransform: 'uppercase',
                color: 'var(--accent-gold)',
                marginBottom: 12,
              }}
            >
              Operations
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
              <h1
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 28,
                  fontWeight: 600,
                  letterSpacing: 1,
                  textTransform: 'uppercase',
                  color: 'var(--text-primary)',
                }}
              >
                System Health
              </h1>

              {/* Overall status badge */}
              {!loading && !error && health && (
                <span
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 11,
                    fontWeight: 600,
                    letterSpacing: 2,
                    textTransform: 'uppercase',
                    color: overallStyle.text,
                    background: overallStyle.bg,
                    border: `1px solid ${overallStyle.text}40`,
                    borderRadius: 20,
                    padding: '4px 14px',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 6,
                  }}
                >
                  <span
                    style={{
                      width: 6,
                      height: 6,
                      borderRadius: '50%',
                      background: overallStyle.text,
                      boxShadow: `0 0 6px ${overallStyle.text}`,
                      display: 'inline-block',
                      animation: overall === 'green' ? 'pulse 3s ease-in-out infinite' : 'none',
                    }}
                  />
                  {overallStyle.label}
                </span>
              )}
            </div>

            {health && (
              <p
                style={{
                  fontFamily: 'var(--font-sans)',
                  fontSize: 14,
                  color: 'var(--text-secondary)',
                  marginTop: 8,
                }}
              >
                {health.summary}
              </p>
            )}
          </div>
        </div>

        {/* Loading */}
        {loading && (
          <div
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 13,
              color: 'var(--text-muted)',
              textAlign: 'center',
              padding: '80px 0',
            }}
          >
            Loading system status...
          </div>
        )}

        {/* Error */}
        {error && (
          <div
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 13,
              color: 'var(--accent-red)',
              padding: '24px',
              background: 'rgba(224, 82, 82, 0.08)',
              border: '1px solid rgba(224, 82, 82, 0.2)',
              borderRadius: 6,
            }}
          >
            Failed to load health data: {error}
          </div>
        )}

        {/* Source grid */}
        {!loading && !error && health && (
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(3, 1fr)',
              gap: 16,
            }}
          >
            {sourceEntries.map(([key, source], idx) => {
              const isGreen = source.status === 'green'
              const borderColor = isGreen
                ? 'rgba(61, 189, 111, 0.5)'
                : 'rgba(224, 82, 82, 0.5)'
              const dotColor = isGreen ? 'var(--accent-green)' : 'var(--accent-red)'
              const dotGlow = isGreen
                ? 'rgba(61, 189, 111, 0.6)'
                : 'rgba(224, 82, 82, 0.6)'

              return (
                <div
                  key={key}
                  style={{
                    background: 'var(--bg-panel)',
                    border: '1px solid var(--border)',
                    borderLeft: `3px solid ${borderColor}`,
                    borderRadius: 6,
                    padding: '20px',
                    position: 'relative',
                    animation: `fadeUp 0.4s ease both`,
                    animationDelay: `${0.05 + idx * 0.04}s`,
                    opacity: 0,
                    transition: 'background 0.15s ease, border-color 0.15s ease',
                  }}
                  onMouseEnter={(e) => {
                    ;(e.currentTarget as HTMLDivElement).style.background = 'var(--bg-card)'
                    ;(e.currentTarget as HTMLDivElement).style.borderColor = 'var(--border-active)'
                  }}
                  onMouseLeave={(e) => {
                    ;(e.currentTarget as HTMLDivElement).style.background = 'var(--bg-panel)'
                    ;(e.currentTarget as HTMLDivElement).style.borderColor = 'var(--border)'
                  }}
                >
                  {/* Status dot */}
                  <div
                    style={{
                      position: 'absolute',
                      top: 20,
                      right: 20,
                      width: 8,
                      height: 8,
                      borderRadius: '50%',
                      background: dotColor,
                      boxShadow: `0 0 8px ${dotGlow}`,
                      animation: isGreen ? 'pulse 3s ease-in-out infinite' : 'none',
                    }}
                  />

                  {/* Source name */}
                  <div
                    style={{
                      fontFamily: 'var(--font-sans)',
                      fontSize: 13,
                      fontWeight: 500,
                      color: 'var(--text-secondary)',
                      marginBottom: 12,
                      paddingRight: 20,
                      letterSpacing: 0.2,
                    }}
                  >
                    {formatSourceName(key)}
                  </div>

                  {/* Record count */}
                  <div
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: 26,
                      fontWeight: 600,
                      color: isGreen ? 'var(--text-primary)' : 'var(--text-muted)',
                      letterSpacing: -0.5,
                      lineHeight: 1,
                      marginBottom: 8,
                    }}
                  >
                    {source.record_count.toLocaleString()}
                  </div>

                  {/* Label */}
                  <div
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: 10,
                      letterSpacing: 1.5,
                      textTransform: 'uppercase',
                      color: 'var(--text-muted)',
                    }}
                  >
                    records
                  </div>

                  {/* Status label */}
                  <div
                    style={{
                      marginTop: 12,
                      fontFamily: 'var(--font-mono)',
                      fontSize: 10,
                      letterSpacing: 1.5,
                      textTransform: 'uppercase',
                      color: isGreen ? 'var(--accent-green)' : 'var(--accent-red)',
                    }}
                  >
                    {isGreen ? 'Active' : 'Inactive'}
                  </div>
                </div>
              )
            })}
          </div>
        )}
    </PageShell>
  )
}
