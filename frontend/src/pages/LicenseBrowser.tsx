import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Nav from '../components/Nav'

interface License {
  licensee: string
  premises_name: string
  premises_address: string
  license_type: string
  status: string
  municipality: string
  last_issue_date: string
  expiration_date: string
}

interface TypeSummary {
  license_type: string
  count: number
}

interface LicenseResponse {
  licenses: License[]
  type_summary: TypeSummary[]
  total: number
}

const STATUS_COLORS: Record<string, string> = {
  Active: 'var(--accent-green)',
  Safekeeping: 'var(--accent-gold)',
  Expired: 'var(--accent-red)',
}

function statusColor(status: string): string {
  return STATUS_COLORS[status] ?? 'var(--text-muted)'
}

function statusBg(status: string): string {
  if (status === 'Active') return 'rgba(61, 189, 111, 0.12)'
  if (status === 'Safekeeping') return 'rgba(212, 168, 67, 0.12)'
  if (status === 'Expired') return 'rgba(224, 82, 82, 0.12)'
  return 'rgba(100, 110, 140, 0.08)'
}

export default function LicenseBrowser() {
  const [data, setData] = useState<LicenseResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [typeFilter, setTypeFilter] = useState('')
  const [muniFilter, setMuniFilter] = useState('')

  useEffect(() => {
    fetch('/api/licenses?status=Active&limit=200')
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then((resp: LicenseResponse) => {
        setData(resp)
        setLoading(false)
      })
      .catch((err) => {
        setError(err.message)
        setLoading(false)
      })
  }, [])

  const licenses = data?.licenses ?? []
  const typeSummary = data?.type_summary ?? []
  const total = data?.total ?? 0

  /* Unique license types for the dropdown */
  const licenseTypes = typeSummary
    .sort((a, b) => b.count - a.count)
    .map((t) => t.license_type)

  /* Top 4 types for pill badges */
  const topTypes = typeSummary
    .sort((a, b) => b.count - a.count)
    .slice(0, 4)

  /* Filtered licenses */
  const filtered = licenses.filter((lic) => {
    if (typeFilter && lic.license_type !== typeFilter) return false
    if (muniFilter && !lic.municipality.toLowerCase().includes(muniFilter.toLowerCase()))
      return false
    return true
  })

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
        <div style={{ marginBottom: 32, animation: 'fadeUp 0.4s ease both' }}>
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
            Liquor Licenses
          </h1>
          <Link
            to="/"
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              color: 'var(--accent-blue)',
              textDecoration: 'none',
              letterSpacing: 0.5,
            }}
          >
            &larr; Back to Home
          </Link>
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
            Loading licenses...
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

        {/* Summary stats + table */}
        {!loading && !error && data && (
          <>
            {/* Summary row */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                marginBottom: 24,
                flexWrap: 'wrap',
                animation: 'fadeUp 0.4s ease both',
                animationDelay: '0.05s',
                opacity: 0,
              }}
            >
              <span
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 13,
                  color: 'var(--text-secondary)',
                  letterSpacing: 0.3,
                }}
              >
                <span
                  style={{
                    fontWeight: 600,
                    color: 'var(--text-primary)',
                    fontSize: 15,
                  }}
                >
                  {total.toLocaleString()}
                </span>{' '}
                active licenses
              </span>

              <span
                style={{
                  width: 1,
                  height: 16,
                  background: 'var(--border)',
                  display: 'inline-block',
                }}
              />

              {topTypes.map((t) => (
                <span
                  key={t.license_type}
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 10,
                    letterSpacing: 0.5,
                    padding: '3px 10px',
                    borderRadius: 3,
                    background: 'rgba(74, 127, 255, 0.08)',
                    border: '1px solid rgba(74, 127, 255, 0.15)',
                    color: 'var(--accent-blue)',
                    textTransform: 'uppercase',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {t.license_type.replace(' (Liquor)', '').replace(' (Beer)', '')} ({t.count})
                </span>
              ))}
            </div>

            {/* Table */}
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
              {/* Filter row */}
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: '240px 1fr',
                  gap: 12,
                  padding: '12px 24px',
                  background: 'var(--bg-deep)',
                  borderBottom: '1px solid var(--border)',
                }}
              >
                <select
                  value={typeFilter}
                  onChange={(e) => setTypeFilter(e.target.value)}
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 11,
                    letterSpacing: 0.5,
                    color: 'var(--text-secondary)',
                    background: 'var(--bg-panel)',
                    border: '1px solid var(--border)',
                    borderRadius: 4,
                    padding: '6px 10px',
                    outline: 'none',
                    cursor: 'pointer',
                    appearance: 'auto',
                  }}
                >
                  <option value="">All license types</option>
                  {licenseTypes.map((lt) => (
                    <option key={lt} value={lt}>
                      {lt}
                    </option>
                  ))}
                </select>

                <input
                  type="text"
                  placeholder="Filter by municipality..."
                  value={muniFilter}
                  onChange={(e) => setMuniFilter(e.target.value)}
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 11,
                    letterSpacing: 0.5,
                    color: 'var(--text-secondary)',
                    background: 'var(--bg-panel)',
                    border: '1px solid var(--border)',
                    borderRadius: 4,
                    padding: '6px 10px',
                    outline: 'none',
                    maxWidth: 280,
                  }}
                />
              </div>

              {/* Table header */}
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: '1.4fr 1.4fr 1fr 0.9fr 0.6fr',
                  padding: '12px 24px',
                  background: 'var(--bg-panel)',
                  borderBottom: '1px solid var(--border)',
                }}
              >
                {['Premises Name', 'Address', 'Type', 'Municipality', 'Status'].map((col) => (
                  <div
                    key={col}
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: 10,
                      fontWeight: 600,
                      letterSpacing: 2,
                      textTransform: 'uppercase',
                      color: 'var(--text-muted)',
                    }}
                  >
                    {col}
                  </div>
                ))}
              </div>

              {/* Table rows */}
              {filtered.length === 0 && (
                <div
                  style={{
                    padding: '40px 24px',
                    textAlign: 'center',
                    fontFamily: 'var(--font-mono)',
                    fontSize: 12,
                    color: 'var(--text-muted)',
                  }}
                >
                  No licenses match the current filters.
                </div>
              )}

              {filtered.map((lic, idx) => {
                const isEven = idx % 2 === 0
                return (
                  <div
                    key={`${lic.premises_name}-${lic.premises_address}-${idx}`}
                    style={{
                      display: 'grid',
                      gridTemplateColumns: '1.4fr 1.4fr 1fr 0.9fr 0.6fr',
                      padding: '12px 24px',
                      background: isEven ? 'var(--bg-panel)' : 'var(--bg-card)',
                      borderBottom:
                        idx < filtered.length - 1 ? '1px solid var(--border)' : 'none',
                      transition: 'background 0.15s ease',
                      cursor: 'default',
                      alignItems: 'center',
                    }}
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
                    {/* Premises Name */}
                    <div
                      style={{
                        fontFamily: 'var(--font-sans)',
                        fontSize: 13,
                        fontWeight: 600,
                        color: 'var(--text-primary)',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        paddingRight: 12,
                      }}
                    >
                      {lic.premises_name || lic.licensee}
                    </div>

                    {/* Address */}
                    <div
                      style={{
                        fontFamily: 'var(--font-mono)',
                        fontSize: 11,
                        color: 'var(--text-secondary)',
                        letterSpacing: 0.3,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        paddingRight: 12,
                      }}
                    >
                      {lic.premises_address}
                    </div>

                    {/* Type */}
                    <div
                      style={{
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
                          fontFamily: 'var(--font-mono)',
                          fontSize: 10,
                          letterSpacing: 0.5,
                          textTransform: 'uppercase',
                          whiteSpace: 'nowrap',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          maxWidth: '100%',
                        }}
                      >
                        {lic.license_type.replace(' (Liquor)', '').replace(' (Beer)', '')}
                      </span>
                    </div>

                    {/* Municipality */}
                    <div
                      style={{
                        fontFamily: 'var(--font-mono)',
                        fontSize: 11,
                        color: 'var(--text-muted)',
                        letterSpacing: 0.3,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {lic.municipality}
                    </div>

                    {/* Status */}
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                      }}
                    >
                      <span
                        style={{
                          fontFamily: 'var(--font-mono)',
                          fontSize: 10,
                          fontWeight: 600,
                          letterSpacing: 1,
                          textTransform: 'uppercase',
                          color: statusColor(lic.status),
                          background: statusBg(lic.status),
                          border: `1px solid ${statusColor(lic.status)}30`,
                          borderRadius: 3,
                          padding: '2px 8px',
                        }}
                      >
                        {lic.status}
                      </span>
                    </div>
                  </div>
                )
              })}

              {/* Footer row */}
              {filtered.length > 0 && (
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
                    {filtered.length === licenses.length
                      ? `${filtered.length} licenses`
                      : `${filtered.length} of ${licenses.length} licenses`}
                  </span>
                  <span
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: 11,
                      color: 'var(--text-muted)',
                      letterSpacing: 0.5,
                    }}
                  >
                    Source: PA Liquor Control Board
                  </span>
                </div>
              )}
            </div>
          </>
        )}
      </main>
    </div>
  )
}
