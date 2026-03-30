import { useState, FormEvent, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'

interface SearchResult {
  result_type: string
  title: string
  subtitle: string
  lat: number | null
  lng: number | null
  score: number
}

const TYPE_ICONS: Record<string, string> = {
  address: '📍',
  tax_claim: '💰',
  license: '🍺',
}

export default function SearchBar() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [loading, setLoading] = useState(false)
  const [showResults, setShowResults] = useState(false)
  const debounceRef = useRef<ReturnType<typeof setTimeout>>()
  const navigate = useNavigate()

  useEffect(() => {
    if (query.trim().length < 2) {
      setResults([])
      setShowResults(false)
      return
    }

    setLoading(true)
    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      fetch(`/api/search?q=${encodeURIComponent(query.trim())}&limit=10`)
        .then(r => r.json())
        .then((data: any) => {
          // API returns {mode, results, ...} — extract the results array
          const items = Array.isArray(data) ? data : (data.results || [])
          setResults(items)
          setShowResults(true)
          setLoading(false)
        })
        .catch(() => {
          setResults([])
          setLoading(false)
        })
    }, 300)

    return () => clearTimeout(debounceRef.current)
  }, [query])

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (query.trim().length >= 2) {
      setShowResults(false)
      navigate(`/search?q=${encodeURIComponent(query.trim())}`)
    }
  }

  return (
    <div style={{ marginBottom: 36, animation: 'fadeUp 0.6s ease-out', position: 'relative' }}>
      <div
        style={{
          fontFamily: 'var(--font-serif)',
          fontSize: 28,
          fontStyle: 'italic',
          color: 'var(--text-secondary)',
          marginBottom: 16,
          opacity: 0.8,
        }}
      >
        What are you looking for?
      </div>
      <form onSubmit={handleSubmit} style={{ position: 'relative' }}>
        <span
          style={{
            position: 'absolute',
            left: 18,
            top: '50%',
            transform: 'translateY(-50%)',
            color: 'var(--text-muted)',
            fontSize: 16,
            pointerEvents: 'none',
          }}
        >
          &#x2315;
        </span>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => results.length > 0 && setShowResults(true)}
          onBlur={() => setTimeout(() => setShowResults(false), 200)}
          placeholder="Search by address, owner name, or parcel ID..."
          autoFocus
          style={{
            width: '100%',
            background: 'var(--bg-panel)',
            border: '1px solid var(--border)',
            borderRadius: 6,
            padding: '16px 20px 16px 48px',
            fontFamily: 'var(--font-mono)',
            fontSize: 14,
            color: 'var(--text-primary)',
            outline: 'none',
            transition: 'border-color 0.2s, box-shadow 0.2s',
          }}
        />
      </form>

      {/* Live search results dropdown */}
      {showResults && results.length > 0 && (
        <div
          style={{
            position: 'absolute',
            left: 0,
            right: 0,
            top: '100%',
            marginTop: 4,
            background: 'var(--bg-panel)',
            border: '1px solid var(--border)',
            borderRadius: 6,
            overflow: 'hidden',
            zIndex: 50,
            boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
          }}
        >
          {results.map((r, i) => (
            <div
              key={`${r.title}-${r.subtitle}-${i}`}
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '10px 16px',
                borderBottom: i < results.length - 1 ? '1px solid var(--border)' : 'none',
                cursor: 'pointer',
                transition: 'background 0.15s',
              }}
              onMouseDown={() => {
                if (r.lat && r.lng) {
                  const pidn = (r as any).pidn || ''
                  navigate(`/map?lat=${r.lat}&lng=${r.lng}&zoom=17${pidn ? `&highlight=${pidn}` : ''}`)
                }
              }}
              onMouseEnter={(e) => { (e.currentTarget as HTMLDivElement).style.background = 'var(--bg-card-hover)' }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLDivElement).style.background = 'transparent' }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontSize: 14 }}>{TYPE_ICONS[r.result_type] || '📄'}</span>
                <div>
                  <div style={{ fontFamily: 'var(--font-sans)', fontSize: 14, color: 'var(--text-primary)' }}>
                    {r.title}
                  </div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
                    {r.subtitle}
                  </div>
                </div>
              </div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)' }}>
                {(r.score * 100).toFixed(0)}%
              </div>
            </div>
          ))}
        </div>
      )}

      {showResults && loading && (
        <div
          style={{
            position: 'absolute',
            left: 0,
            right: 0,
            top: '100%',
            marginTop: 4,
            background: 'var(--bg-panel)',
            border: '1px solid var(--border)',
            borderRadius: 6,
            padding: '16px',
            zIndex: 50,
            fontFamily: 'var(--font-mono)',
            fontSize: 12,
            color: 'var(--text-muted)',
            textAlign: 'center',
          }}
        >
          Searching...
        </div>
      )}

      {!showResults && (
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            color: 'var(--text-muted)',
            marginTop: 8,
            letterSpacing: 0.3,
          }}
        >
          Try:{' '}
          <kbd style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 3, padding: '1px 6px', fontSize: 10 }}>
            123 Main St
          </kbd>{' '}
          or{' '}
          <kbd style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 3, padding: '1px 6px', fontSize: 10 }}>
            KEYSTONE REALTY
          </kbd>
        </div>
      )}
    </div>
  )
}
