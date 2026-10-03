import { useEffect, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import PageShell from '../components/PageShell'
import SiteSearch from '../components/site-inquiries/SiteSearch'
import InquiryEditor from '../components/site-inquiries/InquiryEditor'
import InquiryList from '../components/site-inquiries/InquiryList'
import { ButtonLink, EmptyState, PageHeader, StatusMessage } from '../components/ui'
import { getSiteInquiries } from '../lib/siteInquiries'
import { watchSyncState } from '../lib/watchSync'
import type { SiteInquiry } from '../types/siteIntake'
import './SiteInquiries.css'

type InquiryWorkspace = {
  items: SiteInquiry[]
  error: string
  accountKey: string
  retained: SiteInquiry | null
}

function readInquiries(): InquiryWorkspace {
  const accountKey = watchSyncState().account?.user?.id ?? 'guest'
  try {
    return { items: getSiteInquiries(), error: '', accountKey, retained: null }
  } catch (error) {
    return {
      items: [],
      error: error instanceof Error ? error.message : 'Saved inquiries are unavailable.',
      accountKey,
      retained: null,
    }
  }
}

export default function SiteInquiries({ creating = false }: { creating?: boolean }) {
  const { id } = useParams()
  const [params] = useSearchParams()
  const [saved, setSaved] = useState(readInquiries)
  const [sync, setSync] = useState(watchSyncState)
  useEffect(() => {
    const update = () => {
      setSaved((previous) => {
        const next = readInquiries()
        if (next.accountKey !== previous.accountKey) {
          return next
        }
        // Preserve the open editor if another tab removes its saved entry.
        // The optimistic save check still prevents recreating that entry.
        const retained =
          previous.items.find((item) => item.id === id) ??
          (previous.retained?.id === id ? previous.retained : null)
        return { ...next, retained }
      })
      setSync(watchSyncState())
    }
    window.addEventListener('storage', update)
    window.addEventListener('countyiq-investigation-changed', update)
    window.addEventListener('countyiq-watch-sync-changed', update)
    return () => {
      window.removeEventListener('storage', update)
      window.removeEventListener('countyiq-investigation-changed', update)
      window.removeEventListener('countyiq-watch-sync-changed', update)
    }
  }, [id])
  const current = saved.items.find((item) => item.id === id)
  const selected =
    current ?? (saved.retained && saved.retained.id === id ? saved.retained : undefined)
  const pidn = selected?.pidn ?? params.get('pidn') ?? ''
  const validPidn = /^[A-Za-z0-9_-]{1,100}$/.test(pidn)
  const accountKey = sync.account?.user?.id ?? 'guest'
  const showEditor = validPidn && (!saved.error || selected) && (!id || selected)
  return (
    <PageShell maxWidth={1220} className="site-inquiries">
      {!showEditor && (
        <PageHeader
          eyebrow="York County · Site research"
          title={creating ? 'Find a property' : 'Site inquiries'}
          description={
            creating
              ? 'Choose the candidate site before adding the client’s brief.'
              : 'Keep the brief, evidence and open questions together for each candidate site.'
          }
          actions={
            creating ? (
              <ButtonLink to="/sites">All inquiries</ButtonLink>
            ) : (
              <ButtonLink tone="primary" to="/sites/new">
                New inquiry
              </ButtonLink>
            )
          }
        />
      )}
      {saved.error && <StatusMessage tone="error">{saved.error}</StatusMessage>}
      {selected && !current && !saved.error && (
        <StatusMessage tone="error">
          This inquiry was removed in another tab or device. Your open draft is still here. Copy
          your notes before leaving; saving cannot replace the removed inquiry.
        </StatusMessage>
      )}
      {id && !selected && (
        <EmptyState
          title="Inquiry unavailable"
          actions={<ButtonLink to="/sites">All inquiries</ButtonLink>}
        >
          This inquiry is not in the current workspace. Check the signed-in account or import your
          exported workspace.
        </EmptyState>
      )}
      {pidn && !validPidn && (
        <StatusMessage tone="error">
          That parcel ID is not valid. Find a property to continue.
        </StatusMessage>
      )}
      {showEditor ? (
        <InquiryEditor key={`${accountKey}:${id ?? pidn}`} pidn={pidn} initial={selected} />
      ) : (
        !id &&
        (creating || pidn ? <SiteSearch /> : !saved.error && <InquiryList items={saved.items} />)
      )}
      <div className="site-workspace-note">
        <span>
          {sync.connected
            ? 'Private account workspace'
            : 'Saved in this browser. Sign in to sync across devices.'}
        </span>
        <Link to="/watch">Workspace settings & backup</Link>
      </div>
    </PageShell>
  )
}
