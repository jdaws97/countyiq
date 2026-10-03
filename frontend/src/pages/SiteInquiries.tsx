import { useEffect, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import PageShell from '../components/PageShell'
import SiteSearch from '../components/site-inquiries/SiteSearch'
import InquiryEditor from '../components/site-inquiries/InquiryEditor'
import { ButtonLink, EmptyState, PageHeader, StatusMessage } from '../components/ui'
import { getSiteInquiries } from '../lib/siteInquiries'
import { watchSyncState } from '../lib/watchSync'
import { formatShortDate } from '../lib/format'
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

export default function SiteInquiries() {
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
  return (
    <PageShell maxWidth={1220} className="site-inquiries">
      <PageHeader
        eyebrow="York County · Site research"
        title="Site inquiries"
        description="Turn a candidate property into a cited research handoff for your first municipal conversation."
        actions={<ButtonLink to="/sites">New inquiry</ButtonLink>}
      />
      <div className="site-workspace-note">
        {sync.connected
          ? 'Private account workspace'
          : 'Saved in this browser. Sign in to sync across devices.'}{' '}
        <Link to="/watch">Workspace settings & backup</Link>
      </div>
      {saved.error && <StatusMessage tone="error">{saved.error}</StatusMessage>}
      {selected && !current && !saved.error && (
        <StatusMessage tone="error">
          This inquiry was removed in another tab or device. Your open draft is still here. Copy
          your notes before leaving; saving cannot replace the removed inquiry.
        </StatusMessage>
      )}
      {id && !selected && (
        <EmptyState title="Inquiry unavailable">
          This inquiry is not in the current workspace. Check the signed-in account or import your
          exported workspace.
        </EmptyState>
      )}
      {validPidn && (!saved.error || selected) && (!id || selected) ? (
        <InquiryEditor key={`${accountKey}:${id ?? pidn}`} pidn={pidn} initial={selected} />
      ) : (
        !id && (
          <>
            <SiteSearch />
            <section aria-labelledby="saved-sites-heading" className="site-section">
              <div className="site-section-title">
                <h2 id="saved-sites-heading">Your inquiries</h2>
                <span className="site-count-label">{saved.items.length} saved</span>
              </div>
              {saved.items.length ? (
                <div className="site-inquiry-list">
                  {saved.items.map((item) => (
                    <Link className="site-inquiry-card" to={`/sites/${item.id}`} key={item.id}>
                      <div className="site-card-heading">
                        <strong>{item.label}</strong>
                        <span className="site-stage">{item.status.replaceAll('_', ' ')}</span>
                      </div>
                      <span>{item.proposed_use || 'Proposed use not supplied'}</span>
                      <small>
                        PIDN {item.pidn} · Saved {formatShortDate(item.updated_at)}
                      </small>
                      <div className="site-card-footer">
                        <span>
                          {5 -
                            (item.question_reviews ?? []).filter(
                              (question) => question.status !== 'open',
                            ).length}{' '}
                          review questions open
                        </span>
                        <span>Continue inquiry →</span>
                      </div>
                    </Link>
                  ))}
                </div>
              ) : (
                <EmptyState title="Start with a property">
                  Find a client’s candidate site, confirm its identity, then add the proposed use
                  and questions.
                </EmptyState>
              )}
            </section>
          </>
        )
      )}
    </PageShell>
  )
}
