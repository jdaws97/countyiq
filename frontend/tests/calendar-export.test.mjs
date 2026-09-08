import assert from 'node:assert/strict'
import { after, test } from 'node:test'
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import ts from 'typescript'

const directory = mkdtempSync(join(tmpdir(), 'countyiq-calendar-export-'))
const source = readFileSync(new URL('../src/lib/calendarExport.ts', import.meta.url), 'utf8')
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 },
})
const modulePath = join(directory, 'calendarExport.mjs')
writeFileSync(modulePath, outputText)
const { buildCalendarReminder, canExportCalendarReminder } = await import(pathToFileURL(modulePath))
after(() => rmSync(directory, { recursive: true, force: true }))

const now = new Date(2026, 8, 8)
const sourceItem = {
  evidence_id: 'evidence-1',
  document_url: 'https://borough.example.test/agenda.pdf',
  url: null,
}
const event = {
  event_key: 'development:rezoning-12',
  title: 'North tract rezoning',
  municipality: 'York Township',
}

function unfold(ics) {
  return ics.replace(/\r\n /g, '')
}

test('exports a source-backed proposed date as an all-day calendar reminder', () => {
  const date = {
    date: '2026-09-08',
    time: '7:00 PM',
    label: 'Planning Commission hearing',
    status: 'proposed',
    quote: 'The hearing is proposed for September 8.',
    source_id: 'source-1',
  }
  const ics = buildCalendarReminder(event, date, sourceItem, now)

  assert.ok(ics)
  const unfolded = unfold(ics)
  assert.match(unfolded, /DTSTART;VALUE=DATE:20260908\r\n/)
  assert.match(unfolded, /SUMMARY:Proposed: Planning Commission hearing/)
  assert.match(unfolded, /Stated local time: 7:00 PM/)
  assert.match(unfolded, /Supporting quote: The hearing is proposed for September 8\./)
  assert.match(unfolded, /URL:https:\/\/borough\.example\.test\/agenda\.pdf/)
  assert.match(unfolded, /UID:[0-9a-f]{8}@countyiq\.local/)
  assert.equal(unfolded.includes('DTEND'), false)
})

test('does not export historical, vague, or unsupported dates', () => {
  const base = {
    time: null,
    label: 'Meeting',
    status: 'scheduled',
    quote: 'The meeting is scheduled.',
    source_id: 'source-1',
  }

  assert.equal(canExportCalendarReminder({ ...base, date: '2026-09-07' }, sourceItem, now), false)
  assert.equal(canExportCalendarReminder({ ...base, date: 'Fall 2026' }, sourceItem, now), false)
  assert.equal(
    canExportCalendarReminder(
      { ...base, date: '2026-09-09', status: 'historical' },
      sourceItem,
      now,
    ),
    false,
  )
  assert.equal(canExportCalendarReminder({ ...base, date: '2026-09-09' }, null, now), false)
  assert.equal(
    canExportCalendarReminder(
      { ...base, date: '2026-09-09' },
      { ...sourceItem, document_url: 'javascript:alert(1)' },
      now,
    ),
    false,
  )
})

test('escapes and folds untrusted calendar text', () => {
  const date = {
    date: '2026-09-09',
    time: null,
    label: 'Plan, phase; one',
    status: 'expected',
    quote: `Line one, with; punctuation and a slash \\ plus\n${'evidence '.repeat(20)}`,
    source_id: 'source-1',
  }
  const ics = buildCalendarReminder(
    { ...event, title: 'A title, with; punctuation' },
    date,
    sourceItem,
    now,
  )

  assert.ok(ics)
  assert.match(ics, /Plan\\, phase\\; one/)
  assert.match(ics, /A title\\, with\\; punctuation/)
  assert.match(ics, /slash \\\\ plus\\n/)
  assert.ok(
    ics
      .split('\r\n')
      .filter(Boolean)
      .every((line) => Buffer.byteLength(line) <= 75),
  )
})
