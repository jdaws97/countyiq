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
        What are you looking for?
      </div>
      <form onSubmit={handleSubmit} className="search-form" role="search">
        <span aria-hidden="true">&#x2315;</span>
        <label className="sr-only" htmlFor="primary-search">Search by address, PIDN, municipality, or public organization</label>
        <input
          id="primary-search"
          type="text"
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Address, PIDN, municipality, or public organization..."
        />
      </form>
      <div className="search-examples">
        Try:{' '}
        <kbd>York Township</kbd>{' '}
        or{' '}
        <kbd>1 main st</kbd>{' '}
        or{' '}
        <kbd>0000000000001</kbd>
        {' '}or{' '}
        <kbd>Acme Holdings LLC</kbd>
      </div>
    </div>
  )
}
