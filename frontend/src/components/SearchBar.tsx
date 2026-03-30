import { useState, FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'

export default function SearchBar() {
  const [query, setQuery] = useState('')
  const navigate = useNavigate()

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (query.trim().length >= 2) {
      navigate(`/search?q=${encodeURIComponent(query.trim())}`)
    }
  }

  return (
    <div style={{ marginBottom: 36, animation: 'fadeUp 0.6s ease-out' }}>
      <div style={{
        fontFamily: 'var(--font-serif)', fontSize: 28, fontStyle: 'italic',
        color: 'var(--text-secondary)', marginBottom: 16, opacity: 0.8,
      }}>
        What are you looking for?
      </div>
      <form onSubmit={handleSubmit} style={{ position: 'relative' }}>
        <span style={{
          position: 'absolute', left: 18, top: '50%', transform: 'translateY(-50%)',
          color: 'var(--text-muted)', fontSize: 16, pointerEvents: 'none',
        }}>&#x2315;</span>
        <input
          type="text"
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Search by address, owner name, or parcel ID..."
          autoFocus
          style={{
            width: '100%', background: 'var(--bg-panel)', border: '1px solid var(--border)',
            borderRadius: 6, padding: '16px 20px 16px 48px',
            fontFamily: 'var(--font-mono)', fontSize: 14, color: 'var(--text-primary)', outline: 'none',
          }}
        />
      </form>
      <div style={{
        fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', marginTop: 8, letterSpacing: 0.3,
      }}>
        Try:{' '}
        <kbd style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 3, padding: '1px 6px', fontSize: 10 }}>brian daws</kbd>{' '}
        or{' '}
        <kbd style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 3, padding: '1px 6px', fontSize: 10 }}>breweries in 17404</kbd>{' '}
        or{' '}
        <kbd style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 3, padding: '1px 6px', fontSize: 10 }}>vacant delinquent land</kbd>
      </div>
    </div>
  )
}
