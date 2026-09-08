import { Link } from 'react-router-dom'
import { useState } from 'react'

import { formatShortDate } from '../lib/format'
import { useFetchJson } from '../lib/useFetchJson'
import { useSourceViewer } from '../lib/useSourceViewer'
import SourceExplanation from './SourceExplanation'
import type {
  EvidenceItem,
  MunicipalEvidenceCard,
  MunicipalEvidenceCoverage,
  MunicipalEvidenceResponse,
} from '../types/api'
import './MunicipalEvidence.css'

const INITIAL_LIMIT = 6

export function CoverageSummary({ coverage }: { coverage: MunicipalEvidenceCoverage }) {
  return (
    <details className="municipal-evidence-coverage" aria-label="Municipal record coverage">
      <summary>
        {coverage.reviewed_documents} of {coverage.total_documents} known municipal records reviewed
        <span> · Coverage details</span>
      </summary>
      <p>
        These counts cover collected records for this municipality. Uncollected records are not
        counted.
      </p>
      <div className="municipal-evidence-coverage-counts">
        {coverage.awaiting_read_documents > 0 && (
          <span>{coverage.awaiting_read_documents} awaiting reading</span>
        )}
        {coverage.review_required_documents > 0 && (
          <span>{coverage.review_required_documents} need source review</span>
        )}
        {coverage.failed_documents > 0 && (
          <span>{coverage.failed_documents} could not be read</span>
        )}
        {coverage.blocked_documents > 0 && (
          <span>{coverage.blocked_documents} unavailable for analysis</span>
        )}
        {coverage.future_documents > 0 && (
          <span>{coverage.future_documents} dated after today</span>
        )}
      </div>
      <div className="municipal-evidence-coverage-dates">
        {coverage.last_source_observed_at && (
          <span>Last source collected: {formatShortDate(coverage.last_source_observed_at)}</span>
        )}
        {coverage.last_reviewed_at && (
          <span>Last source review: {formatShortDate(coverage.last_reviewed_at)}</span>
        )}
        {coverage.latest_meeting_date && (
          <span>Latest collected meeting: {formatShortDate(coverage.latest_meeting_date)}</span>
        )}
        {coverage.latest_reviewed_meeting_date && (
          <span>
            Latest reviewed meeting: {formatShortDate(coverage.latest_reviewed_meeting_date)}
          </span>
        )}
      </div>
    </details>
  )
}

function municipalCardSources(card: MunicipalEvidenceCard): EvidenceItem[] {
  if (card.explanation?.citation_evidence.length) {
    return card.explanation.citation_evidence.map((item) => {
      const passage = card.passages.find(
        (candidate) => candidate.text.trim() === item.excerpt?.trim(),
      )
      return {
        ...item,
        details: {
          ...item.details,
          body_name: card.body_name,
          document_kind: card.proceeding_type,
          meeting_date: card.meeting_date,
          page: passage?.page ?? null,
        },
      }
    })
  }
  return card.passages.map((passage, index) => ({
    evidence_id: `${card.id}-passage-${index}`,
    citation_key: `source:${index + 1}`,
    label: `${card.body_name} · ${formatShortDate(card.meeting_date)}`,
    source_kind: 'municipal_evidence',
    source_record_id: null,
    url: card.document_url,
    document_url: card.document_url,
    internal_url: null,
    excerpt: passage.text,
    details: {
      body_name: card.body_name,
      document_kind: card.proceeding_type,
      meeting_date: card.meeting_date,
      page: passage.page,
    },
    effective_at: card.meeting_date,
    observed_at: card.observed_at,
    method: '',
    caveat:
      card.proceeding_type === 'agenda'
        ? 'An agenda lists proposed business; it does not establish the outcome.'
        : null,
    confidence: null,
  }))
}

interface MunicipalEvidenceProps {
  municipality?: string | null
  pidn?: string | null
  initialData?: MunicipalEvidenceResponse | null
  showCoverage?: boolean
}

export default function MunicipalEvidence(props: MunicipalEvidenceProps) {
  const contextKey = `${props.pidn ?? ''}:${props.municipality ?? ''}`
  return <MunicipalEvidenceContent key={contextKey} {...props} />
}

function MunicipalEvidenceContent({
  municipality,
  pidn,
  initialData,
  showCoverage = true,
}: MunicipalEvidenceProps) {
  const [limit, setLimit] = useState(INITIAL_LIMIT)
  const openSource = useSourceViewer()
  const url = pidn
    ? `/api/parcels/${encodeURIComponent(pidn)}/evidence?limit=${limit}`
    : municipality
      ? `/api/municipalities/${encodeURIComponent(municipality)}/evidence?limit=${limit}`
      : null
  const { data, error, loading, reload } = useFetchJson<MunicipalEvidenceResponse>(url)
  const evidence = error ? null : (data ?? initialData)

  return (
    <section className="municipal-evidence" aria-label="Municipal records">
      {showCoverage && evidence?.coverage && <CoverageSummary coverage={evidence.coverage} />}
      {loading && !evidence && (
        <p className="municipal-evidence-status">Loading municipal records…</p>
      )}
      {error && (
        <div className="municipal-evidence-status" role="status">
          <span>Municipal records could not be loaded.</span>
          <button type="button" onClick={reload}>
            Retry
          </button>
        </div>
      )}
      {!loading && !error && evidence?.cards.length === 0 && (
        <p className="municipal-evidence-status">
          No matching passages are available in the reviewed records. Coverage may be incomplete.
        </p>
      )}
      <div className="municipal-evidence-list">
        {evidence?.cards.map((card) => {
          const sources = municipalCardSources(card)
          return (
            <article className="municipal-evidence-card" key={card.id}>
              <div className="municipal-evidence-meta">
                {card.body_name} · {formatShortDate(card.meeting_date)} ·{' '}
                {card.proceeding_type === 'agenda'
                  ? 'Agenda'
                  : card.proceeding_type === 'minutes'
                    ? 'Minutes'
                    : 'Record'}
              </div>
              {card.explanation ? (
                <SourceExplanation
                  explanation={{ ...card.explanation, citation_evidence: sources }}
                  headingLevel="h3"
                />
              ) : (
                <>
                  <h3>{card.title}</h3>
                  <blockquote className="municipal-evidence-preview">
                    {card.passages[0]?.text}
                  </blockquote>
                  {card.proceeding_type === 'agenda' && (
                    <p className="municipal-evidence-status">
                      Agenda item · outcome not established
                    </p>
                  )}
                </>
              )}
              {card.matched_properties.some((property) => property.pidn !== pidn) && (
                <div className="municipal-evidence-properties">
                  {card.matched_properties
                    .filter((property) => property.pidn !== pidn)
                    .map((property) => (
                      <Link
                        key={property.pidn}
                        to={`/property/${encodeURIComponent(property.pidn)}`}
                      >
                        {property.address ?? property.pidn}
                      </Link>
                    ))}
                </div>
              )}
              <button
                className="source-catalog-button"
                type="button"
                onClick={() => openSource(sources)}
              >
                View source{sources.length > 1 ? 's' : ''}
              </button>
            </article>
          )
        })}
      </div>
      {evidence?.more && limit < 100 && (
        <button
          className="ciq-button"
          type="button"
          onClick={() => setLimit(Math.min(limit + INITIAL_LIMIT, 100))}
        >
          Show more records
        </button>
      )}
    </section>
  )
}
