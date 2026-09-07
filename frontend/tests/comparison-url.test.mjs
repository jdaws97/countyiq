import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'

const source = readFileSync(new URL('../src/lib/comparisonUrl.ts', import.meta.url), 'utf8')
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 },
})
const comparison = await import(
  'data:text/javascript;base64,' + Buffer.from(outputText).toString('base64')
)

test('comparison links preserve two to four validated parcel identifiers in order', () => {
  const url = comparison.comparisonUrl(
    ['123.4', 'ABC:567'],
    'https://app.countyiq.net/radar?view=opportunity',
  )
  assert.equal(url, 'https://app.countyiq.net/compare?pidn=123.4&pidn=ABC%3A567')
  assert.deepEqual(comparison.comparisonPidns('?pidn=123.4&pidn=ABC%3A567'), ['123.4', 'ABC:567'])
})

test('comparison links reject incomplete, duplicate, excessive, and unsafe selections', () => {
  for (const search of [
    '?pidn=one',
    '?pidn=one&pidn=one',
    '?pidn=one&pidn=two&pidn=three&pidn=four&pidn=five',
    '?pidn=one&pidn=%3Cscript%3E',
  ]) {
    assert.equal(comparison.comparisonPidns(search), null)
  }
})

test('editing links preserve zero or one transient parcel without falling back to local state', () => {
  assert.deepEqual(comparison.comparisonUrlSelection('?compare=editing'), {
    status: 'selection',
    pidns: [],
  })
  assert.deepEqual(comparison.comparisonUrlSelection('?compare=editing&pidn=123'), {
    status: 'selection',
    pidns: ['123'],
  })
  assert.equal(comparison.comparisonPidns('?compare=editing&pidn=123'), null)
  assert.equal(
    comparison.comparisonEditingUrl([], 'https://app.countyiq.net/compare?pidn=one&pidn=two'),
    'https://app.countyiq.net/compare?compare=editing',
  )
})

test('malformed comparison queries are distinct from an absent selection', () => {
  assert.deepEqual(comparison.comparisonUrlSelection(''), { status: 'absent', pidns: [] })
  assert.deepEqual(comparison.comparisonUrlSelection('?pidn=one'), {
    status: 'invalid',
    pidns: [],
  })
})
