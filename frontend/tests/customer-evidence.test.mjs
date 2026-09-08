import assert from 'node:assert/strict'
import { after, test } from 'node:test'
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import ts from 'typescript'

const directory = mkdtempSync(join(tmpdir(), 'countyiq-customer-evidence-'))
for (const name of ['format', 'recordDates', 'customerEvidence', 'activityDates']) {
  const source = readFileSync(new URL(`../src/lib/${name}.ts`, import.meta.url), 'utf8')
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 },
  })
  writeFileSync(
    join(directory, `${name}.mjs`),
    outputText.replace(/from '(\.\/[^']+)'/g, "from '$1.mjs'"),
  )
}
const evidence = await import(pathToFileURL(join(directory, 'customerEvidence.mjs')))
const activity = await import(pathToFileURL(join(directory, 'activityDates.mjs')))
after(() => rmSync(directory, { recursive: true, force: true }))

test('customer sources preserve useful public facts without serializing operational metadata', () => {
  const facts = evidence.sourceFacts({
    details: {
      address: '1 Main St',
      deed_bk: '2353',
      deed_pg: '7987',
      source_text_sha256: 'secret-hash',
      event_key: 'internal-key',
      inference_id: 74,
      explanation_version: 1,
      weight: 0,
      future_pipeline_metadata: { raw: 'internal' },
      changed: { owner_full: { old: 'Earlier Owner', new: 'Current Owner' } },
    },
  })
  assert.deepEqual(facts, [
    { label: 'Address', value: '1 Main St' },
    { label: 'Deed book', value: '2353' },
    { label: 'Deed page', value: '7987' },
    { label: 'Recorded owner · previous', value: 'Earlier Owner' },
    { label: 'Recorded owner · updated', value: 'Current Owner' },
  ])
  assert.deepEqual(
    evidence.sourceFacts({ details: { owner_full: { old: 'Earlier', new: 'Later' } } }),
    [
      { label: 'Recorded owner · previous', value: 'Earlier' },
      { label: 'Recorded owner · updated', value: 'Later' },
    ],
  )
})

test('source navigation retains the exact PDF page and the related property', () => {
  assert.deepEqual(
    evidence.sourceFacts({
      source_kind: 'official_zoning_layer',
      details: { name: 'Commercial Industrial', code: 'CI' },
    }),
    [
      { label: 'Mapped zoning district', value: 'Commercial Industrial' },
      { label: 'District code', value: 'CI' },
    ],
  )
  const source = {
    document_url: 'https://town.example/agenda.pdf#old',
    details: {
      pidn: '54000JJ008400',
      passages: [{ page: 2, text: 'Hearing proposed for September 8.' }],
    },
  }
  assert.equal(evidence.sourceOriginalUrl(source), 'https://town.example/agenda.pdf#page=2')
  assert.equal(evidence.sourcePropertyPath(source), '/property/54000JJ008400')
  assert.deepEqual(evidence.sourcePassages(source), [
    { text: 'Hearing proposed for September 8.', page: 2 },
  ])
})

test('upcoming dates keep proposal status, exclude historical or invalid dates, and resolve the cited passage', () => {
  const date = {
    date: '2026-09-08',
    label: 'Hearing',
    status: 'proposed',
    source_id: 'P1',
    time: '6:00 pm',
  }
  const source = {
    citation_key: 'evidence:source:P1',
    details: {
      record_dates: [
        date,
        { ...date, date: '2026-09-06' },
        { ...date, status: 'historical' },
        { ...date, date: '2026-02-31' },
      ],
    },
  }
  const event = { event_key: 'example', sources: [source, source] }
  const dates = activity.upcomingActivityDates([event], new Date(2026, 8, 7))
  assert.equal(dates.length, 1)
  assert.equal(dates[0].date.status, 'proposed')
  assert.equal(dates[0].source, source)
})

test('multi-page excerpts copy exact wording and link each physical PDF page', () => {
  const source = {
    label: 'Planning commission agenda',
    source_kind: 'municipal_evidence',
    document_url: 'https://town.example/agenda.pdf?download=1#page=1',
    details: {
      passages: [
        { text: 'First page\n', page: 2 },
        { text: 'Next page.', page: 3 },
      ],
    },
  }
  const passages = evidence.sourcePassages(source)
  assert.equal(
    evidence.sourceOriginalUrl(source, passages[1]),
    'https://town.example/agenda.pdf?download=1#page=3',
  )
  assert.equal(
    evidence.sourceExcerptText(source, passages[0]),
    'First page\n\n\nPlanning commission agenda — PDF page 2\n\nhttps://town.example/agenda.pdf?download=1#page=2',
  )
  assert.equal(evidence.sourceOriginalUrl({ ...source, document_url: 'javascript:alert(1)' }), null)
  assert.equal(
    evidence.sourceOriginalUrl({
      ...source,
      document_url: 'https://user:pass@town.example/source.pdf',
    }),
    null,
  )
  assert.equal(
    evidence.sourcePassages({ excerpt: 'No location', details: { page: -1 } })[0].page,
    null,
  )
})

test('GIS navigation selects the relevant map layer and retains property context', () => {
  const source = {
    source_kind: 'public_record',
    citation_key: 'evidence:source:zoning',
    url: 'https://gis.example/arcgis/rest/services/Zoning/MapServer/0/query',
    internal_url: '/property/12345',
    details: {},
  }
  assert.deepEqual(evidence.sourceMapLink(source), {
    path: '/map?highlight=12345&layer=zoning',
    label: 'View zoning on map',
  })
  assert.equal(evidence.sourceMapLink({ ...source, internal_url: null }), null)
  assert.equal(evidence.sourcePropertyPath({ internal_url: '//elsewhere.example/record' }), null)
})
