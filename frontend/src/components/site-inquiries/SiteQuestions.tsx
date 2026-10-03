import { siteReviewTopics } from '../../lib/sitePacket'
import { SITE_QUESTION_KEYS } from '../../lib/siteInquiries'
import type { SiteInquiry, SiteIntakePacket, SiteQuestionReview } from '../../types/siteIntake'

const TOPIC_LABELS = {
  identity: 'Boundary & authority',
  zoning: 'Proposed use & zoning',
  site_conditions: 'Site conditions',
  utilities_access: 'Utilities & access',
  municipal_history: 'Municipal record',
}

type Props = {
  inquiry: SiteInquiry
  packet: SiteIntakePacket | null
  onChange: (reviews: SiteQuestionReview[]) => void
}

export default function SiteQuestions({ inquiry, packet, onChange }: Props) {
  const topics = packet ? siteReviewTopics(packet) : []
  const reviews = inquiry.question_reviews ?? []
  function update(key: SiteQuestionReview['key'], change: Partial<SiteQuestionReview>) {
    const previous: SiteQuestionReview = reviews.find((review) => review.key === key) ?? {
      key,
      status: 'open',
      note: '',
    }
    onChange([...reviews.filter((review) => review.key !== key), { ...previous, ...change }])
  }
  return (
    <div className="site-question-list">
      {SITE_QUESTION_KEYS.map((key, index) => {
        const topic = topics.find((item) => item.key === key)
        const review = reviews.find((item) => item.key === key)
        const status = review?.status ?? 'open'
        return (
          <article key={key} className="site-question" aria-labelledby={`site-question-${key}`}>
            <div className="site-question-number" aria-hidden="true">
              {index + 1}
            </div>
            <div>
              <h3 id={`site-question-${key}`}>{TOPIC_LABELS[key]}</h3>
              {topic && <p>{topic.question}</p>}
              <div className="site-question-inputs">
                <label>
                  Your progress
                  <select
                    value={status}
                    onChange={(event) =>
                      update(key, {
                        status: event.target.value as SiteQuestionReview['status'],
                      })
                    }
                  >
                    <option value="open">Still open</option>
                    <option value="answered">Answer recorded</option>
                    <option value="not_applicable">Does not apply</option>
                  </select>
                </label>
                <label>
                  Your response or next step
                  <textarea
                    value={review?.note ?? ''}
                    maxLength={1500}
                    rows={2}
                    onChange={(event) => update(key, { note: event.target.value })}
                    placeholder="Who confirmed what, when, and where can it be checked?"
                  />
                  {status !== 'open' && !review?.note.trim() && (
                    <span className="site-field-note">Add an explanation before saving.</span>
                  )}
                </label>
              </div>
            </div>
          </article>
        )
      })}
    </div>
  )
}
