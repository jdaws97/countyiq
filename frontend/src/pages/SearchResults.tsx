import { useEffect, useState } from 'react'
import { useSearchParams, Link, useNavigate } from 'react-router-dom'
import Nav from '../components/Nav'

interface SearchResult {
  result_type?: string
  title?: string
  subtitle?: string
  lat?: number | null
  lng?: number | null
  score?: number
  [key: string]: any
}

interface SearchResponse {
  mode: 'fuzzy' | 'smart' | 'redirect'
  description?: string
  redirect_path?: string
  results: SearchResult[]
}

const TYPE_LABELS: Record<string, { label: string; color: string }> = {
  address: { label: 'Address', color: 'var(--accent-blue)' },
  tax_claim: { label: 'Tax Delinquent', color: 'var(--accent-red)' },
  license: { label: 'Liquor License', color: 'var(--accent-green)' },
  parcel: { label: 'Parcel', color: 'var(--accent-cyan)' },
}

// Simple cache to avoid re-querying on back navigation
const searchCache: Record<string, { mode: string; description: string; results: SearchResult[] }> = {}

export default function SearchResults() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const query = searchParams.get('q') || ''
  const [results, setResults] = useState<SearchResult[]>([])
  const [mode, setMode] = useState<string>('fuzzy')
  const [description, setDescription] = useState<string>('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (query.length < 2) {
      setResults([])
      setLoading(false)
      return
    }

    // Check cache first
    const cached = searchCache[query]
    if (cached) {
      setMode(cached.mode)
      setDescription(cached.description)
      setResults(cached.results)
      setLoading(false)
      return
    }

    setLoading(true)
    fetch(`/api/search?q=${encodeURIComponent(query)}&limit=50`)
      .then(r => r.json())
      .then((data: SearchResponse) => {
        if (data.mode === 'redirect' && data.redirect_path) {
          navigate(data.redirect_path)
          return
        }
        setMode(data.mode)
        setDescription(data.description || '')
        setResults(data.results || [])
        setLoading(false)
        // Cache the results
        searchCache[query] = { mode: data.mode, description: data.description || '', results: data.results || [] }
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
          {mode === 'smart' && description && (
            <p style={{
              fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--accent-gold)',
              background: 'rgba(212, 168, 67, 0.1)', border: '1px solid rgba(212, 168, 67, 0.2)',
              borderRadius: 4, padding: '6px 12px', marginTop: 8, display: 'inline-block',
            }}>
              AI: {description}
            </p>
          )}
          <p style={{ display: 'none' }}>
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

        {!loading && results.length > 0 && mode === 'smart' && (
          <div style={{
            border: '1px solid var(--border)', borderRadius: 8, overflow: 'hidden',
            animation: 'fadeUp 0.5s ease both', animationDelay: '0.1s', opacity: 0,
          }}>
            {results.map((r, idx) => {
              const link = r._link as string | undefined
              const entries = Object.entries(r).filter(([k, v]) => v !== null && v !== '' && !k.startsWith('_'))
              const Wrapper = link ? Link : 'div' as any
              const wrapperProps = link ? { to: link, style: { textDecoration: 'none', color: 'inherit', display: 'block' } } : {}
              return (
                <Wrapper key={idx} {...wrapperProps}>
                <div style={{
                  padding: '20px 24px',
                  background: idx % 2 === 0 ? 'var(--bg-panel)' : 'var(--bg-card)',
                  borderBottom: idx < results.length - 1 ? '1px solid var(--border)' : 'none',
                  transition: 'background 0.15s',
                  cursor: link ? 'pointer' : 'default',
                }}
                onMouseEnter={e => { (e.currentTarget as HTMLDivElement).style.background = 'var(--bg-card-hover)' }}
                onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.background = idx % 2 === 0 ? 'var(--bg-panel)' : 'var(--bg-card)' }}
                >
                  <div style={{
                    display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
                    gap: '10px 24px',
                  }}>
                    {entries.map(([k, v]) => (
                      <div key={k}>
                        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: 1.5, textTransform: 'uppercase' as const, color: 'var(--text-muted)', marginBottom: 2 }}>
                          {k}
                        </div>
                        <div style={{
                          fontFamily: String(v).startsWith('$') || /^\d/.test(String(v)) ? 'var(--font-mono)' : 'var(--font-sans)',
                          fontSize: 14,
                          fontWeight: String(v).startsWith('$') ? 600 : 400,
                          color: String(v).startsWith('$') ? 'var(--accent-green)' : 'var(--text-primary)',
                        }}>
                          {String(v)}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
                </Wrapper>
              )
            })}
          </div>
        )}

        {!loading && results.length > 0 && mode === 'fuzzy' && (
          <div style={{
            border: '1px solid var(--border)', borderRadius: 8, overflow: 'hidden',
            animation: 'fadeUp 0.5s ease both', animationDelay: '0.1s', opacity: 0,
          }}>
            {/* Header row */}
            <div style={{
              display: 'grid', gridTemplateColumns: '100px 1fr 1fr 80px 80px',
              padding: '12px 24px', background: 'var(--bg-panel)',
              borderBottom: '1px solid var(--border)',
            }}>
              {['Type', 'Result', 'Details', 'Match', ''].map((col, i) => (
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
                key={`${r.title}-${r.subtitle}-${idx}`}
                style={{
                  display: 'grid', gridTemplateColumns: '100px 1fr 1fr 80px 80px',
                  padding: '14px 24px', alignItems: 'center',
                  background: idx % 2 === 0 ? 'var(--bg-panel)' : 'var(--bg-card)',
                  borderBottom: idx < results.length - 1 ? '1px solid var(--border)' : 'none',
                  transition: 'background 0.15s',
                }}
                onMouseEnter={e => { (e.currentTarget as HTMLDivElement).style.background = 'var(--bg-card-hover)' }}
                onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.background = idx % 2 === 0 ? 'var(--bg-panel)' : 'var(--bg-card)' }}
              >
                <div>
                  {(() => {
                    const t = TYPE_LABELS[r.result_type || ''] || { label: r.result_type || 'result', color: 'var(--text-muted)' }
                    return (
                      <span style={{
                        padding: '2px 8px', borderRadius: 3, fontSize: 9,
                        letterSpacing: 1, textTransform: 'uppercase' as const,
                        fontFamily: 'var(--font-mono)',
                        color: t.color, background: `${t.color}15`, border: `1px solid ${t.color}30`,
                      }}>
                        {t.label}
                      </span>
                    )
                  })()}
                </div>
                <div style={{
                  fontFamily: 'var(--font-sans)', fontSize: 14, fontWeight: 500,
                  color: 'var(--text-primary)',
                }}>
                  {r.title}
                </div>
                <div style={{
                  fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-secondary)',
                }}>
                  {r.subtitle}
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
