import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'

import type { EvidenceItem } from '../types/api'
import { formatShortDate } from '../lib/format'
import { sourceLinkLabel } from '../lib/evidence'
import { SourceContext } from '../lib/useSourceViewer'
import {
  sourceCaveat,
  sourceDocumentLabel,
  sourceFacts,
  sourceOriginalUrl,
  sourcePassages,
  sourcePropertyPath,
  sourceTitle,
} from '../lib/customerEvidence'
import './SourceViewer.css'

interface SourceSelection {
  items: EvidenceItem[]
  index: number
}

export default function SourceViewerProvider({ children }: { children: ReactNode }) {
  const [selection, setSelection] = useState<SourceSelection | null>(null)
  const dialog = useRef<HTMLDialogElement>(null)
  const location = useLocation()
  const routeKey = location.key
  const [openedRoute, setOpenedRoute] = useState(routeKey)
  const isOpen = selection != null && openedRoute === routeKey

  useEffect(() => {
    if (!isOpen) {
      dialog.current?.close()
      return
    }
    dialog.current?.showModal()
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = previousOverflow
    }
  }, [isOpen])

  const open = (items: EvidenceItem[], index = 0) => {
    if (!items[index]) {
      return
    }
    setOpenedRoute(routeKey)
    setSelection({ items, index })
  }
  const close = () => setSelection(null)
  const current = selection?.items[selection.index]

  return (
    <SourceContext.Provider value={open}>
      {children}
      <dialog
        ref={dialog}
        className="source-viewer"
        aria-labelledby="source-viewer-title"
        onCancel={close}
        onClose={close}
        onClick={(event) => {
          if (event.target === event.currentTarget) {
            close()
          }
        }}
      >
        {current && selection && (
          <div className="source-viewer-content">
            <header className="source-viewer-header">
              <div>
                <div className="record-eyebrow">Supporting source</div>
                <h2 id="source-viewer-title">{sourceTitle(current)}</h2>
              </div>
              <button className="ciq-button" type="button" onClick={close} autoFocus>
                Close
              </button>
            </header>
            {selection.items.length > 1 && (
              <label className="source-viewer-select">
                Source {selection.index + 1} of {selection.items.length}
                <select
                  value={selection.index}
                  onChange={(event) =>
                    setSelection({ ...selection, index: Number(event.target.value) })
                  }
                >
                  {selection.items.map((item, index) => (
                    <option key={`${item.evidence_id}-${index}`} value={index}>
                      {sourceTitle(item)}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <SourceContent item={current} onNavigate={close} />
          </div>
        )}
      </dialog>
    </SourceContext.Provider>
  )
}

export function SourceContent({
  item,
  onNavigate,
}: {
  item: EvidenceItem
  onNavigate?: () => void
}) {
  const facts = sourceFacts(item)
  const passages = sourcePassages(item)
  const original = sourceOriginalUrl(item)
  const propertyPath = sourcePropertyPath(item)
  const caveat = sourceCaveat(item)
  const date = formatShortDate(
    typeof item.details?.meeting_date === 'string' ? item.details.meeting_date : item.effective_at,
  )

  return (
    <div className="source-content">
      <div className="source-content-meta">
        <span>{sourceDocumentLabel(item)}</span>
        {typeof item.details?.body_name === 'string' && <span>{item.details.body_name}</span>}
        {date && <span>{date}</span>}
      </div>
      <div className="source-content-actions">
        {original ? (
          <a
            className="ciq-button ciq-button-primary"
            href={original}
            target="_blank"
            rel="noreferrer"
          >
            {sourceLinkLabel(original)}
          </a>
        ) : (
          <span>Original source link unavailable</span>
        )}
        {propertyPath && (
          <Link className="ciq-button" to={propertyPath} onClick={onNavigate}>
            Open related record
          </Link>
        )}
      </div>
      {passages.length > 0 && (
        <section className="source-passages" aria-label="Original wording">
          <h3>Original wording</h3>
          {passages.map((passage, index) => (
            <div key={index}>
              <blockquote>{passage.text}</blockquote>
              {passage.page != null && <p className="source-page">Page {passage.page}</p>}
            </div>
          ))}
        </section>
      )}
      {facts.length > 0 && (
        <dl className="source-facts">
          {facts.map((fact, index) => (
            <div key={`${fact.label}-${index}`}>
              <dt>{fact.label}</dt>
              <dd>{fact.value}</dd>
            </div>
          ))}
        </dl>
      )}
      {caveat && <p className="source-limitation">{caveat}</p>}
      {!passages.length && !facts.length && (
        <p>Open the original record to inspect the underlying information.</p>
      )}
      {item.observed_at && (
        <p className="source-observed">Added to CountyIQ {formatShortDate(item.observed_at)}</p>
      )}
    </div>
  )
}
