import { useEffect, useState, type FormEvent } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'

import { useCountyMeta } from '../lib/useCountyMeta'

const NAV_ITEMS = [
  { to: '/feed', label: 'Feed' },
  { to: '/radar', label: 'Radar' },
  { to: '/municipalities', label: 'Municipalities' },
  { to: '/map', label: 'Map' },
  { to: '/watch', label: 'Watch' },
  { to: '/compare', label: 'Compare' },
]

function getInitialTheme(): string {
  // Light is the primary reading theme; dark is an explicit choice.
  try {
    return localStorage.getItem('countyiq_theme') || 'light'
  } catch {
    return 'light'
  }
}

export default function Nav() {
  const county = useCountyMeta()
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [theme, setTheme] = useState(getInitialTheme)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try {
      localStorage.setItem('countyiq_theme', theme)
    } catch {
      // Storage can be unavailable in hardened/private browser contexts.
    }
  }, [theme])

  const submitSearch = (event: FormEvent) => {
    event.preventDefault()
    const trimmed = query.trim()
    if (trimmed.length < 2) return
    navigate(`/search?q=${encodeURIComponent(trimmed)}`)
    setQuery('')
  }

  return (
    <nav className="primary-nav">
      <NavLink to="/" className="brand-link">
        <div className="brand-mark">CIQ</div>
        <div>
          <div className="brand-name">CountyIQ</div>
          <div className="brand-county">{county.county_name} · {county.state}</div>
        </div>
      </NavLink>

      <form className="nav-search" role="search" onSubmit={submitSearch}>
        <label className="sr-only" htmlFor="global-search">Search CountyIQ</label>
        <span aria-hidden="true">⌕</span>
        <input
          id="global-search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Address, public organization, or PIDN"
        />
        <button className="nav-search-submit" type="submit">Search</button>
      </form>

      <div className="primary-nav-links" aria-label="Primary navigation">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) => `primary-nav-link${isActive ? ' primary-nav-link-active' : ''}`}
          >
            {item.label === 'Watch' ? '★ ' : ''}{item.label}
          </NavLink>
        ))}
        <button
          className="theme-toggle"
          type="button"
          aria-label={`Use ${theme === 'dark' ? 'light' : 'dark'} theme`}
          title={`Use ${theme === 'dark' ? 'light' : 'dark'} theme`}
          onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
        >
          {theme === 'dark' ? '☀' : '☾'}
        </button>
      </div>
    </nav>
  )
}
