import type { EvidenceItem, IntelligenceEvent, RecordDate } from '../types/api'

const CALENDAR_STATUSES = new Set(['proposed', 'scheduled', 'expected', 'deadline'])

function calendarDate(value: string | null): string | null {
  if (!value) {
    return null
  }

  const iso = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value.trim())
  if (!iso) {
    return null
  }

  const year = Number(iso[1])
  const month = Number(iso[2]) - 1
  const day = Number(iso[3])
  const parsed = new Date(year, month, day)
  if (parsed.getFullYear() !== year || parsed.getMonth() !== month || parsed.getDate() !== day) {
    return null
  }

  return `${iso[1]}${iso[2]}${iso[3]}`
}

function safeOriginalSourceUrl(source: EvidenceItem | null | undefined): string | null {
  const candidate = source?.document_url ?? source?.url
  if (!candidate) {
    return null
  }

  try {
    const parsed = new URL(candidate)
    return ['https:', 'http:'].includes(parsed.protocol) && !parsed.username && !parsed.password
      ? parsed.href
      : null
  } catch {
    return null
  }
}

function escapeText(value: string): string {
  return value
    .replace(/\\/g, '\\\\')
    .replace(/;/g, '\\;')
    .replace(/,/g, '\\,')
    .replace(/\r\n|\r|\n/g, '\\n')
}

function foldLine(line: string): string[] {
  const lines: string[] = []
  let current = ''
  let currentBytes = 0
  let limit = 75

  for (const character of line) {
    const bytes = new TextEncoder().encode(character).length
    if (current && currentBytes + bytes > limit) {
      lines.push(current)
      current = ' '
      currentBytes = 1
      limit = 75
    }
    current += character
    currentBytes += bytes
  }
  lines.push(current)
  return lines
}

function stableHash(value: string): string {
  let hash = 0x811c9dc5
  for (const character of value) {
    hash ^= character.codePointAt(0) ?? 0
    hash = Math.imul(hash, 0x01000193)
  }
  return (hash >>> 0).toString(16).padStart(8, '0')
}

function isTodayOrFuture(compactDate: string, now: Date): boolean {
  const today = [
    now.getFullYear(),
    String(now.getMonth() + 1).padStart(2, '0'),
    String(now.getDate()).padStart(2, '0'),
  ].join('')
  return compactDate >= today
}

export function canExportCalendarReminder(
  date: RecordDate,
  source: EvidenceItem | null | undefined,
  now = new Date(),
): boolean {
  const exactDate = calendarDate(date.date)
  return Boolean(
    exactDate &&
    CALENDAR_STATUSES.has(date.status) &&
    typeof date.quote === 'string' &&
    date.quote.trim() &&
    safeOriginalSourceUrl(source) &&
    isTodayOrFuture(exactDate, now),
  )
}

export function buildCalendarReminder(
  event: IntelligenceEvent,
  date: RecordDate,
  source: EvidenceItem,
  now = new Date(),
): string | null {
  const exactDate = calendarDate(date.date)
  const sourceUrl = safeOriginalSourceUrl(source)
  if (!exactDate || !sourceUrl || !canExportCalendarReminder(date, source, now)) {
    return null
  }

  const status = date.status[0].toUpperCase() + date.status.slice(1)
  const quoteLabel =
    source.details?.translated === true
      ? 'English translation of supporting passage'
      : 'Supporting quote'
  const description = [
    'CountyIQ calendar reminder from a public record.',
    `Status: ${status} (stated in source; outcome unverified)`,
    `Matter: ${event.title}`,
    `Municipality: ${event.municipality ?? 'Not stated'}`,
    `Stated date: ${date.date}`,
    ...(date.time ? [`Stated local time: ${date.time}`] : []),
    `${quoteLabel}: ${date.quote}`,
    `Original source: ${sourceUrl}`,
  ].join('\n')
  const uid = `${stableHash(`${event.event_key}|${date.source_id}|${date.date}|${date.label}`)}@countyiq.local`
  const lines = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//CountyIQ//Record Calendar Reminder//EN',
    'CALSCALE:GREGORIAN',
    'METHOD:PUBLISH',
    'BEGIN:VEVENT',
    `UID:${uid}`,
    `DTSTAMP:${now
      .toISOString()
      .replace(/[-:]/g, '')
      .replace(/\.\d{3}Z$/, 'Z')}`,
    `DTSTART;VALUE=DATE:${exactDate}`,
    `SUMMARY:${escapeText(`${status}: ${date.label} — ${event.title}`)}`,
    `DESCRIPTION:${escapeText(description)}`,
    `URL:${sourceUrl}`,
    'END:VEVENT',
    'END:VCALENDAR',
  ]

  return lines.flatMap(foldLine).join('\r\n') + '\r\n'
}

export function downloadCalendarReminder(ics: string, filename: string): void {
  const url = URL.createObjectURL(new Blob([ics], { type: 'text/calendar;charset=utf-8' }))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}
