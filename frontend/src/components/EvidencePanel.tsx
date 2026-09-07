import { Fragment, type ReactNode } from 'react'

import { CITATION_PATTERN, citationKey, sourceTitle } from '../lib/customerEvidence'
import type { EvidenceItem } from '../types/api'
import { SourceContent } from './SourceViewer'
import { useSourceViewer } from '../lib/useSourceViewer'

export function CitedText({ text, evidence }: { text: string; evidence: EvidenceItem[] }) {
  const openSource = useSourceViewer()
  const byCitation = new Map(
    evidence.map((item, index) => [item.citation_key.toLowerCase(), { item, index }]),
  )
  const nodes: ReactNode[] = []
  let cursor = 0
  for (const match of text.matchAll(CITATION_PATTERN)) {
    const start = match.index ?? 0
    if (start > cursor) {
      nodes.push(text.slice(cursor, start))
    }
    const key = match[1]
      ? citationKey(match[1], match[2].trim())
      : citationKey('evidence', match[4].trim(), match[3].trim())
    const resolved = byCitation.get(key)
    nodes.push(
      resolved ? (
        <button
          key={`${key}-${start}`}
          type="button"
          title={sourceTitle(resolved.item)}
          aria-label={`View source: ${sourceTitle(resolved.item)}`}
          onClick={() => openSource(evidence, resolved.index)}
          className="source-citation"
        >
          {resolved.index + 1}
        </button>
      ) : (
        <span key={`${key}-${start}`} className="source-unavailable">
          (source unavailable)
        </span>
      ),
    )
    cursor = start + match[0].length
  }
  if (cursor < text.length) {
    nodes.push(text.slice(cursor))
  }
  return (
    <>
      {nodes.map((node, index) => (
        <Fragment key={index}>{node}</Fragment>
      ))}
    </>
  )
}

export default function EvidencePanel({
  items,
  title = 'View sources',
}: {
  items: EvidenceItem[]
  title?: string
  intro?: string
}) {
  const openSource = useSourceViewer()
  if (items.length === 0) {
    return null
  }
  return (
    <div className="source-catalog">
      <button type="button" className="source-catalog-button" onClick={() => openSource(items)}>
        {title} ({items.length})
      </button>
      <div className="source-print-appendix">
        {items.map((item, index) => (
          <article key={item.evidence_id}>
            <h3>
              {index + 1}. {sourceTitle(item)}
            </h3>
            <SourceContent item={item} />
          </article>
        ))}
      </div>
    </div>
  )
}
