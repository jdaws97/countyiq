import { useEffect, useState } from 'react'
import PageShell from '../components/PageShell'
import type { HealthData, OverallHealthStatus, SourceHealthReason } from '../types/ops'

function formatSourceName(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

function formatTimestamp(value?: string | null): string {
  if (!value) {
    return 'not observed'
  }
  return new Date(value).toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}

function formatRefreshWindow(hours?: number): string {
  if (!hours) {
    return 'not configured'
  }
  return hours % 24 === 0 ? `${hours / 24} days` : `${hours} hours`
}

const STATUS_LABELS: Record<SourceHealthReason, string> = {
  healthy: 'Healthy',
  empty_source: 'No current records',
  last_run_failed: 'Last run failed',
  missing_table: 'Table missing',
  policy_overdue: 'Policy review overdue',
  query_failed: 'Health query failed',
  run_not_observed: 'No run observed',
  source_unhealthy: 'Source needs attention',
  stale: 'Stale',
}

const OVERALL_COLORS: Record<OverallHealthStatus, { bg: string; text: string; label: string }> = {
  green: { bg: 'rgba(61, 189, 111, 0.15)', text: '#3dbd6f', label: 'All Systems Go' },
  yellow: { bg: 'rgba(212, 168, 67, 0.15)', text: '#d4a843', label: 'Degraded' },
  red: { bg: 'rgba(224, 82, 82, 0.15)', text: '#e05252', label: 'Incident' },
}

export default function OpsHealth() {
  const [health, setHealth] = useState<HealthData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/ops/health')
      .then((r) => {
        if (!r.ok) {
          throw new Error(`HTTP ${r.status}`)
        }
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
  const integrity = health?.intelligence_integrity

  return (
    <PageShell maxWidth={1200}>
      {/* Page header */}
      <div
        style={{
          marginBottom: 48,
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

      {!loading && !error && integrity && (
        <section
          style={{
            marginBottom: 24,
            padding: 20,
            background: 'var(--bg-panel)',
            border: `1px solid ${OVERALL_COLORS[integrity.status].text}55`,
            borderLeft: `3px solid ${OVERALL_COLORS[integrity.status].text}`,
            borderRadius: 6,
          }}
          aria-label="Intelligence integrity"
        >
          <div
            style={{ display: 'flex', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}
          >
            <div>
              <div
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 12,
                  letterSpacing: 1.5,
                  textTransform: 'uppercase',
                  color: 'var(--text-primary)',
                }}
              >
                Intelligence integrity
              </div>
              <div
                style={{
                  marginTop: 6,
                  fontFamily: 'var(--font-mono)',
                  fontSize: 10,
                  textTransform: 'uppercase',
                  color: OVERALL_COLORS[integrity.status].text,
                }}
              >
                {integrity.status_reason.replace(/_/g, ' ')}
              </div>
            </div>
            <div
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                lineHeight: 1.7,
                color: 'var(--text-muted)',
                textAlign: 'right',
              }}
            >
              {integrity.accepted_count.toLocaleString()} accepted ·{' '}
              {integrity.quarantined_count.toLocaleString()} quarantined
              <br />
              {integrity.unresolved_contradiction_count} unresolved ·{' '}
              {integrity.resolved_contradiction_count} resolved
            </div>
          </div>
          <div
            style={{
              marginTop: 14,
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
              gap: 10,
              fontFamily: 'var(--font-mono)',
              fontSize: 10,
              color: 'var(--text-muted)',
            }}
          >
            <span>oldest unresolved {formatTimestamp(integrity.oldest_unresolved_at)}</span>
            <span>unlinked projections {integrity.unlinked_projection_count}</span>
            <span>projection mismatches {integrity.projection_mismatch_count}</span>
            <span>human resolutions {integrity.human_resolution_inference_count}</span>
            <span>invalid outputs (24h) {integrity.validation_rejections_last_24h}</span>
            <span>
              latest invalid output {formatTimestamp(integrity.latest_validation_rejection_at)}
            </span>
          </div>
        </section>
      )}

      {/* Source grid */}
      {!loading && !error && health && (
        <div
          className="ops-source-grid"
          style={{
            display: 'grid',
            gap: 16,
          }}
        >
          {sourceEntries.map(([key, source], idx) => {
            const isGreen = source.status === 'green'
            const borderColor = isGreen ? 'rgba(61, 189, 111, 0.5)' : 'rgba(224, 82, 82, 0.5)'
            const dotColor = isGreen ? 'var(--accent-green)' : 'var(--accent-red)'
            const dotGlow = isGreen ? 'rgba(61, 189, 111, 0.6)' : 'rgba(224, 82, 82, 0.6)'

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
                  {key === 'source_governance'
                    ? 'active source policies'
                    : source.configured_count === undefined
                      ? 'records'
                      : 'documents discovered'}
                </div>

                {key === 'source_governance' && (
                  <div
                    style={{
                      marginTop: 10,
                      fontFamily: 'var(--font-mono)',
                      fontSize: 10,
                      lineHeight: 1.6,
                      color: 'var(--text-muted)',
                    }}
                  >
                    {source.conditional_count} conditional · {source.paused_count} paused ·{' '}
                    {source.configured_count} total
                    <br />
                    {source.overdue_count} overdue · {source.due_soon_count} due within 30 days
                    <br />
                    next review {source.next_review_on ?? 'not scheduled'}
                  </div>
                )}

                {source.configured_count !== undefined && key !== 'source_governance' && (
                  <div
                    style={{
                      marginTop: 10,
                      fontFamily: 'var(--font-mono)',
                      fontSize: 10,
                      lineHeight: 1.6,
                      color: 'var(--text-muted)',
                    }}
                  >
                    {source.healthy_count}/{source.active_count} active bodies healthy
                    <br />
                    {source.blocked_count} blocked · {source.unchecked_count} unchecked ·{' '}
                    {source.stale_count ?? 0} stale
                    <br />
                    latest body check {formatTimestamp(source.last_checked_at)}
                  </div>
                )}

                {source.refresh_job && (
                  <div
                    style={{
                      marginTop: 10,
                      fontFamily: 'var(--font-mono)',
                      fontSize: 10,
                      lineHeight: 1.6,
                      color: 'var(--text-muted)',
                    }}
                  >
                    latest job {formatSourceName(source.last_run_job ?? source.refresh_job)} ·{' '}
                    {source.last_run_status ?? 'unknown'}
                    <br />
                    last run {formatTimestamp(source.last_run_at)}
                    <br />
                    last success {formatTimestamp(source.last_success_at)}
                    <br />
                    freshness window {formatRefreshWindow(source.expected_refresh_hours)}
                  </div>
                )}

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
                  {source.status_reason
                    ? STATUS_LABELS[source.status_reason]
                    : isGreen
                      ? 'Healthy'
                      : 'Needs attention'}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </PageShell>
  )
}
