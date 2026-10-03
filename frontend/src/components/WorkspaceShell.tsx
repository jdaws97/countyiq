import {
  useEffect,
  useId,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
  type ReactNode,
} from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'

import { signOut, watchSyncState } from '../lib/watchSync'
import { useCountyMeta } from '../lib/useCountyMeta'
import './WorkspaceShell.css'

type WorkspaceShellProps = {
  children: ReactNode
  className?: string
  maxWidth?: number
  wide?: boolean
}

type NavigationItem = {
  icon: IconName
  label: string
  to: string
  end?: boolean
}

type IconName =
  'activity' | 'building' | 'compare' | 'home' | 'map' | 'pin' | 'properties' | 'watch'

const NAVIGATION_GROUPS: Array<{ label: string; items: NavigationItem[] }> = [
  {
    label: 'Explore',
    items: [
      { to: '/sites', label: 'Site inquiries', icon: 'home' },
      { to: '/overview', label: 'County overview', icon: 'activity' },
      { to: '/feed', label: 'Activity', icon: 'activity' },
      { to: '/intelligence', label: 'Emerging intelligence', icon: 'activity' },
      { to: '/map', label: 'Map', icon: 'map' },
    ],
  },
  {
    label: 'Research',
    items: [
      { to: '/radar', label: 'Properties', icon: 'properties' },
      { to: '/organizations', label: 'Organizations', icon: 'building' },
      { to: '/municipalities', label: 'Municipalities', icon: 'pin' },
    ],
  },
  {
    label: 'My workspace',
    items: [
      { to: '/my-work', label: 'My work', icon: 'building' },
      { to: '/watch', label: 'Following', icon: 'watch' },
      { to: '/compare', label: 'Compare', icon: 'compare' },
    ],
  },
]

function getInitialTheme(): string {
  try {
    return localStorage.getItem('countyiq_theme') || 'light'
  } catch {
    return 'light'
  }
}

function contextLabel(pathname: string): string {
  if (/^\/my-work/.test(pathname)) {
    return 'My workspace / My work'
  }
  if (/^\/$|^\/app$/.test(pathname)) {
    return 'Workspace / Overview'
  }
  if (/^\/feed/.test(pathname)) {
    return 'Explore / Activity'
  }
  if (/^\/intelligence/.test(pathname)) {
    return 'Explore / Emerging intelligence'
  }
  if (/^\/opportunities/.test(pathname)) {
    return 'Explore / Opportunities'
  }
  if (/^\/map/.test(pathname)) {
    return 'Explore / Map'
  }
  if (/^\/radar/.test(pathname)) {
    return 'Research / Properties'
  }
  if (/^\/organizations/.test(pathname)) {
    return 'Research / Organizations'
  }
  if (/^\/municipalities/.test(pathname)) {
    return 'Research / Municipalities'
  }
  if (/^\/watch/.test(pathname)) {
    return 'My workspace / Following'
  }
  if (/^\/compare/.test(pathname)) {
    return 'My workspace / Compare'
  }
  if (/^\/property/.test(pathname)) {
    return 'Research / Property report'
  }
  if (/^\/(owner|entity)/.test(pathname)) {
    return 'Research / Organization profile'
  }
  if (/^\/project/.test(pathname)) {
    return 'Explore / Project case file'
  }
  if (/^\/search/.test(pathname)) {
    return 'Search'
  }
  return 'CountyIQ'
}

function Icon({ name }: { name: IconName }) {
  const paths: Record<IconName, ReactNode> = {
    home: <path d="m3 10 9-7 9 7v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-9Z M9 21v-6h6v6" />,
    activity: <path d="M3 12h4l2.2-6 4.1 12 2.2-6H21" />,
    map: <path d="m9 18-6 3V6l6-3 6 3 6-3v15l-6 3-6-3Z M9 3v15 M15 6v15" />,
    properties: (
      <path d="M4 21V5a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v16 M2 21h20 M8 7h2 M14 7h2 M8 11h2 M14 11h2 M8 15h2 M14 15h2" />
    ),
    building: (
      <path d="M4 21V4h12v17 M2 21h20 M8 8h1 M12 8h1 M8 12h1 M12 12h1 M17 8h1 M17 12h1 M9 21v-4h3v4" />
    ),
    pin: (
      <path d="M12 21s7-5.2 7-12a7 7 0 1 0-14 0c0 6.8 7 12 7 12Z M12 11.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z" />
    ),
    watch: (
      <path d="M12 5.5a6.5 6.5 0 1 0 6.5 6.5A6.5 6.5 0 0 0 12 5.5Z M12 8v4l2.8 1.8 M9 2h6 M12 2v3 M5.1 5.1 3.7 3.7 M18.9 5.1l1.4-1.4" />
    ),
    compare: (
      <path d="M8 3H4a2 2 0 0 0-2 2v4 M16 3h4a2 2 0 0 1 2 2v4 M8 21H4a2 2 0 0 1-2-2v-4 M16 21h4a2 2 0 0 0 2-2v-4 M7 12h10 M13 8l4 4-4 4 M11 16l-4-4 4-4" />
    ),
  }

  return (
    <svg aria-hidden="true" className="workspace-shell-icon" viewBox="0 0 24 24">
      {paths[name]}
    </svg>
  )
}

function SearchForm({ compact = false }: { compact?: boolean }) {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const inputId = useId()

  const submitSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const trimmed = query.trim()
    if (trimmed.length < 2) {
      return
    }
    navigate(`/search?q=${encodeURIComponent(trimmed)}`)
    setQuery('')
  }

  return (
    <form
      className={`workspace-shell-search${compact ? ' workspace-shell-search-compact' : ''}`}
      role="search"
      onSubmit={submitSearch}
    >
      <label className="sr-only" htmlFor={inputId}>
        Search CountyIQ
      </label>
      <svg aria-hidden="true" className="workspace-shell-search-icon" viewBox="0 0 24 24">
        <circle cx="10.5" cy="10.5" r="6.5" />
        <path d="m16 16 4.5 4.5" />
      </svg>
      <input
        id={inputId}
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="Search places & records"
        title="Search an address, owner, project or public plan number"
      />
      <button type="submit">Search</button>
    </form>
  )
}

function Navigation({ onNavigate, operator }: { onNavigate?: () => void; operator?: boolean }) {
  return (
    <nav aria-label="Workspace navigation" className="workspace-shell-navigation">
      {NAVIGATION_GROUPS.map((group) => (
        <section className="workspace-shell-nav-group" key={group.label}>
          <h2>{group.label}</h2>
          <div>
            {group.items.map((item) => (
              <NavLink
                className={({ isActive }) =>
                  `workspace-shell-nav-link${isActive ? ' workspace-shell-nav-link-active' : ''}`
                }
                end={item.end}
                key={item.to}
                onClick={onNavigate}
                to={item.to}
              >
                <Icon name={item.icon} />
                <span>{item.label}</span>
              </NavLink>
            ))}
          </div>
        </section>
      ))}
      {operator && (
        <section className="workspace-shell-nav-group">
          <h2>Operations</h2>
          <NavLink className="workspace-shell-nav-link" to="/ops/health" onClick={onNavigate}>
            <Icon name="activity" />
            <span>System health</span>
          </NavLink>
        </section>
      )}
    </nav>
  )
}

function WorkspaceControls({
  account,
  onNavigate,
  onThemeChange,
  theme,
}: {
  account: ReturnType<typeof watchSyncState>['account']
  onNavigate?: () => void
  onThemeChange: () => void
  theme: string
}) {
  const county = useCountyMeta()

  return (
    <div className="workspace-shell-controls">
      <div className="workspace-shell-county">
        <span>Current county</span>
        <strong>
          {county.county_name}, {county.state}
        </strong>
      </div>
      <button className="workspace-shell-control" onClick={onThemeChange} type="button">
        <span>Theme</span>
        <span>{theme === 'dark' ? 'Dark' : 'Light'}</span>
      </button>
      {account?.authenticated ? (
        <>
          <span className="workspace-shell-account">{account.user?.email ?? 'Signed in'}</span>
          <button className="workspace-shell-control" onClick={signOut} type="button">
            Sign out
          </button>
        </>
      ) : (
        <a
          className="workspace-shell-control"
          href={account?.login_url ?? '/app'}
          onClick={onNavigate}
        >
          Sign in
        </a>
      )}
    </div>
  )
}

export default function WorkspaceShell({
  children,
  className,
  maxWidth = 900,
  wide = false,
}: WorkspaceShellProps) {
  const location = useLocation()
  const [account, setAccount] = useState(() => watchSyncState().account)
  const [theme, setTheme] = useState(getInitialTheme)
  const [drawerLocationKey, setDrawerLocationKey] = useState<string | null>(null)
  const drawerOpen = drawerLocationKey === location.key
  const menuButtonRef = useRef<HTMLButtonElement>(null)
  const drawerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const update = () => setAccount(watchSyncState().account)
    window.addEventListener('countyiq-watch-sync-changed', update)
    return () => window.removeEventListener('countyiq-watch-sync-changed', update)
  }, [])

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try {
      localStorage.setItem('countyiq_theme', theme)
    } catch {
      // Storage can be unavailable in hardened/private browser contexts.
    }
  }, [theme])

  useEffect(() => {
    if (!drawerOpen) {
      return
    }
    const firstLink = drawerRef.current?.querySelector<HTMLAnchorElement>('a')
    firstLink?.focus()
  }, [drawerOpen])

  useEffect(() => {
    if (!drawerOpen) {
      return
    }

    const bodyOverflow = document.body.style.overflow
    const rootOverflow = document.documentElement.style.overflow
    document.body.style.overflow = 'hidden'
    document.documentElement.style.overflow = 'hidden'

    return () => {
      document.body.style.overflow = bodyOverflow
      document.documentElement.style.overflow = rootOverflow
    }
  }, [drawerOpen])

  const closeDrawer = () => {
    setDrawerLocationKey(null)
    window.requestAnimationFrame(() => menuButtonRef.current?.focus())
  }

  const toggleTheme = () => {
    setTheme((currentTheme) => (currentTheme === 'dark' ? 'light' : 'dark'))
  }

  const containDrawerFocus = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') {
      closeDrawer()
      return
    }
    if (event.key !== 'Tab') {
      return
    }

    const focusable = drawerRef.current?.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), input:not([disabled])',
    )
    if (!focusable?.length) {
      return
    }

    const first = focusable[0]
    const last = focusable[focusable.length - 1]
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
  }

  const mainClassName = ['page-shell-main', 'workspace-shell-main', className]
    .filter(Boolean)
    .join(' ')

  return (
    <div className="page-shell workspace-shell">
      <aside className="workspace-shell-sidebar">
        <NavLink className="workspace-shell-brand" to="/">
          <span className="workspace-shell-brand-mark">CIQ</span>
          <span>
            <strong>CountyIQ</strong>
            <small>County intelligence</small>
          </span>
        </NavLink>
        <Navigation operator={account?.authenticated && account.operator} />
        <WorkspaceControls account={account} onThemeChange={toggleTheme} theme={theme} />
      </aside>

      <div className="workspace-shell-content">
        <header className="workspace-shell-utilitybar">
          <button
            aria-controls="workspace-shell-drawer"
            aria-expanded={drawerOpen}
            className="workspace-shell-menu-button"
            onClick={() => setDrawerLocationKey(location.key)}
            ref={menuButtonRef}
            type="button"
          >
            <span aria-hidden="true">☰</span>
            Menu
          </button>
          <p>{contextLabel(location.pathname)}</p>
          <SearchForm />
          <span className="workspace-shell-utility-account">
            {account?.authenticated ? (account.user?.email ?? 'Signed in') : 'Browser workspace'}
          </span>
        </header>
        <main className={mainClassName} style={wide ? undefined : { maxWidth }}>
          {children}
        </main>
      </div>

      {drawerOpen && (
        <div className="workspace-shell-drawer-layer" onKeyDown={containDrawerFocus}>
          <button
            aria-label="Close menu"
            className="workspace-shell-drawer-backdrop"
            onClick={closeDrawer}
            type="button"
          />
          <div
            aria-labelledby="workspace-shell-drawer-title"
            aria-modal="true"
            className="workspace-shell-drawer"
            id="workspace-shell-drawer"
            ref={drawerRef}
            role="dialog"
          >
            <div className="workspace-shell-drawer-heading">
              <strong id="workspace-shell-drawer-title">CountyIQ</strong>
              <button aria-label="Close menu" onClick={closeDrawer} type="button">
                ×
              </button>
            </div>
            <SearchForm compact />
            <Navigation
              onNavigate={closeDrawer}
              operator={account?.authenticated && account.operator}
            />
            <WorkspaceControls
              account={account}
              onNavigate={closeDrawer}
              onThemeChange={toggleTheme}
              theme={theme}
            />
          </div>
        </div>
      )}
    </div>
  )
}
