import { useEffect, useState } from 'react'
import PageShell from '../components/PageShell'
import { Button, EmptyState, PageHeader, StatusMessage } from '../components/ui'
import { useFetchJson } from '../lib/useFetchJson'
import { watchSyncState } from '../lib/watchSync'
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
  green: { bg: 'rgba(61, 189, 111, 0.15)', text: '#3dbd6f', label: 'Healthy' },
  yellow: { bg: 'rgba(212, 168, 67, 0.15)', text: '#d4a843', label: 'Degraded' },
  red: { bg: 'rgba(224, 82, 82, 0.15)', text: '#e05252', label: 'Incident' },
}

export default function OpsHealth() {
  const [session, setSession] = useState(watchSyncState)

  useEffect(() => {
    const update = () => setSession(watchSyncState())
    window.addEventListener('countyiq-watch-sync-changed', update)
    return () => window.removeEventListener('countyiq-watch-sync-changed', update)
  }, [])

  if (!session.initialized || !session.account?.authenticated || !session.account.operator) {
    return (
      <PageShell maxWidth={1200}>
        <PageHeader eyebrow="Operations" title="System health" />
        <StatusMessage>
          {!session.initialized
            ? 'Checking access…'
            : 'This page is available to CountyIQ operators only.'}
        </StatusMessage>
      </PageShell>
    )
  }

  return <OperatorHealth />
}

function OperatorHealth() {
  const { data: health, loading, error, reload } = useFetchJson<HealthData>('/api/ops/health')
  const [attentionOnly, setAttentionOnly] = useState(false)

  useEffect(() => {
    const interval = window.setInterval(() => {
      if (document.visibilityState === 'visible') {
        reload()
      }
    }, 60_000)
    return () => window.clearInterval(interval)
  }, [reload])

  const overallStyle = health ? OVERALL_COLORS[health.overall] : null
  const sourceEntries = Object.entries(health?.sources ?? {}).sort(([nameA, a], [nameB, b]) => {
    if (a.status !== b.status) {
      return a.status === 'red' ? -1 : 1
    }
    return nameA.localeCompare(nameB)
  })
  const attentionCount = sourceEntries.filter(([, source]) => source.status !== 'green').length
  const visibleSources = attentionOnly
    ? sourceEntries.filter(([, source]) => source.status !== 'green')
    : sourceEntries
  const failedJobs = new Set(
    sourceEntries
      .filter(([, source]) => source.last_run_status === 'failure')
      .map(([, source]) => source.last_run_job ?? source.refresh_job)
      .filter(Boolean),
  ).size
  const staleCount = sourceEntries.filter(([, source]) => source.stale).length
  const integrity = health?.intelligence_integrity

  return (
    <PageShell maxWidth={1200}>
      <PageHeader
        eyebrow="Operations"
        title="System health"
        description="Source availability, scheduled refreshes, municipal coverage, policy reviews, and intelligence integrity."
        meta="Refreshes every minute while this tab is visible. Results may be cached for up to a minute by default."
        actions={
          <Button onClick={reload} disabled={loading}>
            {loading ? 'Refreshing…' : 'Refresh status'}
          </Button>
        }
      />

      {loading && <StatusMessage>Loading system status…</StatusMessage>}
      {error && (
        <StatusMessage tone="error">
          Health data could not be loaded. <Button onClick={reload}>Try again</Button>
        </StatusMessage>
      )}

      {health && overallStyle && (
        <section aria-label="Health overview" style={{ marginBottom: 24 }}>
          <p style={{ marginBottom: 16 }}>
            <strong style={{ color: overallStyle.text }}>{overallStyle.label}</strong>
            {' · '}
            {health.summary}
          </p>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
              gap: 16,
            }}
          >
            {[
              [
                'Sources healthy',
                `${sourceEntries.length - attentionCount}/${sourceEntries.length}`,
              ],
              ['Sources needing attention', attentionCount],
              ['Sources past refresh window', staleCount],
              ['Jobs with a failed latest run', failedJobs],
            ].map(([label, value]) => (
              <div
                key={label}
                style={{
                  padding: 20,
                  background: 'var(--bg-panel)',
                  border: '1px solid var(--border)',
                  borderRadius: 6,
                }}
              >
                <div style={{ fontSize: 28, fontWeight: 600 }}>{value}</div>
                <div style={{ color: 'var(--text-secondary)', fontSize: 14 }}>{label}</div>
              </div>
            ))}
          </div>
        </section>
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

      {health && (
        <section aria-label="Source filters" style={{ margin: '24px 0 16px' }}>
          <h2 style={{ marginBottom: 12 }}>Data sources & policy reviews</h2>
          <div className="segmented" aria-label="Show sources">
            <button
              type="button"
              aria-pressed={!attentionOnly}
              onClick={() => setAttentionOnly(false)}
            >
              All sources ({sourceEntries.length})
            </button>
            <button
              type="button"
              aria-pressed={attentionOnly}
              onClick={() => setAttentionOnly(true)}
            >
              Needs attention ({attentionCount})
            </button>
          </div>
          {visibleSources.length === 0 && (
            <EmptyState
              title={
                sourceEntries.length === 0
                  ? 'No source health reported'
                  : 'No sources need attention'
              }
            >
              {sourceEntries.length === 0
                ? 'The health response did not include any sources. Source availability is unknown.'
                : 'All reported sources are healthy. Intelligence integrity is reported separately above.'}
            </EmptyState>
          )}
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
          {visibleSources.map(([key, source]) => {
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
                    {(source.active_count ?? 0) - (source.healthy_count ?? 0)} active bodies need
                    attention
                    <br />
                    {source.blocked_count} paused or blocked · {source.unchecked_count} unchecked ·{' '}
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
                    {source.freshness_basis === 'asset' ? 'source refresh in' : 'latest job'}{' '}
                    {formatSourceName(source.last_run_job ?? source.refresh_job)} ·{' '}
                    {source.last_run_status ?? 'unknown'}
                    <br />
                    last attempt {formatTimestamp(source.last_run_at)}
                    <br />
                    last success {formatTimestamp(source.last_success_at)}
                    <br />
                    freshness window {formatRefreshWindow(source.expected_refresh_hours)}
                    <br />
                    refresh due {formatTimestamp(source.freshness_due_at)}
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
