import { useState, FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'

export default function SearchBar() {
  const [query, setQuery] = useState('')
  const navigate = useNavigate()

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    const trimmed = query.trim()
    if (trimmed) {
      navigate(`/search?q=${encodeURIComponent(trimmed)}`)
    }
  }

  return (
    <div style={{ marginBottom: 36, animation: 'fadeUp 0.6s ease-out' }}>
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
          onFocus={(e) => {
            e.currentTarget.style.borderColor = 'var(--accent-gold-dim)'
            e.currentTarget.style.boxShadow = '0 0 0 3px rgba(212, 168, 67, 0.08)'
          }}
          onBlur={(e) => {
            e.currentTarget.style.borderColor = 'var(--border)'
            e.currentTarget.style.boxShadow = 'none'
          }}
        />
      </form>
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
        <kbd
          style={{
            background: 'var(--bg-card)',
            border: '1px solid var(--border)',
            borderRadius: 3,
            padding: '1px 6px',
            fontSize: 10,
          }}
        >
          123 Main St
        </kbd>{' '}
        or{' '}
        <kbd
          style={{
            background: 'var(--bg-card)',
            border: '1px solid var(--border)',
            borderRadius: 3,
            padding: '1px 6px',
            fontSize: 10,
          }}
        >
          KEYSTONE REALTY
        </kbd>{' '}
        or{' '}
        <kbd
          style={{
            background: 'var(--bg-card)',
            border: '1px solid var(--border)',
            borderRadius: 3,
            padding: '1px 6px',
            fontSize: 10,
          }}
        >
          4300006006500
        </kbd>
      </div>
    </div>
  )
}
