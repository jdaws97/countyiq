import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import PageShell from '../components/PageShell'
import { formatCurrency } from '../lib/format'
import { useCountyMeta } from '../lib/useCountyMeta'
import { getMunicipalityWatchlist } from '../lib/watchlist'
import type { MunicipalitySummary as Municipality } from '../types/api'

export default function MunicipalityList() {
  const county = useCountyMeta()
  const [municipalities, setMunicipalities] = useState<Municipality[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [watchedNames, setWatchedNames] = useState(() => new Set(getMunicipalityWatchlist().map((item) => item.name)))

  useEffect(() => {
    const refresh = () => setWatchedNames(new Set(getMunicipalityWatchlist().map((item) => item.name)))
    window.addEventListener('countyiq-watchlist-changed', refresh)
    return () => window.removeEventListener('countyiq-watchlist-changed', refresh)
  }, [])

  useEffect(() => {
    fetch('/api/municipalities')
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then((data: Municipality[]) => {
        const sorted = [...data].sort((a, b) => a.name.localeCompare(b.name))
        setMunicipalities(sorted)
        setLoading(false)
      })
      .catch((err) => {
        setError(err.message)
        setLoading(false)
      })
  }, [])

  return (
    <PageShell maxWidth={1200}>
        {/* Page header */}
        <div style={{ marginBottom: 40 }}>
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
            {county.county_name} &middot; {county.state}
          </div>
          <h1
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 28,
              fontWeight: 600,
              letterSpacing: 1,
              textTransform: 'uppercase',
              color: 'var(--text-primary)',
              marginBottom: 8,
            }}
          >
            Municipalities
          </h1>
          <p
            style={{
              fontFamily: 'var(--font-sans)',
              fontSize: 14,
              color: 'var(--text-secondary)',
            }}
          >
            {loading ? `Jurisdictions across ${county.county_name}` : `${municipalities.length} jurisdictions across ${county.county_name}`}
          </p>
        </div>

        {/* Loading state */}
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
            Loading municipalities...
          </div>
        )}

        {/* Error state */}
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
            Failed to load data: {error}
          </div>
        )}

        {/* Table */}
        {!loading && !error && (
          <div
            className="municipality-table"
            style={{
              border: '1px solid var(--border)',
              borderRadius: 8,
              overflow: 'hidden',
            }}
          >
            {/* Table header */}
            <div
              className="municipality-table-head"
              style={{
                display: 'grid',
                gridTemplateColumns: '1fr 160px 180px 180px',
                padding: '12px 24px',
                background: 'var(--bg-panel)',
                borderBottom: '1px solid var(--border)',
              }}
            >
              {['Name', 'Type', 'Delinquent Parcels', 'Total Delinquent'].map((col, i) => (
                <div
                  key={col}
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 10,
                    fontWeight: 600,
                    letterSpacing: 2,
                    textTransform: 'uppercase',
                    color: 'var(--text-muted)',
                    textAlign: i >= 2 ? 'right' : 'left',
                  }}
                >
                  {col}
                </div>
              ))}
            </div>

            {/* Table rows */}
            {municipalities.map((muni, idx) => {
              const isEven = idx % 2 === 0
              return (
                <Link
                  key={muni.name}
                  className="municipality-table-row"
                  to={`/municipalities/${encodeURIComponent(muni.name)}`}
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '1fr 160px 180px 180px',
                    padding: '14px 24px',
                    background: isEven ? 'var(--bg-panel)' : 'var(--bg-card)',
                    borderBottom:
                      idx < municipalities.length - 1 ? '1px solid var(--border)' : 'none',
                    transition: 'background 0.15s ease',
                    cursor: 'pointer',
                    color: 'inherit',
                    textDecoration: 'none',
                  }}
                >
                  {/* Name */}
                  <div
                    style={{
                      fontFamily: 'var(--font-sans)',
                      fontSize: 14,
                      fontWeight: 500,
                      color: 'var(--text-primary)',
                    }}
                  >
                    {watchedNames.has(muni.name) && <span style={{ color: 'var(--accent-gold)', marginRight: 6 }} title="Watched municipality">★</span>}
                    {muni.name}
                  </div>

                  {/* Type */}
                  <div
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: 11,
                      color: 'var(--text-secondary)',
                      letterSpacing: 0.5,
                      display: 'flex',
                      alignItems: 'center',
                    }}
                  >
                    <span
                      style={{
                        padding: '2px 8px',
                        borderRadius: 3,
                        background: 'rgba(74, 127, 255, 0.08)',
                        border: '1px solid rgba(74, 127, 255, 0.15)',
                        color: 'var(--accent-blue)',
                        fontSize: 10,
                        letterSpacing: 1,
                        textTransform: 'uppercase',
                      }}
                    >
                      {muni.muni_type}
                    </span>
                  </div>

                  {/* Delinquent parcels */}
                  <div
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: 14,
                      color:
                        muni.delinquent_parcels > 0 ? 'var(--accent-red)' : 'var(--text-muted)',
                      textAlign: 'right',
                    }}
                  >
                    {muni.delinquent_parcels.toLocaleString()}
                  </div>

                  {/* Total delinquent */}
                  <div
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: 14,
                      color:
                        muni.total_delinquent > 0 ? 'var(--accent-red)' : 'var(--text-muted)',
                      textAlign: 'right',
                      fontWeight: muni.total_delinquent > 0 ? 500 : 400,
                    }}
                  >
                    {muni.total_delinquent > 0 ? formatCurrency(muni.total_delinquent) : '—'}
                  </div>
                </Link>
              )
            })}

            {/* Footer row */}
            {municipalities.length > 0 && (
              <div
                className="municipality-table-footer"
                style={{
                  padding: '12px 24px',
                  background: 'var(--bg-deep)',
                  borderTop: '1px solid var(--border)',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <span
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 11,
                    color: 'var(--text-muted)',
                    letterSpacing: 0.5,
                  }}
                >
                  {municipalities.length} jurisdictions
                </span>
                <span
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 11,
                    color: 'var(--text-muted)',
                    letterSpacing: 0.5,
                  }}
                >
                  Total delinquent:{' '}
                  <span style={{ color: 'var(--accent-red)' }}>
                    {formatCurrency(
                      municipalities.reduce((sum, m) => sum + (m.total_delinquent ?? 0), 0)
                    )}
                  </span>
                </span>
              </div>
            )}
          </div>
        )}
    </PageShell>
  )
}
