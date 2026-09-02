import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import PageShell from '../components/PageShell'
import { formatCurrency } from '../lib/format'
import type {
  TopDelinquentOwner as TopOwner,
  DelinquentParcelSummary as DelinquentParcel,
} from '../types/api'

type Tab = 'owners' | 'parcels'

export default function DelinquentOwners() {
  const [activeTab, setActiveTab] = useState<Tab>('owners')
  const [owners, setOwners] = useState<TopOwner[]>([])
  const [parcels, setParcels] = useState<DelinquentParcel[]>([])
  const [loadingOwners, setLoadingOwners] = useState(true)
  const [loadingParcels, setLoadingParcels] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/delinquent/top-owners?limit=50')
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then((data: TopOwner[]) => {
        setOwners(data)
        setLoadingOwners(false)
      })
      .catch((err) => {
        setError(err.message)
        setLoadingOwners(false)
      })

    fetch('/api/delinquent/parcels?limit=100')
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then((data: DelinquentParcel[]) => {
        setParcels(data)
        setLoadingParcels(false)
      })
      .catch((err) => {
        setError(err.message)
        setLoadingParcels(false)
      })
  }, [])

  const formatYears = (oldest: number | null, newest: number | null) => {
    if (oldest == null && newest == null) return ''
    if (oldest == null) return `${newest}`
    if (newest == null) return `${oldest}`
    return oldest === newest ? `${newest}` : `${oldest}\u2013${newest}`
  }

  const totalOwed = owners.reduce((sum, o) => sum + o.total_owed, 0)
  const loading = activeTab === 'owners' ? loadingOwners : loadingParcels

  return (
    <PageShell maxWidth={1200}>
        {/* Back link */}
        <Link
          to="/"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            color: 'var(--text-muted)',
            textDecoration: 'none',
            marginBottom: 32,
            letterSpacing: 0.5,
            transition: 'color 0.15s ease',
          }}
          onMouseEnter={(e) => {
            ;(e.currentTarget as HTMLAnchorElement).style.color = 'var(--text-secondary)'
          }}
          onMouseLeave={(e) => {
            ;(e.currentTarget as HTMLAnchorElement).style.color = 'var(--text-muted)'
          }}
        >
          &larr; Back to Home
        </Link>

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
            Intelligence
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
            Tax Delinquency
          </h1>
          <p
            style={{
              fontFamily: 'var(--font-sans)',
              fontSize: 14,
              color: 'var(--text-secondary)',
            }}
          >
            {!loadingOwners && owners.length > 0
              ? `${owners.length} top owners owing ${formatCurrency(totalOwed)}`
              : 'Loading delinquency data...'}
          </p>
        </div>

        {/* Tab bar */}
        <div
          style={{
            display: 'flex',
            gap: 0,
            marginBottom: 24,
            animationDelay: '0.05s',
            opacity: 0,
          }}
        >
          {([
            { key: 'owners' as Tab, label: 'Top Owners' },
            { key: 'parcels' as Tab, label: 'All Parcels' },
          ]).map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                fontWeight: 600,
                letterSpacing: 2,
                textTransform: 'uppercase',
                color: activeTab === tab.key ? 'var(--accent-gold)' : 'var(--text-muted)',
                background: activeTab === tab.key ? 'var(--bg-panel)' : 'transparent',
                border: '1px solid',
                borderColor: activeTab === tab.key ? 'var(--border-active)' : 'var(--border)',
                padding: '10px 24px',
                cursor: 'pointer',
                transition: 'all 0.15s ease',
                borderRadius: tab.key === 'owners' ? '6px 0 0 6px' : '0 6px 6px 0',
                marginLeft: tab.key === 'parcels' ? -1 : 0,
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>

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

        {/* Loading state */}
        {loading && !error && (
          <div
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 13,
              color: 'var(--text-muted)',
              textAlign: 'center',
              padding: '80px 0',
            }}
          >
            Loading {activeTab === 'owners' ? 'top owners' : 'parcels'}...
          </div>
        )}

        {/* Top Owners table */}
        {activeTab === 'owners' && !loadingOwners && !error && (
          <div
            style={{
              animationDelay: '0.1s',
              opacity: 0,
              border: '1px solid var(--border)',
              borderRadius: 8,
              overflow: 'hidden',
            }}
          >
            {/* Header */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: '56px 1fr 80px 100px 1fr 160px',
                padding: '12px 24px',
                background: 'var(--bg-panel)',
                borderBottom: '1px solid var(--border)',
              }}
            >
              {['#', 'Owner Name', 'Parcels', 'Years', 'Districts', 'Total Owed'].map(
                (col, i) => (
                  <div
                    key={col}
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: 10,
                      fontWeight: 600,
                      letterSpacing: 2,
                      textTransform: 'uppercase',
                      color: 'var(--text-muted)',
                      textAlign: i === 5 ? 'right' : 'left',
                    }}
                  >
                    {col}
                  </div>
                )
              )}
            </div>

            {/* Rows */}
            {owners.map((owner, idx) => {
              const isEven = idx % 2 === 0
              return (
                <div
                  key={owner.owner_name}
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '56px 1fr 80px 100px 1fr 160px',
                    padding: '14px 24px',
                    background: isEven ? 'var(--bg-panel)' : 'var(--bg-card)',
                    borderBottom:
                      idx < owners.length - 1 ? '1px solid var(--border)' : 'none',
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
                  {/* Rank */}
                  <div
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: 12,
                      color: 'var(--text-muted)',
                    }}
                  >
                    {idx + 1}
                  </div>

                  {/* Owner name */}
                  <div
                    style={{
                      fontFamily: 'var(--font-sans)',
                      fontSize: 14,
                      fontWeight: 600,
                      color: 'var(--text-primary)',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {owner.owner_name}
                  </div>

                  {/* Parcels */}
                  <div
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: 14,
                      color: 'var(--accent-blue)',
                    }}
                  >
                    {owner.parcel_count}
                  </div>

                  {/* Years */}
                  <div
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: 12,
                      color: 'var(--text-secondary)',
                    }}
                  >
                    {formatYears(owner.oldest_year, owner.newest_year)}
                  </div>

                  {/* Districts */}
                  <div
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: 11,
                      color: 'var(--text-muted)',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {owner.districts.join(', ')}
                  </div>

                  {/* Total owed */}
                  <div
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: 14,
                      fontWeight: 500,
                      color: 'var(--accent-red)',
                      textAlign: 'right',
                    }}
                  >
                    {formatCurrency(owner.total_owed)}
                  </div>
                </div>
              )
            })}

            {/* Footer */}
            {owners.length > 0 && (
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
                  {owners.length} owners
                </span>
                <span
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 11,
                    color: 'var(--text-muted)',
                    letterSpacing: 0.5,
                  }}
                >
                  Combined total:{' '}
                  <span style={{ color: 'var(--accent-red)' }}>
                    {formatCurrency(totalOwed)}
                  </span>
                </span>
              </div>
            )}
          </div>
        )}

        {/* All Parcels table */}
        {activeTab === 'parcels' && !loadingParcels && !error && (
          <div
            style={{
              animationDelay: '0.1s',
              opacity: 0,
              border: '1px solid var(--border)',
              borderRadius: 8,
              overflow: 'hidden',
            }}
          >
            {/* Header */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: '140px 1fr 1fr 180px 100px 140px',
                padding: '12px 24px',
                background: 'var(--bg-panel)',
                borderBottom: '1px solid var(--border)',
              }}
            >
              {['PIDN', 'Owner', 'Address', 'District', 'Years', 'Total Owed'].map(
                (col, i) => (
                  <div
                    key={col}
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: 10,
                      fontWeight: 600,
                      letterSpacing: 2,
                      textTransform: 'uppercase',
                      color: 'var(--text-muted)',
                      textAlign: i === 5 ? 'right' : 'left',
                    }}
                  >
                    {col}
                  </div>
                )
              )}
            </div>

            {/* Rows */}
            {parcels.map((parcel, idx) => {
              const isEven = idx % 2 === 0
              return (
                <div
                  key={parcel.pidn}
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '140px 1fr 1fr 180px 100px 140px',
                    padding: '14px 24px',
                    background: isEven ? 'var(--bg-panel)' : 'var(--bg-card)',
                    borderBottom:
                      idx < parcels.length - 1 ? '1px solid var(--border)' : 'none',
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
                  {/* PIDN */}
                  <div
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: 12,
                      color: 'var(--accent-blue)',
                      letterSpacing: 0.5,
                    }}
                  >
                    {parcel.pidn}
                  </div>

                  {/* Owner */}
                  <div
                    style={{
                      fontFamily: 'var(--font-sans)',
                      fontSize: 13,
                      fontWeight: 500,
                      color: 'var(--text-primary)',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {parcel.owner_name}
                  </div>

                  {/* Address */}
                  <div
                    style={{
                      fontFamily: 'var(--font-sans)',
                      fontSize: 13,
                      color: 'var(--text-secondary)',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {parcel.property_address ?? '—'}
                  </div>

                  {/* District */}
                  <div
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: 11,
                      color: 'var(--text-muted)',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {parcel.tax_district_name ?? '—'}
                  </div>

                  {/* Years delinquent */}
                  <div
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: 13,
                      color: 'var(--text-secondary)',
                    }}
                  >
                    {parcel.years_delinquent}
                  </div>

                  {/* Total owed */}
                  <div
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: 14,
                      fontWeight: 500,
                      color: 'var(--accent-red)',
                      textAlign: 'right',
                    }}
                  >
                    {formatCurrency(parcel.total_owed)}
                  </div>
                </div>
              )
            })}

            {/* Footer */}
            {parcels.length > 0 && (
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
                  {parcels.length} parcels
                </span>
                <span
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 11,
                    color: 'var(--text-muted)',
                    letterSpacing: 0.5,
                  }}
                >
                  Combined total:{' '}
                  <span style={{ color: 'var(--accent-red)' }}>
                    {formatCurrency(parcels.reduce((sum, p) => sum + p.total_owed, 0))}
                  </span>
                </span>
              </div>
            )}
          </div>
        )}
    </PageShell>
  )
}
