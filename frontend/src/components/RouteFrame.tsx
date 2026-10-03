import { Suspense, useEffect, useState } from 'react'
import { startWatchSync, watchSyncState, syncWatches } from '../lib/watchSync'
import { recordInvestigation } from '../lib/investigationState'
import { Outlet, ScrollRestoration, useLocation } from 'react-router-dom'
import SourceViewerProvider from './SourceViewer'

const ROUTE_TITLES: Array<[RegExp, string]> = [
  [/^\/$/, 'Your Workspace — CountyIQ'],
  [/^\/app$/, 'Your Workspace — CountyIQ'],
  [/^\/organizations/, 'Organizations — CountyIQ'],
  [/^\/feed/, 'Activity workspace — CountyIQ'],
  [/^\/intelligence/, 'Emerging Intelligence — CountyIQ'],
  [/^\/opportunities/, 'Opportunities — CountyIQ'],
  [/^\/my-work/, 'My Work — CountyIQ'],
  [/^\/radar/, 'Property screening — CountyIQ'],
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
  const [session, setSession] = useState(watchSyncState)
  useEffect(() => {
    const update = () => setSession(watchSyncState())
    window.addEventListener('countyiq-watch-sync-changed', update)
    return () => window.removeEventListener('countyiq-watch-sync-changed', update)
  }, [])
  useEffect(startWatchSync, [])

  useEffect(() => {
    document.title =
      ROUTE_TITLES.find(([pattern]) => pattern.test(location.pathname))?.[1] ?? 'CountyIQ'
  }, [location.pathname])

  useEffect(() => {
    if (!/^\/(property|project|entity|owner|municipalities)\//.test(location.pathname)) {
      return
    }
    const timer = window.setTimeout(() => {
      const label = document.querySelector('main h1')?.textContent?.trim()
      if (label) {
        recordInvestigation(location.pathname, label)
      }
    }, 1000)
    return () => window.clearTimeout(timer)
  }, [location.pathname])

  return (
    <>
      <ScrollRestoration />
      {session.connected && !session.hydrated ? (
        <main className="route-loading">
          <p>{session.message || 'Loading your saved workspace…'}</p>
          <button onClick={() => void syncWatches()}>Retry</button>
        </main>
      ) : (
        <Suspense
          key={session.account?.user?.id ?? 'guest'}
          fallback={<div className="route-loading">Loading CountyIQ…</div>}
        >
          <SourceViewerProvider>
            <Outlet />
          </SourceViewerProvider>
        </Suspense>
      )}
    </>
  )
}

export function RouteError() {
  return (
    <main className="route-error">
      <div className="page-eyebrow">CountyIQ</div>
      <h1>That page could not be opened.</h1>
      <p>The route may have changed, or the requested record may no longer be available.</p>
      <a className="ciq-button ciq-button-primary" href="/">
        Return home
      </a>
    </main>
  )
}
