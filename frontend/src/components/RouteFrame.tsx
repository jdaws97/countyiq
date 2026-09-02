import { Suspense, useEffect } from 'react'
import { Outlet, ScrollRestoration, useLocation } from 'react-router-dom'

const ROUTE_TITLES: Array<[RegExp, string]> = [
  [/^\/$/, 'CountyIQ — York County Property Intelligence'],
  [/^\/feed/, 'Intelligence Feed — CountyIQ'],
  [/^\/radar/, 'Development Radar — CountyIQ'],
  [/^\/municipalities/, 'Municipalities — CountyIQ'],
  [/^\/map/, 'Property Map — CountyIQ'],
  [/^\/watch/, 'Watched Intelligence — CountyIQ'],
  [/^\/compare/, 'Parcel Comparison — CountyIQ'],
  [/^\/property\//, 'Property Report — CountyIQ'],
  [/^\/(owner|entity)\//, 'Entity Case File — CountyIQ'],
  [/^\/project\//, 'Project Case File — CountyIQ'],
  [/^\/search/, 'Search — CountyIQ'],
]

export default function RouteFrame() {
  const location = useLocation()

  useEffect(() => {
    document.title = ROUTE_TITLES.find(([pattern]) => pattern.test(location.pathname))?.[1] ?? 'CountyIQ'
  }, [location.pathname])

  return (
    <>
      <ScrollRestoration />
      <Suspense fallback={<div className="route-loading">Loading CountyIQ…</div>}>
        <Outlet />
      </Suspense>
    </>
  )
}

export function RouteError() {
  return (
    <main className="route-error">
      <div className="page-eyebrow">CountyIQ</div>
      <h1>That page could not be opened.</h1>
      <p>The route may have changed, or the requested record may no longer be available.</p>
      <a className="ciq-button ciq-button-primary" href="/">Return home</a>
    </main>
  )
}
