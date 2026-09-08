import { CitedText } from './EvidencePanel'
import { describeRecordDate } from '../lib/recordDates'
import { formatLabel } from '../lib/format'
import type { SourceExplanationData } from '../types/api'
import './SourceExplanation.css'

export default function SourceExplanation({
  explanation,
  headingLevel = 'h2',
  showHeading = true,
}: {
  explanation: SourceExplanationData
  headingLevel?: 'h2' | 'h3'
  showHeading?: boolean
}) {
  const Heading = headingLevel
  const dates = explanation.record?.dates.slice(0, 3) ?? []

  return (
    <section className="source-explanation" aria-label="What the records say">
      {showHeading && <Heading>{explanation.headline}</Heading>}
      <p className="source-explanation-summary">
        <CitedText text={explanation.summary} evidence={explanation.citation_evidence} />
      </p>
      {explanation.next_step && (
        <p className="source-explanation-next-step">
          <strong>Next step:</strong>{' '}
          <CitedText text={explanation.next_step} evidence={explanation.citation_evidence} />
        </p>
      )}
      {(explanation.record?.record_status || explanation.record?.matter_category) && (
        <div className="source-explanation-meta">
          {explanation.record?.record_status && (
            <span>{formatLabel(explanation.record.record_status)}</span>
          )}
          {explanation.record?.matter_category && (
            <span>{formatLabel(explanation.record.matter_category)}</span>
          )}
          {explanation.record?.decision_scope && (
            <span>{formatLabel(explanation.record.decision_scope)}</span>
          )}
        </div>
      )}
      {dates.length > 0 && (
        <div className="source-explanation-dates" aria-label="Dates stated in the source">
          {dates.map((recordDate, index) => (
            <div key={`${recordDate.source_id}-${recordDate.label}-${index}`}>
              <CitedText
                text={`${describeRecordDate(recordDate)} [Evidence:source:${recordDate.source_id}]`}
                evidence={explanation.citation_evidence}
              />
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
