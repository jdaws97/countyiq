import { Link } from 'react-router-dom'
import { upcomingActivityDates } from '../lib/activityDates'
import { describeRecordDate } from '../lib/recordDates'
import { useSourceViewer } from '../lib/useSourceViewer'
import type { IntelligenceEvent } from '../types/api'
import CalendarDateAction from './CalendarDateAction'

export default function UpcomingDates({ events }: { events: IntelligenceEvent[] }) {
  const openSource = useSourceViewer()
  const dates = upcomingActivityDates(events).slice(0, 3)
  if (!dates.length) {
    return null
  }
  return (
    <section className="upcoming-dates" aria-labelledby="upcoming-dates-heading">
      <h2 id="upcoming-dates-heading">Dates to follow</h2>
      <p className="activity-scope-note">
        Upcoming dates stated in these results. Proposed dates still need confirmation.
      </p>
      <div className="upcoming-dates-list">
        {dates.map(({ event, date, source }) => (
          <article key={`${event.event_key}-${date.date}-${date.label}`}>
            <strong>{describeRecordDate(date)}</strong>
            <span>{event.title}</span>
            <div>
              {source && (
                <button className="source-catalog-button" onClick={() => openSource([source])}>
                  View source
                </button>
              )}
              <CalendarDateAction event={event} date={date} source={source} />
              {event.related_pidns.length === 1 && (
                <Link to={`/property/${encodeURIComponent(event.related_pidns[0])}`}>
                  Open property
                </Link>
              )}
              {event.project && (
                <Link to={`/project/${encodeURIComponent(event.project.key)}`}>Open project</Link>
              )}
            </div>
          </article>
        ))}
      </div>
    </section>
  )
}
