import { Link } from 'react-router-dom'
import { CitedText } from './EvidencePanel'
import { formatShortDate } from '../lib/format'
import type { EvidenceItem, RecordBrief as RecordBriefData } from '../types/api'
import './RecordBrief.css'

const MAX_VISIBLE_FINDINGS = 4
const MAX_VISIBLE_QUESTIONS = 3

type FindingCategory = RecordBriefData['findings'][number]['category']

const categoryLabels: Record<FindingCategory, string> = {
  activity: 'Activity',
  constraint: 'Constraint',
  context: 'Context',
}

export default function RecordBrief({
  brief,
  evidence,
}: {
  brief: RecordBriefData
  evidence: EvidenceItem[]
}) {
  const findings = brief.findings.slice(0, MAX_VISIBLE_FINDINGS)
  const questions = brief.questions.slice(0, MAX_VISIBLE_QUESTIONS)
  const hasMoreSignals = brief.signal_count > findings.length

  return (
    <section className="record-brief" aria-labelledby="record-brief-heading">
      <div className="record-brief-heading">
        <div>
          <div className="record-brief-eyebrow">Record summary</div>
          <h2 id="record-brief-heading">{brief.headline}</h2>
        </div>
        {brief.source_updated_at && (
          <div className="record-brief-date">
            Record snapshot {formatShortDate(brief.source_updated_at)}
          </div>
        )}
      </div>

      {findings.length > 0 && (
        <div className="record-brief-findings" aria-label="Source findings">
          {findings.map((finding) => (
            <article className="record-brief-finding" key={finding.signal_key}>
              <div className={`record-brief-category record-brief-category-${finding.category}`}>
                {categoryLabels[finding.category]}
              </div>
              <h3>{finding.title}</h3>
              <p>
                <CitedText text={finding.text} evidence={evidence} />
              </p>
              {finding.caveat && <div className="record-brief-caveat">{finding.caveat}</div>}
            </article>
          ))}
        </div>
      )}

      {(questions.length > 0 || hasMoreSignals) && (
        <div className="record-brief-footer">
          {questions.length > 0 && (
            <div className="record-brief-questions">
              <h3>Questions to resolve</h3>
              <ul>
                {questions.map((question) => (
                  <li key={question}>
                    <CitedText text={question} evidence={evidence} />
                  </li>
                ))}
              </ul>
            </div>
          )}
          {hasMoreSignals && (
            <Link
              className="record-brief-signals-link"
              to="?view=records#property-signals"
              onClick={() => {
                const signals = document.getElementById('property-signals')
                if (signals instanceof HTMLDetailsElement) {
                  signals.open = true
                }
              }}
            >
              Review all {brief.signal_count} signals
            </Link>
          )}
        </div>
      )}
    </section>
  )
}
