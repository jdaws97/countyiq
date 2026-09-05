import { useState, type FormEvent } from 'react'
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
    <div className="search-block">
      <div className="search-prompt">
        Find a property, organization or project
      </div>
      <form onSubmit={handleSubmit} className="search-form" role="search">
        <svg className="search-icon" aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4.5 4.5" /></svg>
        <label className="sr-only" htmlFor="primary-search">Search properties, organizations, projects or places</label>
        <input
          id="primary-search"
          type="text"
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Address, organization, project or place..."
        />
        <button className="home-search-submit" type="submit">Search</button>
      </form>
      <div className="search-examples">Search by street address, parcel ID, organization, project name or municipality.</div>
    </div>
  )
}
