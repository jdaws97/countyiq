import assert from 'node:assert/strict'
import { after, test } from 'node:test'
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import ts from 'typescript'

const directory = mkdtempSync(join(tmpdir(), 'countyiq-flood-screening-'))
for (const name of ['format', 'floodScreening', 'customerEvidence']) {
  const source = readFileSync(new URL(`../src/lib/${name}.ts`, import.meta.url), 'utf8')
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 },
  })
  writeFileSync(
    join(directory, `${name}.mjs`),
    outputText.replace(/from '(\.\/[^']+)'/g, "from '$1.mjs'"),
  )
}
const { presentFloodScreening, floodScreeningSummary, floodLayerSfhaLabel } = await import(
  pathToFileURL(join(directory, 'floodScreening.mjs'))
)
const { sourceFacts } = await import(pathToFileURL(join(directory, 'customerEvidence.mjs')))
after(() => rmSync(directory, { recursive: true, force: true }))

const legacy = { in_flood_zone: false, zone: null, sfha: false, overlap_pct: null }

test('older negative responses remain unknown while observed hits remain visible', () => {
  const missingCoverage = presentFloodScreening(legacy)
  assert.equal(missingCoverage.status, 'unknown')
  assert.equal(missingCoverage.label, 'Flood screening unknown')
  assert.match(missingCoverage.summary, /Mapping freshness is unknown/)
  assert.doesNotMatch(missingCoverage.summary, /No SFHA overlap/)

  const observed = presentFloodScreening({ ...legacy, in_flood_zone: true, zone: 'AE' })
  assert.equal(observed.status, 'overlap')
  assert.match(observed.summary, /Mapped SFHA overlap\. Zone AE/)
})

test('explicit unknown status takes precedence over legacy booleans and rounded coverage', () => {
  const result = presentFloodScreening({
    ...legacy,
    in_flood_zone: true,
    status: 'unknown',
    mapped_coverage_pct: 100,
    reason: 'Mapped coverage is missing, incomplete, or includes undetermined zones.',
  })
  assert.equal(result.status, 'unknown')
  assert.match(result.summary, /100\.0% mapped coverage/)
  assert.match(result.summary, /includes undetermined zones/)
  assert.doesNotMatch(result.summary, /No SFHA overlap|Mapped SFHA overlap/)
})

test('supported absence always retains its stale or unknown freshness qualification', () => {
  for (const status of ['stale', 'unknown']) {
    const result = presentFloodScreening({
      ...legacy,
      status: 'no_overlap',
      mapped_coverage_pct: 100,
      freshness: { status, last_successful_run_at: '2026-09-01' },
    })
    assert.equal(result.label, 'No SFHA overlap in loaded mapping')
    assert.match(result.summary, new RegExp(status))
    assert.match(result.summary, /Last successful source run: Sep 1, 2026/)
    assert.doesNotMatch(result.summary, /cleared|safe|flood.free/i)
  }
})

test('UI and CSV summary preserve the same supported result and freshness', () => {
  const flood = {
    ...legacy,
    status: 'no_overlap',
    mapped_coverage_pct: 100,
    freshness: { status: 'stale', last_successful_run_at: null },
  }
  assert.equal(floodScreeningSummary(flood), presentFloodScreening(flood).summary)
  assert.match(floodScreeningSummary(flood), /No SFHA overlap in loaded mapping.*stale/)
})

test('positive overlap remains visible when mapping covers only part of the parcel', () => {
  const result = presentFloodScreening({
    ...legacy,
    status: 'overlap',
    zone: 'AE',
    overlap_pct: 12.3,
    mapped_coverage_pct: 40,
    freshness: { status: 'current', last_successful_run_at: null },
  })
  assert.equal(result.status, 'overlap')
  assert.match(result.summary, /12\.3% of parcel area overlaps/)
  assert.match(result.summary, /40\.0% mapped coverage/)
  assert.doesNotMatch(result.summary, /stale|freshness is unknown/)
})

test('raw map polygons distinguish supported non-SFHA mapping from unknown classifications', () => {
  assert.equal(floodLayerSfhaLabel({ fld_zone: 'AE', sfha_tf: 'T' }), 'Yes')
  assert.equal(floodLayerSfhaLabel({ fld_zone: 'X', sfha_tf: 'F' }), 'No — mapped non-SFHA area')
  for (const properties of [
    {},
    { fld_zone: 'X', sfha_tf: null },
    { fld_zone: 'AE', sfha_tf: 'F' },
    { fld_zone: 'AREA NOT INCLUDED', sfha_tf: 'F' },
  ]) {
    assert.equal(floodLayerSfhaLabel(properties), 'Unknown')
  }
  assert.match(floodLayerSfhaLabel({ fld_zone: 'D', sfha_tf: 'F' }), /^Unknown/)
})

test('flood receipts present supported status and freshness without leaking operational metadata', () => {
  assert.deepEqual(
    sourceFacts({
      source_kind: 'official_flood_layer',
      details: {
        screening_status: 'no_overlap',
        mapped_coverage_pct: 100,
        freshness: 'stale',
        last_successful_run_at: '2026-09-01',
        future_internal_field: 'not public',
      },
    }),
    [
      { label: 'Flood screening', value: 'No SFHA overlap in loaded mapping' },
      { label: 'Mapping freshness', value: 'Loaded mapping is stale' },
      { label: 'Mapped coverage', value: '100%' },
      { label: 'Last successful source run', value: 'Sep 1, 2026' },
    ],
  )
})
