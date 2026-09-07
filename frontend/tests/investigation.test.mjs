import assert from 'node:assert/strict'
import { after, test } from 'node:test'
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import ts from 'typescript'

const directory = mkdtempSync(join(tmpdir(), 'countyiq-investigation-'))
const source = readFileSync(new URL('../src/lib/investigation.ts', import.meta.url), 'utf8')
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 },
})
const modulePath = join(directory, 'investigation.mjs')
writeFileSync(modulePath, outputText)
const { investigationDetails, supportingSource } = await import(pathToFileURL(modulePath))
after(() => rmSync(directory, { recursive: true, force: true }))

test('an explanation retains conditions and milestones from the underlying proceeding', () => {
  const date = { date: '2026-09-08', label: 'Hearing', status: 'proposed', source_id: 'P1' }
  const conditionSource = { details: { supports: ['condition:0'] } }
  const event = {
    sources: [
      {
        details: {
          explanation_version: 1,
          explanation_next_step: 'Check the minutes.',
          record_dates: [date],
        },
      },
      {
        details: {
          contract_version: 3,
          conditions: ['Resolve stormwater comments.'],
          milestones: [{ text: 'Return to the board.' }],
        },
      },
      conditionSource,
    ],
  }
  assert.deepEqual(investigationDetails(event), {
    dates: [date],
    nextStep: 'Check the minutes.',
    conditions: [{ text: 'Resolve stormwater comments.', index: 0 }],
    milestones: [{ text: 'Return to the board.', index: 0, kind: null }],
  })
  assert.equal(supportingSource(event, 'condition:0'), conditionSource)
  assert.equal(supportingSource(event, 'condition:1'), undefined)
})

test('records without an explanation retain their stated dates without inventing a next check', () => {
  const date = { date: null, label: 'Hearing date not set', status: 'unknown', source_id: 'P1' }
  assert.deepEqual(
    investigationDetails({
      sources: [{ details: { contract_version: 2, record_dates: [date, null, 'invalid'] } }],
    }),
    {
      dates: [date],
      nextStep: null,
      conditions: [],
      milestones: [],
    },
  )
  assert.deepEqual(investigationDetails({ sources: [] }), {
    dates: [],
    nextStep: null,
    conditions: [],
    milestones: [],
  })
})

test('filtered malformed facts keep original source positions', () => {
  const source = { details: { supports: ['condition:2', 'milestone:1'] } }
  const event = {
    sources: [
      {
        details: {
          contract_version: 3,
          conditions: [null, '', 'Resolve access.'],
          milestones: [false, { text: 'Submit revision.', kind: 'deadline' }],
        },
      },
      source,
    ],
  }
  const result = investigationDetails(event)
  assert.deepEqual(result.conditions, [{ text: 'Resolve access.', index: 2 }])
  assert.deepEqual(result.milestones, [{ text: 'Submit revision.', index: 1, kind: 'deadline' }])
  assert.equal(supportingSource(event, `condition:${result.conditions[0].index}`), source)
  assert.equal(supportingSource(event, `milestone:${result.milestones[0].index}`), source)
})
