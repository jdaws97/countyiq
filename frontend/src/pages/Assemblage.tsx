import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import BackButton from '../components/BackButton'
import PageShell from '../components/PageShell'
import { formatCurrencyCompact } from '../lib/format'
import { getPropertyClassLabel, getSchoolDistrictLabel } from '../lib/propertyLabels'
import type { AssemblageCluster, AssemblageResponse } from '../types/api'

export default function Assemblage() {
  const navigate = useNavigate()
  const [clusters, setClusters] = useState<AssemblageCluster[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [minParcels, setMinParcels] = useState('3')
  const [expanded, setExpanded] = useState<string | null>(null)

  useEffect(() => {
    const cacheKey = `assemblage_${minParcels}`
    const cached = window.__assemblageCache?.[cacheKey]
    if (cached) {
      setClusters(cached)
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    fetch(`/api/scores/assemblage?min_parcels=${minParcels}&min_acres=0.5&limit=50`)
      .then(r => {
        if (!r.ok) throw new Error(`Assemblage request failed (${r.status})`)
        return r.json()
      })
      .then((d: AssemblageResponse) => {
        const items = d.clusters || []
        setClusters(items)
        if (!window.__assemblageCache) window.__assemblageCache = {}
        window.__assemblageCache[cacheKey] = items
        setLoading(false)
      })
      .catch((err) => {
        console.error('Failed to load assemblage clusters', err)
        setError(err.message)
        setLoading(false)
      })
  }, [minParcels])

  return (
    <PageShell maxWidth={1100}>
      <BackButton onClick={() => navigate(-1)} />

        <div style={{ animation: 'fadeUp 0.4s ease both', marginBottom: 32 }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, letterSpacing: 3, textTransform: 'uppercase', color: 'var(--accent-purple)', marginBottom: 8 }}>Intelligence</div>
          <h1 style={{ fontFamily: 'var(--font-mono)', fontSize: 28, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 8 }}>Assemblage Opportunities</h1>
          <p style={{ fontFamily: 'var(--font-sans)', fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            Clusters of adjacent parcels with shared distress signals — delinquency, vacancy, fragmented ownership.
            Each cluster represents a potential land assembly acquisition.
          </p>
        </div>

        {/* Filters */}
        <div style={{ display: 'flex', gap: 12, marginBottom: 24 }}>
          <select value={minParcels} onChange={e => setMinParcels(e.target.value)} style={{
            background: 'var(--bg-panel)', border: '1px solid var(--border)', borderRadius: 4,
            padding: '6px 12px', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-primary)',
          }}>
            <option value="2">2+ adjacent</option>
            <option value="3">3+ adjacent</option>
            <option value="5">5+ adjacent</option>
            <option value="10">10+ adjacent</option>
          </select>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', display: 'flex', alignItems: 'center' }}>
            {loading ? 'Loading...' : `${clusters.length} clusters found`}
          </span>
        </div>

        {error && (
          <div style={{
            fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--accent-red)',
            padding: 24, background: 'rgba(224, 82, 82, 0.08)',
            border: '1px solid rgba(224, 82, 82, 0.2)', borderRadius: 6, marginBottom: 24,
          }}>
            Failed to load data: {error}
          </div>
        )}

        {/* Results */}
        {!loading && clusters.map((c, i) => {
          const isExpanded = expanded === c.seed_pidn
          return (
            <div key={c.seed_pidn} style={{
              marginBottom: 12,
              border: '1px solid var(--border)',
              borderRadius: 8,
              overflow: 'hidden',
              animation: `fadeUp 0.4s ease ${0.05 + i * 0.02}s both`,
              opacity: 0,
            }}>
              {/* Cluster header */}
              <div
                onClick={() => setExpanded(isExpanded ? null : c.seed_pidn)}
                style={{
                  display: 'grid', gridTemplateColumns: '1fr 80px 80px 80px 80px 70px 90px',
                  padding: '18px 24px', alignItems: 'center', cursor: 'pointer',
                  background: 'var(--bg-panel)', transition: 'background 0.15s',
                }}
                onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'var(--bg-card-hover)' }}
                onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'var(--bg-panel)' }}
              >
                <div>
                  <div style={{ fontFamily: 'var(--font-sans)', fontSize: 15, fontWeight: 600, color: 'var(--text-primary)' }}>
                    {c.seed_owner}
                  </div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
                    {c.seed_address || c.seed_pidn} · {getSchoolDistrictLabel(c.school_dis)} · {getPropertyClassLabel(c.seed_class)}
                  </div>
                </div>
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 18, fontWeight: 700, color: 'var(--accent-blue)' }}>{c.adjacent_count}</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-muted)', letterSpacing: 1, textTransform: 'uppercase' }}>Adjacent</div>
                </div>
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 18, fontWeight: 700, color: 'var(--accent-red)' }}>{c.delinquent_neighbors}</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-muted)', letterSpacing: 1, textTransform: 'uppercase' }}>Delinquent</div>
                </div>
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 18, fontWeight: 700, color: 'var(--accent-green)' }}>{c.vacant_neighbors}</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-muted)', letterSpacing: 1, textTransform: 'uppercase' }}>Vacant</div>
                </div>
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 18, fontWeight: 700, color: 'var(--accent-cyan)' }}>{c.unique_owners || '?'}</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-muted)', letterSpacing: 1, textTransform: 'uppercase' }}>Owners</div>
                </div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-secondary)', textAlign: 'right' }}>
                  {c.total_acres?.toFixed(1)} ac
                </div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--accent-green)', textAlign: 'right' }}>
                  {formatCurrencyCompact(c.total_assessed)}
                </div>
              </div>

              {/* View on Map + Expanded details */}
              {isExpanded && (
                <div style={{ padding: '10px 24px', background: 'var(--bg-card)', borderTop: '1px solid var(--border)', display: 'flex', gap: 12 }}>
                  <Link to={`/property/${c.seed_pidn}`} style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--accent-blue)', textDecoration: 'none', padding: '4px 12px', border: '1px solid var(--border)', borderRadius: 4 }}>
                    View Seed Property
                  </Link>
                  {c.lat && c.lng && (() => {
                    const allPidns = [c.seed_pidn, ...(c.neighbors || []).map(n => n.pidn)].join(',')
                    return (
                      <Link to={`/map?cluster=${allPidns}&seed=${c.seed_pidn}&zoom=18&lat=${c.lat}&lng=${c.lng}`} style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--accent-purple)', textDecoration: 'none', padding: '4px 12px', border: '1px solid var(--border)', borderRadius: 4 }}>
                        View Cluster on Map ({(c.neighbors || []).length + 1} parcels)
                      </Link>
                    )
                  })()}
                </div>
              )}
              {isExpanded && (() => {
                // Compute ownership breakdown
                const allParcels = [{ owner: c.seed_owner, pidn: c.seed_pidn }, ...(c.neighbors || []).map(n => ({ owner: n.owner, pidn: n.pidn }))]
                const ownerCounts: Record<string, number> = {}
                allParcels.forEach(p => { ownerCounts[p.owner] = (ownerCounts[p.owner] || 0) + 1 })
                const totalInCluster = allParcels.length
                const sortedOwners = Object.entries(ownerCounts).sort((a, b) => b[1] - a[1])

                return (
                <div style={{ borderTop: '1px solid var(--border)' }}>
                  {/* Ownership breakdown */}
                  <div style={{ padding: '12px 24px', background: 'rgba(74,127,255,0.05)', borderBottom: '1px solid var(--border)' }}>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: 1.5, textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 8 }}>Ownership Concentration</div>
                    <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
                      {sortedOwners.slice(0, 4).map(([owner, count]) => (
                        <div key={owner} style={{ fontFamily: 'var(--font-mono)', fontSize: 11 }}>
                          <span style={{ color: count > 1 ? 'var(--accent-blue)' : 'var(--text-muted)', fontWeight: count > 1 ? 600 : 400 }}>
                            {owner.substring(0, 25)}{owner.length > 25 ? '...' : ''}
                          </span>
                          <span style={{ color: 'var(--text-muted)', marginLeft: 6 }}>
                            {count}/{totalInCluster} ({Math.round(count / totalInCluster * 100)}%)
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div style={{ padding: '10px 24px', background: 'var(--bg-card)', fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: 1.5, textTransform: 'uppercase', color: 'var(--text-muted)', display: 'grid', gridTemplateColumns: '1fr 1fr 100px 70px 100px' }}>
                    <div>Owner</div><div>Address</div><div style={{ textAlign: 'right' }}>Assessed</div><div style={{ textAlign: 'right' }}>Acres</div><div>Status</div>
                  </div>
                  {/* Seed parcel */}
                  <Link to={`/property/${c.seed_pidn}`} style={{ textDecoration: 'none', color: 'inherit', display: 'grid', gridTemplateColumns: '1fr 1fr 100px 70px 100px', padding: '10px 20px', background: 'rgba(224,82,82,0.08)', borderBottom: '1px solid var(--border)' }}>
                    <div style={{ fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--text-primary)', fontWeight: 600 }}>{c.seed_owner}</div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-secondary)' }}>{c.seed_address}</div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-secondary)', textAlign: 'right' }}>{formatCurrencyCompact(c.seed_assessed)}</div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, textAlign: 'right' }}>{c.seed_acres?.toFixed(1)}</div>
                    <div style={{ display: 'flex', gap: 4 }}><Badge color="var(--accent-red)">Delinquent</Badge> <Badge color="var(--accent-blue)">Seed</Badge></div>
                  </Link>
                  {/* Neighbors */}
                  {(c.neighbors || []).map((n, j: number) => (
                    <Link key={n.pidn} to={`/property/${n.pidn}`} style={{
                      textDecoration: 'none', color: 'inherit',
                      display: 'grid', gridTemplateColumns: '1fr 1fr 100px 70px 100px',
                      padding: '10px 20px',
                      background: j % 2 === 0 ? 'var(--bg-panel)' : 'var(--bg-card)',
                      borderBottom: '1px solid var(--border)',
                      transition: 'background 0.15s',
                    }}
                      onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'var(--bg-card-hover)' }}
                      onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = j % 2 === 0 ? 'var(--bg-panel)' : 'var(--bg-card)' }}
                    >
                      <div style={{ fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--text-primary)' }}>{n.owner}</div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-secondary)' }}>{n.address}</div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-secondary)', textAlign: 'right' }}>{formatCurrencyCompact(n.assessed)}</div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, textAlign: 'right' }}>{n.acres ? Number(n.acres).toFixed(1) : '--'}</div>
                      <div style={{ display: 'flex', gap: 4 }}>
                        {n.delinquent && <Badge color="var(--accent-red)">Delq</Badge>}
                        {n.vacant && <Badge color="var(--accent-gold)">Vacant</Badge>}
                        {!n.delinquent && !n.vacant && <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)' }}>Current</span>}
                      </div>
                    </Link>
                  ))}
                </div>
                )
              })()}
            </div>
          )
        })}
    </PageShell>
  )
}

function Badge({ color, children }: { color: string; children: React.ReactNode }) {
  return (
    <span style={{
      display: 'inline-block', padding: '1px 6px', borderRadius: 3,
      fontFamily: 'var(--font-mono)', fontSize: 9, fontWeight: 600,
      color, background: `${color}20`, border: `1px solid ${color}40`,
    }}>
      {children}
    </span>
  )
}
