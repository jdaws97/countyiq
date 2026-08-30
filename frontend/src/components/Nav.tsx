import { NavLink } from 'react-router-dom'

import { useCountyMeta } from '../lib/useCountyMeta'

const NAV_ITEMS = [
  { to: '/feed', label: 'Feed' },
  { to: '/radar', label: 'Radar' },
  { to: '/map', label: 'Map' },
  { to: '/watch', label: 'Watch' },
]

export default function Nav() {
  const county = useCountyMeta()

  return (
    <nav className="primary-nav">
      <NavLink to="/" className="brand-link">
        <div className="brand-mark">CIQ</div>
        <div>
          <div className="brand-name">CountyIQ</div>
          <div className="brand-county">{county.county_name} · {county.state}</div>
        </div>
      </NavLink>

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
      </div>
    </nav>
  )
}
