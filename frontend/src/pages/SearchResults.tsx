import { useEffect, useState } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import Nav from '../components/Nav'

interface SearchResult {
  add_number: number
  street_name: string
  st_pos_typ: string
  inc_muni: string
  full_address: string
  lat: number | null
  lng: number | null
  score: number
}

export default function SearchResults() {
  const [searchParams] = useSearchParams()
  const query = searchParams.get('q') || ''
  const [results, setResults] = useState<SearchResult[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (query.length < 2) {
      setResults([])
      setLoading(false)
      return
    }
    setLoading(true)
    fetch(`/api/search?q=${encodeURIComponent(query)}&limit=50`)
      .then(r => r.json())
      .then((data: SearchResult[]) => {
        setResults(data)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [query])

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-deep)' }}>
      <Nav />
      <main style={{ maxWidth: 1200, margin: '0 auto', padding: '48px 32px' }}>

        {/* Header */}
        <div style={{ marginBottom: 32, animation: 'fadeUp 0.4s ease both' }}>
          <Link to="/" style={{
            fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)',
            textDecoration: 'none', letterSpacing: 1,
          }}>
            &larr; Back to Home
          </Link>
          <h1 style={{
            fontFamily: 'var(--font-mono)', fontSize: 24, fontWeight: 600,
            color: 'var(--text-primary)', marginTop: 12, marginBottom: 4,
          }}>
            Search Results
          </h1>
          <p style={{
            fontFamily: 'var(--font-sans)', fontSize: 14, color: 'var(--text-secondary)',
          }}>
            {loading ? 'Searching...' : `${results.length} results for "${query}"`}
          </p>
        </div>

        {/* Results */}
        {!loading && results.length === 0 && (
          <div style={{
            fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--text-muted)',
            textAlign: 'center', padding: '60px 0',
          }}>
            No results found for "{query}"
          </div>
        )}

        {!loading && results.length > 0 && (
          <div style={{
            border: '1px solid var(--border)', borderRadius: 8, overflow: 'hidden',
            animation: 'fadeUp 0.5s ease both', animationDelay: '0.1s', opacity: 0,
          }}>
            {/* Header row */}
            <div style={{
              display: 'grid', gridTemplateColumns: '1fr 200px 100px 80px',
              padding: '12px 24px', background: 'var(--bg-panel)',
              borderBottom: '1px solid var(--border)',
            }}>
              {['Address', 'Municipality', 'Match', ''].map((col, i) => (
                <div key={col} style={{
                  fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: 600,
                  letterSpacing: 2, textTransform: 'uppercase' as const,
                  color: 'var(--text-muted)', textAlign: i >= 2 ? 'right' : 'left',
                }}>
                  {col}
                </div>
              ))}
            </div>

            {/* Result rows */}
            {results.map((r, idx) => (
              <div
                key={`${r.full_address}-${r.inc_muni}-${idx}`}
                style={{
                  display: 'grid', gridTemplateColumns: '1fr 200px 100px 80px',
                  padding: '14px 24px', alignItems: 'center',
                  background: idx % 2 === 0 ? 'var(--bg-panel)' : 'var(--bg-card)',
                  borderBottom: idx < results.length - 1 ? '1px solid var(--border)' : 'none',
                  transition: 'background 0.15s',
                }}
                onMouseEnter={e => { (e.currentTarget as HTMLDivElement).style.background = 'var(--bg-card-hover)' }}
                onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.background = idx % 2 === 0 ? 'var(--bg-panel)' : 'var(--bg-card)' }}
              >
                <div style={{
                  fontFamily: 'var(--font-sans)', fontSize: 14, fontWeight: 500,
                  color: 'var(--text-primary)',
                }}>
                  {r.full_address}
                </div>
                <div style={{
                  fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-secondary)',
                }}>
                  <span style={{
                    padding: '2px 8px', borderRadius: 3,
                    background: 'rgba(74, 127, 255, 0.08)',
                    border: '1px solid rgba(74, 127, 255, 0.15)',
                    color: 'var(--accent-blue)', fontSize: 10,
                    letterSpacing: 1, textTransform: 'uppercase' as const,
                  }}>
                    {r.inc_muni}
                  </span>
                </div>
                <div style={{
                  fontFamily: 'var(--font-mono)', fontSize: 12,
                  color: 'var(--text-muted)', textAlign: 'right',
                }}>
                  {(r.score * 100).toFixed(0)}%
                </div>
                <div style={{ textAlign: 'right' }}>
                  {r.lat && r.lng && (
                    <Link
                      to={`/map?lat=${r.lat}&lng=${r.lng}&zoom=16`}
                      style={{
                        fontFamily: 'var(--font-mono)', fontSize: 10,
                        color: 'var(--accent-blue)', textDecoration: 'none',
                        padding: '4px 8px', border: '1px solid var(--border)',
                        borderRadius: 4,
                      }}
                    >
                      Map
                    </Link>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  )
}
