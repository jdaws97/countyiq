import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import PageShell from '../components/PageShell'
import { siteUrls } from '../lib/siteUrls'
import { PageHeader, StatusMessage, EmptyState, ButtonLink } from '../components/ui'
import ServerWatches from '../components/ServerWatches'
import SearchBar from '../components/SearchBar'
import { watchSyncState, refreshAccount } from '../lib/watchSync'
import { getRecentInvestigations, getSavedSearches } from '../lib/investigationState'
import { getWatchlist, getProjectWatchlist, getEntityWatchlist, getMunicipalityWatchlist } from '../lib/watchlist'

export default function WorkspaceHome() {
  const [state,setState]=useState(watchSyncState)
  const [,refresh]=useState(0)
  useEffect(()=>{
    const update=()=>{setState(watchSyncState());refresh(v=>v+1)}
    window.addEventListener('countyiq-watch-sync-changed',update)
    window.addEventListener('countyiq-investigation-changed',update)
    window.addEventListener('countyiq-watchlist-changed',update)
    return ()=>{
      window.removeEventListener('countyiq-watch-sync-changed',update)
      window.removeEventListener('countyiq-investigation-changed',update)
      window.removeEventListener('countyiq-watchlist-changed',update)
    }
  },[])
  if(!state.initialized)return <PageShell><StatusMessage>Opening your workspace…</StatusMessage></PageShell>
  if(!state.account && state.message)return <PageShell>
    <PageHeader title="Your CountyIQ workspace" description="Follow properties and organizations, save searches, and return to the changes that matter to you." />
    <EmptyState title="Workspace sign-in could not be checked" actions={<><button className="ciq-button ciq-button-primary" onClick={()=>{void refreshAccount()}}>Retry sign-in check</button><ButtonLink to="/search">Search properties</ButtonLink></>}>
      We could not load your account status. Retry to check sign-in availability and open your saved workspace.
    </EmptyState>
  </PageShell>
  if(!state.account?.authenticated && state.account?.configured)return <PageShell>
    <PageHeader title="Your CountyIQ workspace" description="Follow properties and organizations, save searches, and return to the changes that matter to you." />
    <EmptyState title="Sign in to continue" actions={<><a className="ciq-button ciq-button-primary" href={state.account?.login_url ?? '/app'} onClick={event=>{if(!state.account?.configured){event.preventDefault();void refreshAccount()}}}>{state.account?.configured?'Sign in':'Check sign-in availability'}</a><a className="ciq-button" href={siteUrls(window.location).marketing}>About CountyIQ</a></>}>
      {state.account?.configured?'Use your invited account to open your saved workspace.':'Account sign-in is not enabled on this local preview. You can explore the product here; saved account work requires sign-in.'}
    </EmptyState>
    <div className="section-actions workspace-home-actions"><ButtonLink to="/radar">Explore Radar</ButtonLink><ButtonLink to="/search">Search properties</ButtonLink></div>
  </PageShell>
  const saved=getSavedSearches(),recent=getRecentInvestigations()
  const watches=getWatchlist().length+getProjectWatchlist().length+getEntityWatchlist().length+getMunicipalityWatchlist().length
  const hasWork=watches>0 || saved.length>0 || recent.length>0
  return <PageShell maxWidth={1100}>
    <PageHeader eyebrow="Your workspace" title={hasWork?'Pick up your investigation':'Start with a property'} description={hasWork?'Your saved places, searches, and recently opened records.':'Find a York County property, check the recorded owner and site context, then save what you want to follow.'} meta={hasWork?<span>{watches} {watches===1?'watch':'watches'} · {saved.length} saved searches</span>:undefined} actions={watches>0?<ButtonLink to="/watch">View your watches</ButtonLink>:undefined} />
    <SearchBar />
    {state.account?.authenticated && <ServerWatches />}
    {hasWork && <div className="workspace-home-grid">
      <section className="workspace-home-card"><h2>Saved searches</h2>{saved.length?saved.map(item=><Link key={item.id} to={item.path}>{item.name} →</Link>):<p>Save a search from Activity or Radar to return to the same filters.</p>}<Link to="/radar">Explore development signals →</Link></section>
      <section className="workspace-home-card"><h2>Recent investigations</h2>{recent.length?recent.map(item=><Link key={item.path} to={item.path}>{item.label} →</Link>):<p>Properties, organizations and projects you open will appear here.</p>}<Link to="/search">Find a property or organization →</Link></section>
    </div>}
    {!hasWork && <div className="workspace-home-grid">
      <section className="workspace-home-card"><h2>Looking for a place to start?</h2><p>Use acreage, property type and development signals to build a shortlist. Each result explains why it ranked.</p><Link to="/radar">Find properties on Radar →</Link></section>
      <section className="workspace-home-card"><h2>Know the area?</h2><p>Explore a municipality’s properties, mapped context and available public records.</p><Link to="/municipalities">Choose a municipality →</Link></section>
    </div>}
    <div className="section-actions workspace-home-actions"><ButtonLink to="/feed">Recent activity</ButtonLink><ButtonLink to="/organizations">Organizations</ButtonLink><ButtonLink to="/map">Property map</ButtonLink></div>
    {!state.account?.authenticated && <p className="workspace-local-note">Local preview · Saved work stays in this browser. Account sync becomes available when sign-in is configured.</p>}
  </PageShell>
}
