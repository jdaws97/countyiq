import { Fragment, type ReactNode } from 'react'
import { Link } from 'react-router-dom'

import Badge from './Badge'
import { openEvidenceReceipt, sourceLinkLabel } from '../lib/evidence'
import { formatLabel, formatShortDate } from '../lib/format'
import type { EvidenceItem } from '../types/api'

function citationLookupKey(kind: string, value: string, group?: string): string {
  if (kind.toLowerCase() === 'evidence') {
    return `evidence:${group ?? ''}:${value}`.toLowerCase()
  }
  return `${kind}:${value}`.toLowerCase()
}

export function CitedText({ text, evidence }: { text: string; evidence: EvidenceItem[] }) {
  const byCitation = new Map(
    evidence.map((item, index) => [item.citation_key.toLowerCase(), { item, index }]),
  )
  const token = /\[(Signal|Parcel):\s*([^\]]+)\]|\[Evidence:\s*([^:\]]+):([^\]]+)\]/gi
  const nodes: ReactNode[] = []
  let cursor = 0
  for (const match of text.matchAll(token)) {
    const start = match.index ?? 0
    if (start > cursor) {
      nodes.push(text.slice(cursor, start))
    }
    const key = match[1]
      ? citationLookupKey(match[1], match[2].trim())
      : citationLookupKey('evidence', match[4].trim(), match[3].trim())
    const resolved = byCitation.get(key)
    if (resolved) {
      nodes.push(
        <a
          key={`${key}-${start}`}
          href={`#${resolved.item.evidence_id}`}
          title={`Open evidence: ${resolved.item.label}`}
          onClick={() => openEvidenceReceipt(resolved.item.evidence_id)}
          className="cite-link"
        >
          [E{resolved.index + 1}]
        </a>,
      )
    } else {
      nodes.push(match[0])
    }
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

function displayValue(value: unknown): string {
  if (value == null || value === '') {
    return '—'
  }
  if (typeof value === 'boolean') {
    return value ? 'Yes' : 'No'
  }
  if (typeof value === 'number') {
    return value.toLocaleString()
  }
  if (Array.isArray(value)) {
    return value.map(displayValue).join(', ')
  }
  if (typeof value === 'object') {
    const record = value as Record<string, unknown>
    if ('old' in record || 'new' in record) {
      return `${displayValue(record.old)} → ${displayValue(record.new)}`
    }
    return Object.entries(record)
      .filter(([key]) => !['passage_ids', 'source_sha256', 'start', 'end'].includes(key))
      .map(([key, item]) => `${formatLabel(key)}: ${displayValue(item)}`)
      .join(' · ')
  }
  return String(value)
}

export default function EvidencePanel({
  items,
  title = 'Evidence receipts',
  intro,
}: {
  items: EvidenceItem[]
  title?: string
  intro?: string
}) {
  if (items.length === 0) {
    return null
  }

  return (
    <div>
      <div style={{ marginBottom: 10 }}>
        <div className="evidence-panel-title">{title}</div>
        {intro && <div className="evidence-panel-intro">{intro}</div>}
      </div>
      <div className="evidence-list">
        {items.map((item, index) => {
          const originalHref = item.document_url ?? item.url
          const facts = Object.entries(item.details ?? {}).filter(
            ([key]) =>
              ![
                'contract_version',
                'evidence_spans',
                'supports',
                'source_sha256',
                'passage_ids',
                'identity_status',
                'discovery_eligible',
                'location_status',
              ].includes(key),
          )
          const confidenceLabel = /proceeding|extraction/.test(item.source_kind)
            ? 'extraction confidence'
            : item.source_kind === 'validated_signal'
              ? 'validation confidence'
              : 'confidence'
          const dates = [
            item.effective_at ? `record ${formatShortDate(item.effective_at)}` : null,
            item.observed_at ? `observed ${formatShortDate(item.observed_at)}` : null,
          ].filter(Boolean)
          return (
            <details id={item.evidence_id} key={item.evidence_id} className="evidence-receipt">
              <summary>
                <span className="evidence-receipt-title">
                  <Badge color="var(--accent-gold)" mono>
                    E{index + 1}
                  </Badge>
                  <span className="evidence-receipt-label">{item.label}</span>
                  <Badge color="var(--text-muted)">{formatLabel(item.source_kind)}</Badge>
                  {item.confidence != null && (
                    <Badge color="var(--text-muted)">
                      {Math.round(item.confidence * 100)}% {confidenceLabel}
                    </Badge>
                  )}
                </span>
              </summary>
              <div className="evidence-receipt-body">
                {item.excerpt && (
                  <blockquote className="evidence-excerpt">{item.excerpt}</blockquote>
                )}
                {facts.length > 0 && (
                  <div className="evidence-facts">
                    {facts.map(([key, value]) => (
                      <div key={key} className="evidence-fact">
                        <div className="field-label">{formatLabel(key)}</div>
                        <div className="evidence-fact-value">{displayValue(value)}</div>
                      </div>
                    ))}
                  </div>
                )}
                <div className="evidence-method">
                  <strong>How CountyIQ used it:</strong> {item.method}
                </div>
                {item.caveat && <div className="evidence-caveat">{item.caveat}</div>}
                <div className="evidence-footer">
                  {item.source_record_id && (
                    <span className="mono">record {item.source_record_id}</span>
                  )}
                  {dates.length > 0 && <span>{dates.join(' · ')}</span>}
                  {item.internal_url && <Link to={item.internal_url}>Open CountyIQ record →</Link>}
                  {originalHref && (
                    <a href={originalHref} target="_blank" rel="noreferrer">
                      {sourceLinkLabel(originalHref)}
                    </a>
                  )}
                  {!originalHref && <span>Original source link unavailable</span>}
                </div>
              </div>
            </details>
          )
        })}
      </div>
    </div>
  )
}
