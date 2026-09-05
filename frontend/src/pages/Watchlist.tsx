import { useEffect, useRef, useState, type ChangeEvent } from 'react'
import { Link } from 'react-router-dom'

import Badge from '../components/Badge'
import ServerWatches from '../components/ServerWatches'
import { watchSyncState } from '../lib/watchSync'
import IntelligenceEventCard from '../components/IntelligenceEventCard'
import PageShell from '../components/PageShell'
import Section from '../components/Section'
import { Button, ButtonLink, EmptyState, PageHeader, StatusMessage } from '../components/ui'
import { formatCurrencyCompact } from '../lib/format'
import {
  downloadText,
  getComparison,
  getEventTriage,
  getLastWatchVisit,
  getSavedSearches,
  removeSavedSearch,
  parseWorkspace,
  replaceWorkspace,
  setLastWatchVisit,
  toCsv,
  type PortableWorkspace,
} from '../lib/investigationState'
import { getPropertyClassLabel } from '../lib/propertyLabels'
import { useFetchJson } from '../lib/useFetchJson'
import {
  getEntityWatchlist,
  getMunicipalityWatchlist,
  getProjectWatchlist,
  getWatchlist,
  toggleEntityWatch,
  toggleMunicipalityWatch,
  toggleProjectWatch,
  toggleWatch,
  WATCHLIST_CAP,
} from '../lib/watchlist'
import type { IntelligenceEvent, IntelligenceFeedResponse, WatchlistSummaryResponse } from '../types/api'

export default function Watchlist() {
  const [watched, setWatched] = useState<string[]>(() => getWatchlist())
  const [watchedProjects, setWatchedProjects] = useState(() => getProjectWatchlist())
  const [watchedEntities, setWatchedEntities] = useState(() => getEntityWatchlist())
  const [watchedMunicipalities, setWatchedMunicipalities] = useState(() => getMunicipalityWatchlist())
  const [savedSearches, setSavedSearches] = useState(() => getSavedSearches())
  const [lastVisit] = useState(() => getLastWatchVisit())
  const [serverConnected, setServerConnected] = useState(() => watchSyncState().connected)
  const previousVisit = serverConnected ? null : lastVisit
  const [workspaceMessage, setWorkspaceMessage] = useState<string | null>(null)
  const importRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const refreshSync = () => setServerConnected(watchSyncState().connected)
    window.addEventListener('countyiq-watch-sync-changed', refreshSync)
    const refresh = () => {
      setWatched(getWatchlist())
      setWatchedProjects(getProjectWatchlist())
      setWatchedEntities(getEntityWatchlist())
      setWatchedMunicipalities(getMunicipalityWatchlist())
      setSavedSearches(getSavedSearches())
    }
    window.addEventListener('countyiq-watchlist-changed', refresh)
    window.addEventListener('countyiq-investigation-changed', refresh)
    return () => {
      window.removeEventListener('countyiq-watch-sync-changed', refreshSync)
      setLastWatchVisit()
      window.removeEventListener('countyiq-watchlist-changed', refresh)
      window.removeEventListener('countyiq-investigation-changed', refresh)
    }
  }, [])

  const url = watched.length > 0 ? `/api/parcels/summary?pidns=${watched.map(encodeURIComponent).join(',')}` : null
  const { data, error, loading } = useFetchJson<WatchlistSummaryResponse>(url)
  const parcelEvents = useFetchJson<IntelligenceFeedResponse>(watched.length > 0 ? `/api/feed?since_days=3650&limit=30&pidns=${encodeURIComponent(watched.join(','))}` : null)
  const projectEvents = useFetchJson<IntelligenceFeedResponse>(watchedProjects.length > 0 ? `/api/feed?since_days=3650&limit=30&project_keys=${encodeURIComponent(watchedProjects.map((project) => project.key).join(','))}` : null)
  const entityEvents = useFetchJson<IntelligenceFeedResponse>(watchedEntities.length > 0 ? `/api/feed?since_days=3650&limit=30&sort=latest&entity_ids=${watchedEntities.map((entity) => entity.id).join(',')}` : null)
  // A municipality generates far more events than one subject, so its watch
  // window is the recent quarter rather than all history.
  const municipalityEvents = useFetchJson<IntelligenceFeedResponse>(watchedMunicipalities.length > 0 ? `/api/feed?since_days=90&limit=30&sort=latest&municipality=${encodeURIComponent(watchedMunicipalities.map((municipality) => municipality.name).join(','))}` : null)
  // "Something happened next door": events on other parcels within 400 m of
  // a watched parcel, over the last quarter.
  const nearbyEvents = useFetchJson<IntelligenceFeedResponse>(watched.length > 0 ? `/api/feed?since_days=90&limit=30&sort=latest&near_radius_m=400&near_pidns=${encodeURIComponent(watched.join(','))}` : null)
  const parcels = data?.parcels ?? []
  const missing = data?.missing ?? []
  const changedCount = parcels.filter((parcel) => parcel.changed_recently).length
  const allEvents = uniqueEvents([...(parcelEvents.data?.events ?? []), ...(projectEvents.data?.events ?? []), ...(entityEvents.data?.events ?? []), ...(municipalityEvents.data?.events ?? []), ...(nearbyEvents.data?.events ?? [])])
  const newEvents = previousVisit ? allEvents.filter((event) => new Date(event.detected_at) > new Date(previousVisit)) : []

  const exportWorkspace = () => {
    const workspace: PortableWorkspace = {
      version: 1,
      exportedAt: new Date().toISOString(),
      parcels: getWatchlist(),
      projects: getProjectWatchlist(),
      entities: getEntityWatchlist(),
      municipalities: getMunicipalityWatchlist(),
      savedSearches: getSavedSearches(),
      comparison: getComparison(),
      triage: getEventTriage(),
    }
    downloadText(`countyiq-workspace-${new Date().toISOString().slice(0, 10)}.json`, JSON.stringify(workspace, null, 2), 'application/json')
    setWorkspaceMessage('Workspace exported. Import the file in another browser to continue there.')
  }

  const importWorkspace = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    if (file.size > 2_000_000) {
      setWorkspaceMessage('Workspace import failed: file exceeds 2 MB.')
      event.target.value = ''
      return
    }
    file.text().then((text) => {
      const workspace = parseWorkspace(text)
      if (!window.confirm('Importing this workspace will replace the current browser workspace. Continue?')) {
        setWorkspaceMessage('Workspace import canceled; current browser data was kept.')
        return
      }
      replaceWorkspace(workspace)
      setWorkspaceMessage('Workspace imported into this browser.')
    }).catch((reason: unknown) => setWorkspaceMessage(reason instanceof Error ? reason.message : 'Workspace import failed'))
    event.target.value = ''
  }

  const exportParcels = () => {
    const rows: Array<Array<string | number | boolean | null>> = [['PIDN', 'Address', 'Owner', 'Municipality', 'Assessed total', 'Class', 'Acres', 'Changed recently', 'Tax delinquency signal']]
    for (const parcel of parcels) rows.push([parcel.pidn, parcel.propadr, parcel.owner_full, parcel.municipality, parcel.aprtotal, getPropertyClassLabel(parcel.class), parcel.acres, parcel.changed_recently, parcel.has_tax_delinquency])
    downloadText(`countyiq-watched-parcels-${new Date().toISOString().slice(0, 10)}.csv`, toCsv(rows), 'text/csv')
  }

  const nothingWatched = watched.length === 0 && watchedProjects.length === 0 && watchedEntities.length === 0 && watchedMunicipalities.length === 0

  return (
    <PageShell maxWidth={1040}>
      <PageHeader
        eyebrow="Retained intelligence"
        title="Watched Intelligence"
        description="Return to the parcels, projects, entities, municipalities, saved searches, and new evidence that matter to your current investigation."
        meta={<><Badge color="var(--accent-blue)">{watched.length}/{WATCHLIST_CAP} parcels</Badge><Badge color="var(--accent-cyan)">{watchedProjects.length} projects</Badge><Badge color="var(--accent-green)">{watchedEntities.length} entities</Badge><Badge color="var(--accent-purple)">{watchedMunicipalities.length} municipalities</Badge>{changedCount > 0 && <Badge color="var(--accent-gold)">{changedCount} parcels changed</Badge>}</>}
        actions={<><Button tone="quiet" onClick={exportWorkspace}>Export workspace</Button><Button tone="quiet" onClick={() => importRef.current?.click()}>Import workspace</Button><input ref={importRef} className="sr-only" type="file" accept="application/json,.json" onChange={importWorkspace} /></>}
      />

      <ServerWatches />
      {workspaceMessage && <StatusMessage tone={workspaceMessage.includes('failed') || workspaceMessage.startsWith('Not') ? 'error' : 'success'}>{workspaceMessage}</StatusMessage>}

      {newEvents.length > 0 && (
        <div className="watch-alert"><strong>{newEvents.length} new watched event{newEvents.length === 1 ? '' : 's'} since your last visit.</strong><span>Review them in the watched evidence sections below.</span></div>
      )}

      {nothingWatched && savedSearches.length === 0 && (
        <EmptyState title="Start an investigation" actions={<><ButtonLink to="/feed" tone="primary">Browse intelligence feed</ButtonLink><ButtonLink to="/radar">Explore Radar</ButtonLink><ButtonLink to="/map">Open map</ButtonLink></>}>
          Watch a parcel, project, entity, or municipality from any case file. CountyIQ will collect its source-backed events here and flag what changed since your last visit.
        </EmptyState>
      )}

      {savedSearches.length > 0 && (
        <Section title={`Saved searches (${savedSearches.length})`}>
          <div className="saved-search-list">{savedSearches.map((search) => <div className="saved-search" key={search.id}><Link to={search.path}>{search.name}</Link><span>{search.kind} · saved {new Date(search.createdAt).toLocaleDateString()}</span><Button tone="quiet" onClick={() => removeSavedSearch(search.id)}>Remove</Button></div>)}</div>
        </Section>
      )}

      {watchedEntities.length > 0 && (
        <WatchSection title={`Watched entities (${watchedEntities.length})`} events={entityEvents} previousVisit={previousVisit}>
          {watchedEntities.map((entity) => <WatchChip key={entity.id} to={`/entity/${entity.id}`} label={entity.name} onRemove={() => toggleEntityWatch(entity)} />)}
        </WatchSection>
      )}

      {watchedMunicipalities.length > 0 && (
        <WatchSection title={`Watched municipalities (${watchedMunicipalities.length}) · last 90 days`} events={municipalityEvents} previousVisit={previousVisit}>
          {watchedMunicipalities.map((municipality) => <WatchChip key={municipality.name} to={`/municipalities/${encodeURIComponent(municipality.name)}`} label={municipality.name} onRemove={() => toggleMunicipalityWatch(municipality)} />)}
        </WatchSection>
      )}

      {watchedProjects.length > 0 && (
        <WatchSection title={`Watched projects (${watchedProjects.length})`} events={projectEvents} previousVisit={previousVisit}>
          {watchedProjects.map((project) => <WatchChip key={project.key} to={`/project/${encodeURIComponent(project.key)}`} label={project.name} onRemove={() => toggleProjectWatch(project)} />)}
        </WatchSection>
      )}

      {loading && <StatusMessage>Loading watched parcels…</StatusMessage>}
      {!loading && error && <StatusMessage tone="error">{error}</StatusMessage>}

      {!loading && !error && parcels.length > 0 && (
        <Section title={`Watched parcels (${parcels.length})`}>
          <div className="section-actions" data-print-hidden><Button tone="quiet" onClick={exportParcels}>Export parcel CSV</Button><ButtonLink to="/compare" tone="quiet">Open comparison</ButtonLink></div>
          <div className="watch-parcel-list">
            {parcels.map((parcel) => (
              <div className={`watch-parcel-row${parcel.changed_recently ? ' watch-parcel-changed' : ''}`} key={parcel.pidn}>
                <div><Link to={`/property/${parcel.pidn}`}>{parcel.propadr ?? parcel.pidn}</Link><span>{parcel.owner_full ?? 'Owner not displayed'} · {parcel.municipality ?? 'Municipality unavailable'}</span></div>
                <div><strong>{parcel.aprtotal !== null ? formatCurrencyCompact(parcel.aprtotal, { allowBillions: true }) : '—'}</strong><span>{getPropertyClassLabel(parcel.class) || parcel.class || 'Class unavailable'}</span></div>
                <div>{parcel.changed_recently ? <Badge color="var(--accent-gold)">Changed</Badge> : <span>No recent change</span>}</div>
                <Button tone="quiet" onClick={() => toggleWatch(parcel.pidn)}>Unwatch</Button>
              </div>
            ))}
          </div>
        </Section>
      )}

      {missing.length > 0 && <Section title={`No longer found (${missing.length})`}><div className="missing-watch-list">{missing.map((pidn) => <span key={pidn}>{pidn}<button onClick={() => toggleWatch(pidn)}>remove</button></span>)}</div></Section>}

      {watched.length > 0 && <WatchSection title="Recent intelligence for watched parcels" events={parcelEvents} previousVisit={previousVisit} />}

      {watched.length > 0 && <WatchSection title="Activity next door · within 400 m of watched parcels, last 90 days" events={nearbyEvents} previousVisit={previousVisit} />}
    </PageShell>
  )
}

function WatchSection({ title, events, previousVisit, children }: { title: string; events: ReturnType<typeof useFetchJson<IntelligenceFeedResponse>>; previousVisit: string | null; children?: React.ReactNode }) {
  return <Section title={title}>{children && <div className="watch-chip-list">{children}</div>}{events.loading && <StatusMessage>Loading watched intelligence…</StatusMessage>}{events.error && <StatusMessage tone="error">{events.error}</StatusMessage>}{!events.loading && !events.error && (events.data?.events.length ?? 0) === 0 && <div className="watch-empty-inline">No source-backed events are linked yet.</div>}{(events.data?.events.length ?? 0) > 0 && <div className="feed-list">{events.data!.events.map((event) => <IntelligenceEventCard key={event.event_key} event={event} isNew={Boolean(previousVisit && new Date(event.detected_at) > new Date(previousVisit))} />)}</div>}</Section>
}

function WatchChip({ to, label, onRemove }: { to: string; label: string; onRemove: () => void }) {
  return <span className="watch-chip"><Link to={to}>{label} →</Link><button onClick={onRemove} aria-label={`Remove ${label}`}>×</button></span>
}

function uniqueEvents(events: IntelligenceEvent[]): IntelligenceEvent[] {
  return Array.from(new Map(events.map((event) => [event.event_key, event])).values())
}
