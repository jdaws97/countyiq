import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import PageShell from '../components/PageShell'
import ParcelContextMap from '../components/ParcelContextMap'
import MunicipalEvidence from '../components/MunicipalEvidence'
import { Button, ButtonLink, EmptyState, PageHeader, StatusMessage } from '../components/ui'
import { useFetchJson } from '../lib/useFetchJson'
import { useSourceViewer } from '../lib/useSourceViewer'
import { getSiteInquiries, saveSiteInquiry, removeSiteInquiry } from '../lib/siteInquiries'
import { watchSyncState } from '../lib/watchSync'
import { downloadText } from '../lib/investigationState'
import { floodScreeningSummary } from '../lib/floodScreening'
import { sitePacketText } from '../lib/sitePacket'
import { formatShortDate } from '../lib/format'
import type { SearchResponse } from '../types/api'
import type { SiteInquiry, SiteIntakePacket } from '../types/siteIntake'
import './SiteInquiries.css'

function readInquiries() {
  try {
    return { items: getSiteInquiries(), error: '' }
  } catch (error) {
    return {
      items: [],
      error: error instanceof Error ? error.message : 'Saved inquiries are unavailable.',
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
      setSaved(readInquiries())
      setSync(watchSyncState())
    }
    window.addEventListener('countyiq-investigation-changed', update)
    window.addEventListener('countyiq-watch-sync-changed', update)
    return () => {
      window.removeEventListener('countyiq-investigation-changed', update)
      window.removeEventListener('countyiq-watch-sync-changed', update)
    }
  }, [])
  const selected = saved.items.find((item) => item.id === id)
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
          ? sync.message || 'Private account workspace'
          : 'Saved in this browser. Sign in to sync across devices.'}{' '}
        <Link to="/watch">Workspace export, import and sync settings</Link>
      </div>
      {saved.error && <StatusMessage tone="error">{saved.error}</StatusMessage>}
      {id && !selected && (
        <EmptyState title="Inquiry unavailable">
          This inquiry is not in the current workspace. Check the signed-in account or import your
          exported workspace.
        </EmptyState>
      )}
      {validPidn && !saved.error && (!id || selected) ? (
        <InquiryEditor key={`${accountKey}:${id ?? pidn}`} pidn={pidn} initial={selected} />
      ) : (
        !id && (
          <>
            <SiteSearch />
            <section aria-labelledby="saved-sites-heading" className="site-section">
              <h2 id="saved-sites-heading">Your inquiries</h2>
              {saved.items.length ? (
                <div className="site-inquiry-list">
                  {saved.items.map((item) => (
                    <Link className="site-inquiry-card" to={`/sites/${item.id}`} key={item.id}>
                      <strong>{item.label}</strong>
                      <span>{item.proposed_use || 'Proposed use not supplied'}</span>
                      <small>
                        {item.status.replaceAll('_', ' ')} · PIDN {item.pidn} · Saved{' '}
                        {formatShortDate(item.updated_at)}
                      </small>
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

function SiteSearch() {
  const [query, setQuery] = useState('')
  const [submitted, setSubmitted] = useState('')
  const result = useFetchJson<SearchResponse>(
    submitted ? `/api/search?q=${encodeURIComponent(submitted)}&limit=15` : null,
  )
  const matches = result.data?.results.filter((item) => item.pidn) ?? []
  const redirectPidn = result.data?.redirect_path?.match(/^\/property\/([A-Za-z0-9_-]+)$/)?.[1]
  function submit(event: FormEvent) {
    event.preventDefault()
    const next = query.trim()
    if (next.length < 2) {
      return
    }
    setSubmitted(next)
    if (next === submitted) {
      result.reload()
    }
  }
  return (
    <section className="site-section" aria-labelledby="identify-site-heading">
      <h2 id="identify-site-heading">Identify the site</h2>
      <form className="site-search" onSubmit={submit} role="search">
        <label htmlFor="site-query">Address, owner or parcel ID</label>
        <div>
          <input
            id="site-query"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            maxLength={200}
            minLength={2}
            required
            placeholder="Enter the client’s candidate property"
          />
          <Button type="submit" tone="primary">
            Find property
          </Button>
        </div>
      </form>
      <p>
        Choose the exact property. Similar addresses and owner names can refer to different parcels.
      </p>
      {result.loading && <StatusMessage>Finding properties…</StatusMessage>}
      {result.error && (
        <StatusMessage tone="error">
          Property search is unavailable. Retry before starting the inquiry.
        </StatusMessage>
      )}
      {redirectPidn && (
        <ButtonLink to={`/sites?pidn=${encodeURIComponent(redirectPidn)}`}>
          Review parcel {redirectPidn}
        </ButtonLink>
      )}
      <div className="site-inquiry-list">
        {matches.map((item, index) => (
          <Link
            key={`${item.pidn}:${index}`}
            className="site-inquiry-card"
            to={`/sites?pidn=${encodeURIComponent(item.pidn!)}`}
          >
            <strong>{item.title || item.pidn}</strong>
            <span>{item.subtitle}</span>
            <small>PIDN {item.pidn} · Confirm identity</small>
          </Link>
        ))}
      </div>
      {result.data && !matches.length && !redirectPidn && (
        <StatusMessage>
          No matching parcel was found. Try the PIDN or open the <Link to="/map">map</Link> to
          identify the site.
        </StatusMessage>
      )}
    </section>
  )
}

function InquiryEditor({ pidn, initial }: { pidn: string; initial?: SiteInquiry }) {
  const navigate = useNavigate()
  const openSource = useSourceViewer()
  const response = useFetchJson<SiteIntakePacket>(`/api/parcels/${encodeURIComponent(pidn)}/intake`)
  const packet = response.data
  const [draft, setDraft] = useState<SiteInquiry>(
    () =>
      initial ?? {
        id: crypto.randomUUID(),
        pidn,
        label: '',
        proposed_use: '',
        note: '',
        questions: '',
        status: 'researching',
        reviewed_revision: null,
        updated_at: new Date().toISOString(),
      },
  )
  const [message, setMessage] = useState('')
  const [failure, setFailure] = useState('')
  const [dirty, setDirty] = useState(false)
  const [exporting, setExporting] = useState(false)
  const reviewed = packet && draft.reviewed_revision === packet.revision
  useEffect(() => {
    if (!dirty) {
      return
    }
    const warn = (event: BeforeUnloadEvent) => event.preventDefault()
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])
  function update(change: Partial<SiteInquiry>) {
    setDraft((previous) => ({ ...previous, ...change }))
    setDirty(true)
    setMessage('')
  }
  function save(markReviewed = false) {
    if (!packet && !initial) {
      return
    }
    try {
      const next = {
        ...draft,
        label: draft.label.trim() || packet?.report.parcel.propadr || `Parcel ${pidn}`,
        reviewed_revision: markReviewed && packet ? packet.revision : draft.reviewed_revision,
        updated_at: new Date().toISOString(),
      }
      saveSiteInquiry(next)
      setDraft(next)
      setDirty(false)
      setFailure('')
      setMessage(
        markReviewed
          ? 'Saved your review of the current evidence. Open questions remain in the handoff.'
          : 'Inquiry saved.',
      )
      navigate(`/sites/${next.id}`, { replace: true })
    } catch (error) {
      setFailure(error instanceof Error ? error.message : 'The inquiry could not be saved.')
    }
  }
  function remove() {
    if (!window.confirm('Remove this inquiry and its private notes from your workspace?')) {
      return
    }
    try {
      removeSiteInquiry(draft.id)
      navigate('/sites')
    } catch (error) {
      setFailure(error instanceof Error ? error.message : 'Unable to remove this inquiry.')
    }
  }
  async function exportPacket() {
    if (!packet || dirty || exporting) {
      return
    }
    const account = watchSyncState().account?.user?.id ?? null
    setExporting(true)
    setFailure('')
    try {
      const fresh = await fetch(`/api/parcels/${encodeURIComponent(pidn)}/intake`)
      if (!fresh.ok) {
        throw new Error('Current source evidence is unavailable. The packet was not exported.')
      }
      const current: SiteIntakePacket = await fresh.json()
      if (account !== (watchSyncState().account?.user?.id ?? null)) {
        return
      }
      if (current.revision !== packet.revision) {
        response.reload()
        throw new Error(
          'Evidence changed before export. Review the refreshed packet and save before exporting again.',
        )
      }
      downloadText(`countyiq-site-${pidn}.txt`, sitePacketText(draft, current))
    } catch (error) {
      response.reload()
      setFailure(error instanceof Error ? error.message : 'Unable to verify the packet for export.')
    } finally {
      setExporting(false)
    }
  }
  return (
    <>
      <div className="site-toolbar">
        <ButtonLink to="/sites">All inquiries</ButtonLink>
        <ButtonLink to={`/property/${encodeURIComponent(pidn)}`}>
          Full property investigation
        </ButtonLink>
        <Button onClick={response.reload}>Refresh evidence</Button>
      </div>
      {response.loading && <StatusMessage>Loading the current site evidence…</StatusMessage>}
      {response.error && (
        <StatusMessage tone="error">
          Current evidence is unavailable or its use is restricted. Your private notes are kept.
          Refresh to retry; packet export is unavailable until the sources can be checked.
        </StatusMessage>
      )}
      {packet && (
        <section className="site-identity">
          <div>
            <div className="page-eyebrow">Confirm the property</div>
            <h2>{packet.report.parcel.propadr || `Parcel ${pidn}`}</h2>
            <p>
              {packet.report.parcel.municipality || 'Municipality unknown'} · PIDN {pidn}
            </p>
            <p>
              Recorded owner: {packet.report.parcel.owner_full || 'Unknown'} ·{' '}
              {packet.report.parcel.acres ?? 'Unknown'} acres
            </p>
            <p>Confirm the boundary and reviewing authority before using the packet.</p>
          </div>
          <ParcelContextMap report={packet.report} />
        </section>
      )}
      <section className="site-section" aria-labelledby="inquiry-input-heading">
        <h2 id="inquiry-input-heading">Client inquiry</h2>
        <p className="site-muted">Private user input. It does not change the source evidence.</p>
        <div className="site-form-grid">
          <label>
            Inquiry name
            <input
              value={draft.label}
              placeholder={packet?.report.parcel.propadr || `Parcel ${pidn}`}
              onChange={(event) => update({ label: event.target.value })}
              maxLength={200}
            />
          </label>
          <label>
            Workflow stage
            <select
              value={draft.status}
              onChange={(event) => update({ status: event.target.value as SiteInquiry['status'] })}
            >
              <option value="researching">Researching</option>
              <option value="ready_for_handoff">Ready for handoff</option>
              <option value="on_hold">On hold</option>
            </select>
          </label>
          <label className="site-full">
            Proposed use
            <textarea
              value={draft.proposed_use}
              onChange={(event) =>
                update({ proposed_use: event.target.value, reviewed_revision: null })
              }
              maxLength={2000}
              rows={3}
              placeholder="Describe what the client wants to do, including the scale and current stage."
            />
          </label>
        </div>
      </section>
      {packet && (
        <>
          <section className="site-section" aria-labelledby="site-evidence-heading">
            <div className="site-section-title">
              <h2 id="site-evidence-heading">What the records establish</h2>
              <Button onClick={() => openSource(packet.report.evidence)}>
                Check source receipts
              </Button>
            </div>
            <div className="site-facts">
              <article>
                <h3>Mapped zoning</h3>
                <strong>
                  {packet.report.zoning
                    ? `${packet.report.zoning.code} · ${packet.report.zoning.name}`
                    : 'Unknown'}
                </strong>
                <p>
                  This is a parcel-center match. Check split zoning and the current municipal
                  ordinance; it does not establish that the proposed use is permitted.
                </p>
              </article>
              <article>
                <h3>Flood screening</h3>
                <p>{floodScreeningSummary(packet.report.flood_zone)}</p>
              </article>
              <article>
                <h3>Mapped soils</h3>
                <strong>{packet.report.soil_profile.mapped_coverage_pct}% parcel coverage</strong>
                <p>
                  {packet.report.soil_profile.considerations.join(' ') ||
                    'No soil considerations established by the loaded records.'}
                </p>
                <p>Missing mapping does not establish site suitability.</p>
              </article>
            </div>
            <div className="site-source-grid">
              {packet.sources.map((source) => (
                <div key={source.key}>
                  <strong>{source.label}</strong>
                  <span className={`site-source-status site-source-${source.status}`}>
                    {source.status === 'current'
                      ? 'Refresh current'
                      : source.status === 'stale'
                        ? 'Refresh needs attention'
                        : 'Refresh unverified'}
                  </span>
                  <small>
                    Last successful acquisition:{' '}
                    {source.last_successful_run_at
                      ? formatShortDate(source.last_successful_run_at)
                      : 'Unknown'}
                  </small>
                </div>
              ))}
            </div>
            <p className="site-muted">
              Acquisition dates describe when CountyIQ checked a source, not when the map or rule
              became effective.
            </p>
          </section>
          <section className="site-section" aria-labelledby="site-history-heading">
            <h2 id="site-history-heading">Municipal record trail</h2>
            <p>
              These are source passages associated with this parcel by PIDN or address. A reference
              does not itself establish approval or a complete project history.
            </p>
            <MunicipalEvidence
              pidn={pidn}
              municipality={packet.report.parcel.municipality}
              initialData={packet.report.municipal_evidence}
            />
            <details>
              <summary>Collection coverage for this municipality</summary>
              {packet.municipal_collection.length ? (
                <ul>
                  {packet.municipal_collection.map((body, index) => (
                    <li key={`${body.body_name}:${index}`}>
                      {body.body_name}: {body.status.replaceAll('_', ' ')} · Checked{' '}
                      {body.checked_at ? formatShortDate(body.checked_at) : 'unknown'}
                    </li>
                  ))}
                </ul>
              ) : (
                <p>No active municipal collection coverage is established.</p>
              )}
            </details>
          </section>
          <section className="site-section">
            <h2>Questions for the first conversation</h2>
            <ul>
              {packet.questions.map((question) => (
                <li key={question}>{question}</li>
              ))}
            </ul>
          </section>
        </>
      )}
      <section className="site-section">
        <h2>Research handoff</h2>
        <div className="site-form-grid">
          <label className="site-full">
            Open questions and required follow-up
            <textarea
              value={draft.questions}
              onChange={(event) => update({ questions: event.target.value })}
              maxLength={4000}
              rows={4}
              placeholder="Record the questions that still need a client, municipal or professional answer."
            />
          </label>
          <label className="site-full">
            Reviewer notes
            <textarea
              value={draft.note}
              onChange={(event) => update({ note: event.target.value })}
              maxLength={4000}
              rows={4}
              placeholder="Record your interpretation separately from the cited facts."
            />
          </label>
        </div>
        {packet && (
          <StatusMessage>
            {reviewed
              ? 'You reviewed this evidence revision. Your workflow stage and notes remain your own assessment.'
              : draft.reviewed_revision
                ? 'Evidence has changed since your last review. Recheck the sources before handoff.'
                : 'This evidence has not been marked reviewed.'}
          </StatusMessage>
        )}
        {message && <StatusMessage tone="success">{message}</StatusMessage>}
        {failure && <StatusMessage tone="error">{failure}</StatusMessage>}
        <div className="site-toolbar">
          <Button tone="primary" onClick={() => save()} disabled={!packet && !initial}>
            Save inquiry{dirty ? ' *' : ''}
          </Button>
          <Button disabled={!packet || !draft.proposed_use.trim()} onClick={() => save(true)}>
            Mark evidence reviewed and save
          </Button>
          <Button
            disabled={!packet || dirty || !initial || exporting}
            onClick={() => void exportPacket()}
          >
            Export research handoff
          </Button>
          {initial && (
            <Button tone="quiet" onClick={remove}>
              Remove inquiry
            </Button>
          )}
        </div>
        {packet && <p className="site-muted">{packet.scope_note}</p>}
      </section>
    </>
  )
}
