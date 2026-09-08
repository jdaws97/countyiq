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
  isMappedSource,
  sourceMapLink,
  sourceExcerptText,
  sourceOriginalUrl,
  sourcePassages,
  sourcePropertyPath,
  sourceTitle,
  type SourcePassage,
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
  const translated = item.details?.translated === true
  const original = sourceOriginalUrl(item)
  const propertyPath = sourcePropertyPath(item)
  const caveat = sourceCaveat(item)
  const mapped = isMappedSource(item)
  const mapLink = sourceMapLink(item)
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
        {mapLink && (
          <Link className="ciq-button ciq-button-primary" to={mapLink.path} onClick={onNavigate}>
            {mapLink.label}
          </Link>
        )}
        {original ? (
          <a
            className={`ciq-button ${mapped ? 'ciq-button-secondary' : 'ciq-button-primary'}`}
            href={original}
            target="_blank"
            rel="noreferrer"
          >
            {mapped ? 'Open official data record ↗' : sourceLinkLabel(original)}
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
      {mapped && (
        <p className="source-reading-guide">
          These are mapped source facts.{' '}
          {mapLink ? 'Use the map to see the property in context. ' : ''}
          The official data record contains the original attributes.
        </p>
      )}
      {passages.length > 0 && (
        <section
          className="source-passages"
          aria-label={translated ? 'English translation' : 'Original wording'}
        >
          <h3>
            {translated
              ? 'English translation of the source excerpt'
              : 'Excerpts from the original document'}
          </h3>
          <p className="source-reading-guide">
            {translated
              ? 'Translated from the original document. Page links open the beginning of the supporting passage.'
              : 'Original wording is preserved below. Page links use PDF page numbers where available.'}
          </p>
          {passages.map((passage, index) => (
            <SourcePassageContent
              key={`${item.evidence_id}-${index}`}
              item={item}
              passage={passage}
              index={index}
            />
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

function SourcePassageContent({
  item,
  passage,
  index,
}: {
  item: EvidenceItem
  passage: SourcePassage
  index: number
}) {
  const [copyStatus, setCopyStatus] = useState('')
  const original = sourceOriginalUrl(item, passage)
  const pageLink = passage.page != null && original && /#page=\d+$/.test(original)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(sourceExcerptText(item, passage))
      setCopyStatus('Excerpt and source copied')
    } catch {
      setCopyStatus('Could not copy. Select the excerpt below to copy it manually.')
    }
  }
  return (
    <div className="source-passage">
      <div className="source-passage-heading">
        <strong>
          Excerpt {index + 1}
          {passage.page != null ? ` · PDF page ${passage.page}` : ''}
        </strong>
        {pageLink && (
          <a href={original} target="_blank" rel="noreferrer">
            Open page {passage.page} ↗
          </a>
        )}
      </div>
      <blockquote>{passage.text}</blockquote>
      <div className="source-excerpt-actions">
        <button type="button" className="source-catalog-button" onClick={() => void copy()}>
          Copy excerpt & source
        </button>
        <span role="status">{copyStatus}</span>
      </div>
    </div>
  )
}
