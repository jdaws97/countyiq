import { recordDateTimestamp } from './recordDates'
import type { EvidenceItem, IntelligenceEvent, RecordDate } from '../types/api'

export interface UpcomingActivityDate {
  event: IntelligenceEvent
  date: RecordDate
  source: EvidenceItem | null
}

export function upcomingActivityDates(
  events: IntelligenceEvent[],
  now = new Date(),
): UpcomingActivityDate[] {
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const values = new Map<string, UpcomingActivityDate>()
  for (const event of events) {
    for (const source of event.sources) {
      const dates = source.details?.record_dates
      if (!Array.isArray(dates)) {
        continue
      }
      for (const value of dates) {
        if (
          !value ||
          typeof value !== 'object' ||
          typeof value.date !== 'string' ||
          typeof value.label !== 'string'
        ) {
          continue
        }
        if (!['proposed', 'scheduled', 'expected', 'deadline'].includes(value.status)) {
          continue
        }
        const timestamp = recordDateTimestamp(value.date)
        if (timestamp == null || timestamp < today) {
          continue
        }
        const key = `${event.event_key}:${value.date}:${value.time ?? ''}:${value.label}:${value.status}`
        const citedSource = event.sources.find(
          (item) =>
            item.citation_key.toLowerCase() === `evidence:source:${value.source_id}`.toLowerCase(),
        )
        values.set(key, { event, date: value as RecordDate, source: citedSource ?? null })
      }
    }
  }
  return [...values.values()].sort(
    (a, b) => (recordDateTimestamp(a.date.date) ?? 0) - (recordDateTimestamp(b.date.date) ?? 0),
  )
}
