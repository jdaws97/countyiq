import { useEffect, useRef, useState } from 'react'
import { useBlocker } from 'react-router-dom'
import { saveSiteInquiry, validQuestionReviews } from '../../lib/siteInquiries'
import type { SiteInquiry, SiteIntakePacket } from '../../types/siteIntake'

type EditSession = { draft: SiteInquiry; baseUpdatedAt: string | null }

export function useInquiryDraft(pidn: string, initial?: SiteInquiry) {
  const [created, setCreated] = useState<SiteInquiry>(() => ({
    id: crypto.randomUUID(),
    pidn,
    label: '',
    proposed_use: '',
    note: '',
    questions: '',
    status: 'researching',
    reviewed_revision: null,
    question_reviews: [],
    updated_at: new Date().toISOString(),
  }))
  const [editing, setEditing] = useState<EditSession | null>(null)
  const [failure, setFailure] = useState('')
  const [message, setMessage] = useState('')
  const unsaved = useRef(false)
  const draft = editing?.draft ?? initial ?? created
  const dirty = editing !== null
  const blocker = useBlocker(({ currentLocation, nextLocation }) => {
    return (
      unsaved.current &&
      (currentLocation.pathname !== nextLocation.pathname ||
        currentLocation.search !== nextLocation.search)
    )
  })

  useEffect(() => {
    if (!dirty) {
      return
    }
    const warn = (event: BeforeUnloadEvent) => event.preventDefault()
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])

  function update(change: Partial<SiteInquiry>) {
    unsaved.current = true
    setEditing((previous) => ({
      draft: { ...(previous?.draft ?? initial ?? created), ...change },
      baseUpdatedAt: previous ? previous.baseUpdatedAt : (initial?.updated_at ?? null),
    }))
    setMessage('')
    setFailure('')
  }

  function discard() {
    unsaved.current = false
    setEditing(null)
    setFailure('')
  }

  function save(packet: SiteIntakePacket | null, markReviewed = false): SiteInquiry | null {
    if (!packet && !initial) {
      setFailure('Confirm the property before saving this new inquiry.')
      return null
    }
    if (!validQuestionReviews(draft.question_reviews ?? [])) {
      setFailure('Add a response explaining each answered or inapplicable question before saving.')
      return null
    }
    try {
      const reviewedRevision = markReviewed && packet ? packet.revision : draft.reviewed_revision
      const status =
        draft.status === 'ready_for_handoff' &&
        (!packet || reviewedRevision !== packet.revision || !draft.proposed_use.trim())
          ? 'researching'
          : draft.status
      const next = {
        ...draft,
        label: draft.label.trim() || packet?.report.parcel.propadr || `Parcel ${pidn}`,
        reviewed_revision: reviewedRevision,
        status,
        updated_at: new Date().toISOString(),
      }
      const expectedUpdatedAt = editing ? editing.baseUpdatedAt : (initial?.updated_at ?? null)
      saveSiteInquiry(next, expectedUpdatedAt)
      unsaved.current = false
      setCreated(next)
      setEditing(null)
      setFailure('')
      setMessage(
        markReviewed ? 'Current evidence marked reviewed and inquiry saved.' : 'Inquiry saved.',
      )
      return next
    } catch (error) {
      setFailure(error instanceof Error ? error.message : 'The inquiry could not be saved.')
      return null
    }
  }

  return { draft, dirty, blocker, failure, message, update, discard, save }
}
