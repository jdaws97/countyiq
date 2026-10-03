import { Link, useSearchParams } from 'react-router-dom'
import { Button, ButtonLink, EmptyState } from '../ui'
import { formatShortDate } from '../../lib/format'
import { openSiteQuestionCount, SITE_STAGE_LABELS } from '../../lib/siteInquiries'
import type { SiteInquiry } from '../../types/siteIntake'

export default function InquiryList({ items }: { items: SiteInquiry[] }) {
  const [params, setParams] = useSearchParams()
  const query = params.get('q') ?? ''
  const requestedStage = params.get('stage') ?? 'all'
  const stage = Object.hasOwn(SITE_STAGE_LABELS, requestedStage) ? requestedStage : 'all'
  const search = query.trim().toLocaleLowerCase()
  const matches = items
    .filter((item) => {
      const matchesStage = stage === 'all' || stage === item.status
      const matchesSearch = `${item.label} ${item.pidn}`.toLocaleLowerCase().includes(search)
      return matchesStage && matchesSearch
    })
    .sort((left, right) => Date.parse(right.updated_at) - Date.parse(left.updated_at))

  function updateFilters(nextQuery: string, nextStage: string) {
    const next = new URLSearchParams()
    if (nextQuery) {
      next.set('q', nextQuery)
    }
    if (nextStage !== 'all') {
      next.set('stage', nextStage)
    }
    setParams(next, { replace: true, preventScrollReset: true })
  }

  if (!items.length) {
    return (
      <section className="site-welcome" aria-labelledby="site-welcome-heading">
        <div>
          <div className="page-eyebrow">Your first inquiry</div>
          <h2 id="site-welcome-heading">Start with a place. Keep the questions together.</h2>
          <p>
            Find the candidate property, add the client’s brief, and review the public records
            before your first municipal conversation.
          </p>
          <ButtonLink tone="primary" to="/sites/new">
            Find a property
          </ButtonLink>
        </div>
        <ol className="site-welcome-steps">
          <li>
            <strong>Confirm the site</strong>
            <span>Check the parcel, boundary and reviewing authority.</span>
          </li>
          <li>
            <strong>Review the evidence</strong>
            <span>Keep mapped facts separate from your assessment.</span>
          </li>
          <li>
            <strong>Prepare the conversation</strong>
            <span>Save open questions and a cited handoff.</span>
          </li>
        </ol>
      </section>
    )
  }

  return (
    <section className="site-inquiry-workspace" aria-labelledby="saved-sites-heading">
      <div className="site-section-title">
        <div>
          <h2 id="saved-sites-heading">Your inquiries</h2>
          <p className="site-muted">
            Resume your saved work. Current evidence is checked when you open an inquiry.
          </p>
        </div>
        <span className="site-count-label">{items.length} saved</span>
      </div>
      <div className="site-list-filters">
        <label>
          Find an inquiry
          <input
            type="search"
            value={query}
            onChange={(event) => updateFilters(event.target.value, stage)}
            placeholder="Search by inquiry name or parcel ID"
          />
        </label>
        <label>
          Saved stage
          <select value={stage} onChange={(event) => updateFilters(query, event.target.value)}>
            <option value="all">All stages</option>
            {Object.entries(SITE_STAGE_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <p className="site-list-result-count" role="status">
        {matches.length} of {items.length} inquiries
      </p>
      {matches.length ? (
        <div className="site-inquiry-list">
          {matches.map((item) => {
            const openQuestions = openSiteQuestionCount(item)
            return (
              <Link className="site-inquiry-card" to={`/sites/${item.id}`} key={item.id}>
                <div className="site-card-heading">
                  <span className={`site-stage site-stage-${item.status}`}>
                    {SITE_STAGE_LABELS[item.status]}
                  </span>
                  <span className="site-card-date">Saved {formatShortDate(item.updated_at)}</span>
                </div>
                <h3>{item.label}</h3>
                <p className="site-card-brief">
                  {item.proposed_use || 'Add the client’s proposed use.'}
                </p>
                <span className="site-card-parcel">Parcel {item.pidn}</span>
                <div className="site-card-footer">
                  <span>
                    {openQuestions === 0
                      ? 'All question responses recorded'
                      : `${openQuestions} questions still open`}
                  </span>
                  <span className="site-card-continue">
                    Continue <span aria-hidden="true">→</span>
                  </span>
                </div>
              </Link>
            )
          })}
        </div>
      ) : (
        <EmptyState
          title="No inquiries match"
          actions={<Button onClick={() => updateFilters('', 'all')}>Clear filters</Button>}
        >
          Try another inquiry name, parcel ID or saved stage.
        </EmptyState>
      )}
    </section>
  )
}
