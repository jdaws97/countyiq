import { formatShortDate } from './format'
import type { RecordDate } from '../types/api'

const MONTHS: Record<string, number> = {
  JAN: 0,
  FEB: 1,
  MAR: 2,
  APR: 3,
  MAY: 4,
  JUN: 5,
  JUL: 6,
  AUG: 7,
  SEP: 8,
  OCT: 9,
  NOV: 10,
  DEC: 11,
}

export function recordDateTimestamp(value: string | null | undefined): number | null {
  if (!value) {
    return null
  }

  const countyDate = /^(\d{1,2})-([A-Za-z]{3})-(\d{4})$/.exec(value.trim())
  if (countyDate) {
    const month = MONTHS[countyDate[2].toUpperCase()]
    const day = Number(countyDate[1])
    const year = Number(countyDate[3])
    const parsed = new Date(year, month, day)
    return month != null && parsed.getMonth() === month && parsed.getDate() === day
      ? parsed.getTime()
      : null
  }

  const isoDate = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value.trim())
  if (isoDate) {
    const year = Number(isoDate[1])
    const month = Number(isoDate[2]) - 1
    const day = Number(isoDate[3])
    const parsed = new Date(year, month, day)
    return parsed.getMonth() === month && parsed.getDate() === day ? parsed.getTime() : null
  }

  const parsed = new Date(value).getTime()
  return Number.isNaN(parsed) ? null : parsed
}

export function describeRecordDate(recordDate: RecordDate, now = new Date()): string {
  const formatted = formatShortDate(recordDate.date) ?? recordDate.date ?? 'Date unavailable'
  const time = recordDate.time ? ` at ${recordDate.time}` : ''
  const timestamp = recordDateTimestamp(recordDate.date)
  const isPast =
    timestamp != null &&
    timestamp < new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const status = recordDate.status === 'historical' ? 'Recorded' : recordDate.status

  if (isPast && ['proposed', 'scheduled', 'expected'].includes(recordDate.status)) {
    return `${recordDate.label}: ${formatted}${time} · ${status} date passed; outcome unverified`
  }
  return `${recordDate.label}: ${formatted}${time} · ${status}`
}
