import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useIntelligenceWorkspace } from '../lib/intelligenceWorkspace'
import { useFetchJson } from '../lib/useFetchJson'
import { WORK_LABELS, workNeedsReview } from '../lib/intelligenceFlow'
import { CitedText } from './EvidencePanel'
import IntelligenceDecision from './IntelligenceDecision'
import type { EmergingResponse } from '../types/emerging'

export default function IntelligenceSavedWork({ fullPage = false }: { fullPage?: boolean }) {
  const { work, removeCase } = useIntelligenceWorkspace()
  const [filter, setFilter] = useState('active')
  const params = new URLSearchParams({ limit: '100' })
  for (const item of work) {
    params.append('case_key', item.case_key)
  }
  const { data, loading, error, reload } = useFetchJson<EmergingResponse>(
    work.length ? `/api/intelligence?${params}` : null,
  )
  useEffect(() => {
    window.addEventListener('focus', reload)
    return () => window.removeEventListener('focus', reload)
  }, [reload])
  if (!work.length) {
    return fullPage ? (
      <section>
        <h2>Start with a case that matters to you</h2>
        <p>
          Pursue an active investigation, follow a case for later, or dismiss it. Your decisions and
          notes will appear here.
        </p>
        <Link to="/intelligence?view=all">Explore cases →</Link>
      </section>
    ) : null
  }
  const selected = work
    .filter((item) => {
      const current = data?.cases.find((candidate) => candidate.case_key === item.case_key)
      if (filter === 'updates') {
        return Boolean(data) && workNeedsReview(item, current)
      }
      if (filter === 'active') {
        return item.status !== 'rejected'
      }
      return item.status === filter
    })
    .sort((left, right) => {
      const leftCurrent = data?.cases.find((item) => item.case_key === left.case_key)
      const rightCurrent = data?.cases.find((item) => item.case_key === right.case_key)
      return (
        Number(workNeedsReview(right, rightCurrent)) - Number(workNeedsReview(left, leftCurrent))
      )
    })
  return (
    <section className="emerging-page" aria-label="My intelligence cases">
      <h2>My work</h2>
      <p className="emerging-scope">
        Your cases and decisions. Updated cases appear first when you return.
      </p>
      <div className="intelligence-views" aria-label="Filter my work">
        {[
          ['active', 'Active'],
          ['updates', 'Needs review'],
          ['qualifying', 'Pursuing'],
          ['waiting', 'Following'],
          ['rejected', 'Dismissed'],
        ].map(([value, label]) => (
          <button key={value} aria-pressed={filter === value} onClick={() => setFilter(value)}>
            {label}
          </button>
        ))}
        <button onClick={reload}>Check for updates</button>
      </div>
      {loading && <p>Checking your saved cases against current evidence…</p>}
      {error && <p>Your saved notes are kept. Current cases could not be checked.</p>}
      <div className="emerging-list">
        {selected.map((item) => {
          const current = data?.cases.find((candidate) => candidate.case_key === item.case_key)
          return (
            <article className="emerging-case-card" key={item.case_key}>
              <h3>
                <Link to={`/intelligence/${item.case_key}`}>
                  {current?.title ?? 'Saved case awaiting current evidence'}
                </Link>
              </h3>
              <p>
                {WORK_LABELS[item.status]}
                {current && current.revision !== item.last_seen_revision
                  ? ' · Revised since your last review'
                  : ''}
              </p>
              {current && current.revision !== item.last_seen_revision && (
                <div className="emerging-change">
                  <p>
                    <strong>Current stage:</strong>{' '}
                    <CitedText text={current.stage} evidence={current.citation_evidence} />
                  </p>
                  <p>
                    {current.opportunities.length
                      ? 'Commercial possibilities are available for review in the current case.'
                      : 'No qualified commercial action is established in the current case.'}
                  </p>
                  <Link to={`/intelligence/${item.case_key}`}>Review current evidence →</Link>
                </div>
              )}
              {item.note && <p>{item.note}</p>}
              {!loading && !error && !current && (
                <p>This case needs reassessment or has been withdrawn.</p>
              )}
              {current && <IntelligenceDecision item={current} />}
              <button className="ciq-button" onClick={() => removeCase(item.case_key)}>
                Remove saved case
              </button>
            </article>
          )
        })}
      </div>
      {!loading && !error && !selected.length && <p>No cases in this view.</p>}
    </section>
  )
}
