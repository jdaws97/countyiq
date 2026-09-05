import { useEffect, useRef, useState, type FormEvent } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'

import { watchSyncState, signOut } from '../lib/watchSync'
import { siteUrls } from '../lib/siteUrls'
import { useCountyMeta } from '../lib/useCountyMeta'

const NAV_ITEMS = [
  { to: '/', label: 'Workspace' },
  { to: '/feed', label: 'Activity' },
  { to: '/radar', label: 'Radar' },
  { to: '/map', label: 'Map' },
  { to: '/watch', label: 'Watches' },
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
  const [account,setAccount]=useState(()=>watchSyncState().account)
  useEffect(()=>{
    const update=()=>setAccount(watchSyncState().account)
    window.addEventListener('countyiq-watch-sync-changed',update)
    return ()=>window.removeEventListener('countyiq-watch-sync-changed',update)
  },[])
  const moreRef = useRef<HTMLDetailsElement>(null)
  const location = useLocation()
  useEffect(() => {
    if (moreRef.current) moreRef.current.open = false
  }, [location.pathname, location.search])
  const navRef = useRef<HTMLElement>(null)
  useEffect(() => {
    const nav = navRef.current
    if (!nav) return
    const updateHeight = () => document.documentElement.style.setProperty('--nav-height', nav.getBoundingClientRect().height + 'px')
    updateHeight()
    const observer = new ResizeObserver(updateHeight)
    observer.observe(nav)
    return () => {
      observer.disconnect()
      document.documentElement.style.removeProperty('--nav-height')
    }
  }, [])
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
    <nav ref={navRef} className="primary-nav">
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
          placeholder="Property, organization, project"
        />
        <button className="nav-search-submit" type="submit">Search</button>
      </form>

      <div className="primary-nav-links" aria-label="Primary navigation">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) => `primary-nav-link${isActive ? ' primary-nav-link-active' : ''}`}
          >
            {item.label}
          </NavLink>
        ))}
        <details ref={moreRef} className="nav-more" onKeyDown={event => {
          if (event.key === 'Escape' && moreRef.current) {
            moreRef.current.open = false
            moreRef.current.querySelector('summary')?.focus()
          }
        }} onBlur={event => {
          if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
            event.currentTarget.open = false
          }
        }}>
          <summary className="primary-nav-link">More</summary>
          <div className="nav-more-panel">
            <NavLink to="/organizations">Organizations</NavLink>
            <NavLink to="/municipalities">Municipalities</NavLink>
            <NavLink to="/compare">Compare properties</NavLink>
            <a href={siteUrls(window.location).marketing}>About CountyIQ</a>
            <button type="button" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>
              Use {theme === 'dark' ? 'light' : 'dark'} theme
            </button>
            {account?.authenticated
              ? <button type="button" onClick={signOut}>Sign out</button>
              : <a href={account?.login_url ?? "/app"}>Sign in</a>}
          </div>
        </details>
      </div>
    </nav>
  )
}
