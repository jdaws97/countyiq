import type { EvidenceItem, IntelligenceEvent, RecordDate } from '../types/api'
import {
  buildCalendarReminder,
  canExportCalendarReminder,
  downloadCalendarReminder,
} from '../lib/calendarExport'

export default function CalendarDateAction({
  event,
  date,
  source,
}: {
  event: IntelligenceEvent
  date: RecordDate
  source?: EvidenceItem | null
}) {
  if (!canExportCalendarReminder(date, source)) {
    return null
  }

  const download = () => {
    if (!source) {
      return
    }
    const ics = buildCalendarReminder(event, date, source)
    if (!ics) {
      return
    }
    downloadCalendarReminder(ics, `countyiq-${date.date}-${date.source_id}.ics`)
  }

  return (
    <button
      className="source-catalog-button"
      type="button"
      title="Download calendar reminder for this stated date"
      aria-label={`Download calendar reminder for ${date.label}`}
      onClick={download}
    >
      Add to calendar
    </button>
  )
}
