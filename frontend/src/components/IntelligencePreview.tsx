import { Link } from 'react-router-dom'

import { useFetchJson } from '../lib/useFetchJson'
import { useIntelligenceWorkspace } from '../lib/intelligenceWorkspace'
import { caseFit, profileQuery } from '../lib/intelligenceFlow'
import type { EmergingResponse } from '../types/emerging'

import './ActivityPreview.css'
import '../pages/EmergingIntelligence.css'

export default function IntelligencePreview() {
  const { profile, work } = useIntelligenceWorkspace()
  const params = profileQuery(profile)
  params.set('limit', '3')
  for (const item of work.filter((entry) => entry.status === 'rejected')) {
    params.append('exclude_case_key', item.case_key)
  }
  const { data, loading, error, reload } = useFetchJson<EmergingResponse>(
    `/api/intelligence?${params}`,
  )

  return (
    <section className="intelligence-preview" aria-labelledby="emerging-preview-heading">
      <div className="activity-preview-heading">
        <h2 id="emerging-preview-heading">Cases for your work</h2>
        <Link to="/intelligence">Explore cases →</Link>
      </div>
      <p className="activity-scope-note">
        Cases matched to your work criteria. Open one to review its relevance, then pursue, follow
        or dismiss it.
      </p>
      {loading && <p role="status">Loading emerging intelligence…</p>}
      {error && (
        <p role="alert">
          Emerging intelligence could not be loaded.{' '}
          <button type="button" className="source-catalog-button" onClick={reload}>
            Try again
          </button>
        </p>
      )}
      {!loading && !error && data?.cases.length === 0 && (
        <p>
          No current cases match your work criteria.{' '}
          <Link to="/intelligence?view=all">Explore all cases</Link> or{' '}
          <Link to="/intelligence?edit_profile=1">edit your criteria</Link>.
        </p>
      )}
      <div className="intelligence-preview-list">
        {data?.cases.map((item) => (
          <article key={item.case_key} className="intelligence-preview-card">
            <p>{formatLabel(item.family)}</p>
            <h3>
              <Link to={`/intelligence/${encodeURIComponent(item.case_key)}`}>{item.title}</Link>
            </h3>
            <span>{formatLabel(item.evidence_strength)} evidence</span>
            <p>{caseFit(item, profile)}</p>
          </article>
        ))}
      </div>
    </section>
  )
}

function formatLabel(value: string) {
  return value.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
}
