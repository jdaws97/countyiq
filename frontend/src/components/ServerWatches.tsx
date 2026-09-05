import { useEffect, useState } from 'react'
import { Button, StatusMessage } from './ui'
import IntelligenceEventCard from './IntelligenceEventCard'
import { acknowledgeWatchChanges, olderWatchChanges, latestWatchChanges, clearAccountWorkspace, enableBrowserAlerts, loadServerWatches, syncWatches, watchSyncState } from '../lib/watchSync'

export default function ServerWatches() {
  const [state,setState]=useState(watchSyncState)
  const [error,setError]=useState('')
  const [pending,setPending]=useState(false)
  useEffect(()=>{
    const update=()=>setState(watchSyncState())
    window.addEventListener('countyiq-watch-sync-changed',update)
    return ()=>window.removeEventListener('countyiq-watch-sync-changed',update)
  },[])
  async function act(action:()=>Promise<unknown>) {
    if(pending)return
    setPending(true);setError('')
    try{await action()}catch(reason){setError(reason instanceof Error ? reason.message : 'Unable to complete this action.')}
    finally{setPending(false)}
  }
  if(!state.connected)return <div className="workspace-boundary"><strong>Browser workspace</strong><span>Sign in to save watches and investigations across devices. <a href={state.account?.login_url ?? '/app'}>Open your workspace →</a></span></div>
  return <section aria-label="Account workspace" className="server-watchspace">
    <h2>Changes on your watches</h2>
    <details className="workspace-settings"><summary>Workspace settings</summary>
    <p>Watches, saved searches, comparisons and recent investigations are saved to your account.</p>
    <div className="section-actions">
      <Button disabled={pending} onClick={()=>void act(syncWatches)}>Sync now</Button>
      <Button disabled={pending} tone="quiet" onClick={()=>{if(window.confirm('Replace local edits with your saved account workspace? Export first to keep a copy.'))void act(loadServerWatches)}}>Load saved copy</Button>
      <Button disabled={pending} tone="quiet" onClick={()=>void act(enableBrowserAlerts)}>Enable browser alerts</Button>
      <Button disabled={pending} tone="quiet" onClick={()=>{if(window.confirm('Clear all saved watches, searches, comparisons and inbox items from your account?'))void act(clearAccountWorkspace)}}>Clear saved workspace</Button>
    </div>
    <p>Browser alerts work while CountyIQ is open. Your unread inbox is retained when it is closed.</p>
    </details>
    {(error||state.message)&&<StatusMessage tone={error||state.conflict?'error':'neutral'}>{error||state.message}</StatusMessage>}
    {state.inbox&&<div aria-live="polite">
      <p>{state.inbox.summary}</p>
      {!state.inbox.notifications.length&&<p>{state.inbox.has_more ? 'No currently visible changes on this page. Continue to older unread changes.' : state.olderInbox ? 'No more visible unread changes on this page.' : 'No visible unread changes. Follow records to see their next recorded changes here.'}</p>}
      {state.olderInbox&&<Button disabled={pending} tone="quiet" onClick={()=>void act(latestWatchChanges)}>Newest unread changes</Button>}
      {state.inbox.has_more&&<Button disabled={pending} tone="quiet" onClick={()=>void act(olderWatchChanges)}>Older unread changes</Button>}
      {state.inbox.notifications.length>0&&<Button disabled={pending} tone="quiet" onClick={()=>void act(acknowledgeWatchChanges)}>Mark these changes reviewed</Button>}
      <div className="feed-list">{state.inbox.notifications.map(notice=><IntelligenceEventCard key={notice.id} event={notice.event} isNew />)}</div>
    </div>}
  </section>
}
