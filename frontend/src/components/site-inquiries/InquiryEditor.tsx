import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import ParcelContextMap from '../ParcelContextMap'
import { Button, ButtonLink, StatusMessage } from '../ui'
import { useFetchJson } from '../../lib/useFetchJson'
import { getSiteInquiries, removeSiteInquiry } from '../../lib/siteInquiries'
import { watchSyncState } from '../../lib/watchSync'
import { downloadText } from '../../lib/investigationState'
import { sitePacketText } from '../../lib/sitePacket'
import { formatShortDate } from '../../lib/format'
import type { SiteInquiry, SiteIntakePacket } from '../../types/siteIntake'
import { useInquiryDraft } from './useInquiryDraft'
import SiteEvidence from './SiteEvidence'
import SiteQuestions from './SiteQuestions'
import SiteHandoff from './SiteHandoff'
import UnsavedInquiryDialog from './UnsavedInquiryDialog'

export default function InquiryEditor({ pidn, initial }: { pidn: string; initial?: SiteInquiry }) {
  const navigate = useNavigate()
  const response = useFetchJson<SiteIntakePacket>(`/api/parcels/${encodeURIComponent(pidn)}/intake`)
  const packet = response.data
  const editor = useInquiryDraft(pidn, initial)
  const { draft, dirty, blocker } = editor
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState('')
  const [preview, setPreview] = useState<SiteIntakePacket | null>(null)
  const active = useRef(true)
  const edits = useRef(0)
  const reviewed = Boolean(packet && draft.reviewed_revision === packet.revision)
  const openQuestions =
    5 - (draft.question_reviews ?? []).filter((question) => question.status !== 'open').length
  useEffect(() => {
    active.current = true
    return () => {
      active.current = false
    }
  }, [])

  function update(change: Partial<SiteInquiry>) {
    edits.current += 1
    editor.update(change)
    setExportError('')
  }

  function save(markReviewed = false) {
    const saved = editor.save(packet, markReviewed)
    if (saved && !initial) {
      navigate(`/sites/${saved.id}`, { replace: true })
    }
  }

  function remove() {
    if (!window.confirm('Remove this inquiry and its private notes from your workspace?')) {
      return
    }
    try {
      removeSiteInquiry(draft.id)
      editor.discard()
      navigate('/sites')
    } catch (error) {
      setExportError(error instanceof Error ? error.message : 'Unable to remove this inquiry.')
    }
  }

  async function prepareHandoff(kind: 'preview' | 'print' | 'text') {
    if (!packet || dirty || !initial || exporting) {
      return
    }
    const account = watchSyncState().account?.user?.id ?? null
    const editVersion = edits.current
    setExporting(true)
    setExportError('')
    try {
      const fresh = await fetch(`/api/parcels/${encodeURIComponent(pidn)}/intake`)
      if (!fresh.ok) {
        throw new Error('Current source evidence is unavailable. The handoff was not exported.')
      }
      const current: SiteIntakePacket = await fresh.json()
      if (!active.current || account !== (watchSyncState().account?.user?.id ?? null)) {
        return
      }
      if (
        editVersion !== edits.current ||
        getSiteInquiries().find((item) => item.id === draft.id)?.updated_at !== draft.updated_at
      ) {
        throw new Error(
          'The inquiry changed while preparing the handoff. Save and review it before exporting.',
        )
      }
      if (current.revision !== packet.revision) {
        response.reload()
        setPreview(null)
        throw new Error(
          'Evidence changed. Review the refreshed records and save before preparing the handoff again.',
        )
      }
      if (kind === 'text') {
        downloadText(`countyiq-site-${pidn}.txt`, sitePacketText(draft, current))
      } else {
        setPreview(current)
        if (kind === 'print') {
          await new Promise<void>((resolve) =>
            window.requestAnimationFrame(() => window.requestAnimationFrame(() => resolve())),
          )
          if (active.current && account === (watchSyncState().account?.user?.id ?? null)) {
            window.print()
          }
        } else {
          window.scrollTo({ top: 0, behavior: 'smooth' })
        }
      }
    } catch (error) {
      if (active.current) {
        setPreview(null)
        setExportError(error instanceof Error ? error.message : 'Unable to verify the handoff.')
      }
    } finally {
      if (active.current) {
        setExporting(false)
      }
    }
  }

  if (preview) {
    return (
      <SiteHandoff
        inquiry={draft}
        packet={preview}
        busy={exporting}
        error={exportError}
        onClose={() => setPreview(null)}
        onPrint={() => void prepareHandoff('print')}
        onDownload={() => void prepareHandoff('text')}
      />
    )
  }

  return (
    <div className="site-editor">
      <div className="site-toolbar site-context-links">
        <ButtonLink to="/sites">← All inquiries</ButtonLink>
        <ButtonLink to={`/property/${encodeURIComponent(pidn)}`}>
          Full property investigation
        </ButtonLink>
        <Button onClick={response.reload} disabled={response.loading}>
          Refresh evidence
        </Button>
      </div>
      <div className="site-review-bar" aria-label="Inquiry save and review status">
        <div className="site-save-state" role="status">
          <strong>
            {dirty
              ? 'Unsaved changes'
              : initial
                ? 'Saved in your workspace'
                : 'New inquiry · Not saved yet'}
          </strong>
          <span>
            {dirty
              ? 'Save before leaving or preparing a handoff.'
              : initial
                ? `Last saved ${formatShortDate(initial.updated_at)}`
                : 'Confirm the property and describe the proposed use.'}
          </span>
        </div>
        <div className="site-review-actions">
          <Button
            tone="primary"
            onClick={() => save()}
            disabled={exporting || (!packet && !initial)}
          >
            Save inquiry
          </Button>
          <Button
            onClick={() => void prepareHandoff('preview')}
            disabled={!packet || dirty || !initial || exporting}
          >
            {exporting ? 'Checking evidence…' : 'Preview handoff'}
          </Button>
        </div>
      </div>
      {editor.message && <StatusMessage tone="success">{editor.message}</StatusMessage>}
      {(editor.failure || exportError) && (
        <StatusMessage tone="error">{editor.failure || exportError}</StatusMessage>
      )}
      {response.loading && <StatusMessage>Checking the current site evidence…</StatusMessage>}
      {response.error && (
        <StatusMessage tone="error">
          Current evidence is unavailable or its use is restricted. Your private notes are kept.
          Refresh to retry; handoff export needs a current source check.
        </StatusMessage>
      )}

      {packet && (
        <section className="site-identity" aria-labelledby="site-identity-heading">
          <div>
            <div className="page-eyebrow">The candidate property</div>
            <h2 id="site-identity-heading">{packet.report.parcel.propadr || `Parcel ${pidn}`}</h2>
            <p>
              {packet.report.parcel.municipality || 'Municipality unknown'} ·{' '}
              {packet.report.parcel.acres ?? 'Unknown'} acres
            </p>
            <dl className="site-identity-details">
              <div>
                <dt>Parcel ID</dt>
                <dd>{pidn}</dd>
              </div>
              <div>
                <dt>Recorded owner</dt>
                <dd>{packet.report.parcel.owner_full || 'Unknown'}</dd>
              </div>
            </dl>
            <p className="site-muted">
              Confirm the boundary and reviewing authority before using the handoff.
            </p>
          </div>
          <ParcelContextMap report={packet.report} />
        </section>
      )}
      <nav className="site-section-nav" aria-label="Inquiry sections">
        <a href="#site-proposal">1 · Proposed use</a>
        <a href="#site-evidence">2 · Site evidence</a>
        <a href="#site-history">3 · Municipal record</a>
        <a href="#site-questions">4 · Questions & handoff</a>
      </nav>
      <section id="site-proposal" className="site-section" aria-labelledby="inquiry-input-heading">
        <div className="site-section-title">
          <div>
            <div className="page-eyebrow">01 · Frame the inquiry</div>
            <h2 id="inquiry-input-heading">What is the client considering?</h2>
          </div>
        </div>
        <p className="site-muted">Your private working brief. Source evidence stays separate.</p>
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
              <option value="ready_for_handoff" disabled={!reviewed}>
                Ready for handoff
              </option>
              <option value="on_hold">On hold</option>
            </select>
            {!reviewed && (
              <span className="site-field-note">
                Review the current evidence before marking ready.
              </span>
            )}
          </label>
          <label className="site-full">
            Proposed use
            <textarea
              value={draft.proposed_use}
              onChange={(event) =>
                update({
                  proposed_use: event.target.value,
                  reviewed_revision: null,
                  status: draft.status === 'ready_for_handoff' ? 'researching' : draft.status,
                })
              }
              maxLength={2000}
              rows={3}
              placeholder="What does the client want to do? Include scale, existing conditions and the current stage."
            />
          </label>
        </div>
      </section>
      {packet && <SiteEvidence packet={packet} pidn={pidn} />}
      <section
        id="site-questions"
        className="site-section"
        aria-labelledby="site-questions-heading"
      >
        <div className="page-eyebrow">04 · Prepare the conversation</div>
        <div className="site-section-title">
          <h2 id="site-questions-heading">Questions & next steps</h2>
          <span className="site-count-label">{openQuestions} still open</span>
        </div>
        <p>
          Keep the questions that need an answer. Record who confirmed an answer and when; these
          responses are your assessment.
        </p>
        {packet && (
          <SiteQuestions
            inquiry={draft}
            packet={packet}
            onChange={(question_reviews) => update({ question_reviews })}
          />
        )}
        <div className="site-form-grid site-handoff-notes">
          <label className="site-full">
            Additional open questions
            <textarea
              value={draft.questions}
              onChange={(event) => update({ questions: event.target.value })}
              maxLength={4000}
              rows={3}
              placeholder="What else needs a client, municipal or professional answer?"
            />
          </label>
          <label className="site-full">
            Reviewer notes
            <textarea
              value={draft.note}
              onChange={(event) => update({ note: event.target.value })}
              maxLength={4000}
              rows={3}
              placeholder="Record your interpretation separately from the cited facts."
            />
          </label>
        </div>
        <div className={`site-review-summary ${reviewed ? 'site-review-complete' : ''}`}>
          <div>
            <strong>
              {!packet
                ? response.loading
                  ? 'Checking the evidence revision…'
                  : 'Current evidence could not be verified'
                : reviewed
                  ? 'Current evidence reviewed'
                  : draft.reviewed_revision
                    ? 'Evidence has changed since your review'
                    : 'Ready to review the evidence?'}
            </strong>
            <p>
              {reviewed
                ? 'Open questions stay in the handoff. Your review is not a determination of permitted use or buildability.'
                : 'Check the facts, source limitations and municipal trail before acknowledging this revision.'}
            </p>
          </div>
          <Button
            onClick={() => save(true)}
            disabled={!packet || !draft.proposed_use.trim() || exporting}
          >
            Mark reviewed & save
          </Button>
        </div>
        {packet && <p className="site-muted">{packet.scope_note}</p>}
        {initial && (
          <Button tone="quiet" onClick={remove}>
            Remove inquiry
          </Button>
        )}
      </section>
      {blocker.state === 'blocked' && (
        <UnsavedInquiryDialog
          error={editor.failure}
          onStay={() => blocker.reset()}
          onDiscard={() => {
            editor.discard()
            blocker.proceed()
          }}
          onSave={() => {
            if (editor.save(packet)) {
              blocker.proceed()
            }
          }}
        />
      )}
    </div>
  )
}
