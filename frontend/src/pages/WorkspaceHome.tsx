import { useEffect, useState } from 'react'
import PageShell from '../components/PageShell'
import { siteUrls } from '../lib/siteUrls'
import { PageHeader, StatusMessage, EmptyState, ButtonLink } from '../components/ui'
import ServerWatches from '../components/ServerWatches'
import WorkspaceOverview from '../components/WorkspaceOverview'
import { watchSyncState, refreshAccount } from '../lib/watchSync'
import {
  getWatchlist,
  getProjectWatchlist,
  getEntityWatchlist,
  getMunicipalityWatchlist,
} from '../lib/watchlist'

export default function WorkspaceHome() {
  const [state, setState] = useState(watchSyncState)
  const [, refresh] = useState(0)
  useEffect(() => {
    const update = () => {
      setState(watchSyncState())
      refresh((v) => v + 1)
    }
    window.addEventListener('countyiq-watch-sync-changed', update)
    window.addEventListener('countyiq-investigation-changed', update)
    window.addEventListener('countyiq-watchlist-changed', update)
    return () => {
      window.removeEventListener('countyiq-watch-sync-changed', update)
      window.removeEventListener('countyiq-investigation-changed', update)
      window.removeEventListener('countyiq-watchlist-changed', update)
    }
  }, [])
  if (!state.initialized) {
    return (
      <PageShell>
        <StatusMessage>Opening your workspace…</StatusMessage>
      </PageShell>
    )
  }
  if (!state.account && state.message) {
    return (
      <PageShell>
        <PageHeader
          title="Your CountyIQ workspace"
          description="Follow properties and organizations, save searches, and return to the changes that matter to you."
        />
        <EmptyState
          title="Workspace sign-in could not be checked"
          actions={
            <>
              <button
                className="ciq-button ciq-button-primary"
                onClick={() => {
                  void refreshAccount()
                }}
              >
                Retry sign-in check
              </button>
              <ButtonLink to="/search">Search properties</ButtonLink>
            </>
          }
        >
          We could not load your account status. Retry to check sign-in availability and open your
          saved workspace.
        </EmptyState>
      </PageShell>
    )
  }
  if (!state.account?.authenticated && state.account?.configured) {
    return (
      <PageShell>
        <PageHeader
          title="Your CountyIQ workspace"
          description="Follow properties and organizations, save searches, and return to the changes that matter to you."
        />
        <EmptyState
          title="Sign in to continue"
          actions={
            <>
              <a
                className="ciq-button ciq-button-primary"
                href={state.account?.login_url ?? '/app'}
                onClick={(event) => {
                  if (!state.account?.configured) {
                    event.preventDefault()
                    void refreshAccount()
                  }
                }}
              >
                {state.account?.configured ? 'Sign in' : 'Check sign-in availability'}
              </a>
              <a className="ciq-button" href={siteUrls(window.location).marketing}>
                About CountyIQ
              </a>
            </>
          }
        >
          {state.account?.configured
            ? 'Use your invited account to open your saved workspace.'
            : 'Account sign-in is not enabled on this local preview. You can explore the product here; saved account work requires sign-in.'}
        </EmptyState>
        <div className="section-actions workspace-home-actions">
          <ButtonLink to="/radar">Explore Radar</ButtonLink>
          <ButtonLink to="/search">Search properties</ButtonLink>
        </div>
      </PageShell>
    )
  }
  const watches =
    getWatchlist().length +
    getProjectWatchlist().length +
    getEntityWatchlist().length +
    getMunicipalityWatchlist().length
  return (
    <PageShell wide className="overview-page">
      <WorkspaceOverview watches={watches} />
      {state.account?.authenticated && <ServerWatches />}
      {!state.account?.authenticated && (
        <p className="workspace-local-note">
          Your saved work stays in this browser during the local preview.
        </p>
      )}
    </PageShell>
  )
}
