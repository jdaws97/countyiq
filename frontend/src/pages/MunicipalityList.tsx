import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Nav from '../components/Nav'

interface Municipality {
  name: string
  muni_type: string
  delinquent_parcels: number
  total_delinquent: number
}

export default function MunicipalityList() {
  const [municipalities, setMunicipalities] = useState<Municipality[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()

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

  const formatCurrency = (value: number) =>
    '$' + value.toLocaleString('en-US', { maximumFractionDigits: 0 })

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-deep)' }}>
      <Nav />

      <main
        style={{
          maxWidth: 1200,
          margin: '0 auto',
          padding: '48px 32px',
        }}
      >
        {/* Page header */}
        <div style={{ marginBottom: 40, animation: 'fadeUp 0.4s ease both' }}>
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
            York County &middot; PA
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
            72 jurisdictions across York County
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
            style={{
              animation: 'fadeUp 0.5s ease both',
              animationDelay: '0.1s',
              opacity: 0,
              border: '1px solid var(--border)',
              borderRadius: 8,
              overflow: 'hidden',
            }}
          >
            {/* Table header */}
            <div
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
                <div
                  key={muni.name}
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '1fr 160px 180px 180px',
                    padding: '14px 24px',
                    background: isEven ? 'var(--bg-panel)' : 'var(--bg-card)',
                    borderBottom:
                      idx < municipalities.length - 1 ? '1px solid var(--border)' : 'none',
                    transition: 'background 0.15s ease',
                    cursor: 'pointer',
                  }}
                  onClick={() => navigate(`/delinquent?municipality=${encodeURIComponent(muni.name)}`)}
                  onMouseEnter={(e) => {
                    ;(e.currentTarget as HTMLDivElement).style.background =
                      'var(--bg-card-hover)'
                  }}
                  onMouseLeave={(e) => {
                    ;(e.currentTarget as HTMLDivElement).style.background = isEven
                      ? 'var(--bg-panel)'
                      : 'var(--bg-card)'
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
                </div>
              )
            })}

            {/* Footer row */}
            {municipalities.length > 0 && (
              <div
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
      </main>
    </div>
  )
}
