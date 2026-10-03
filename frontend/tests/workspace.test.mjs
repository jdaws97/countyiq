import assert from 'node:assert/strict'
import { after, beforeEach, test } from 'node:test'
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import ts from 'typescript'

// Compile the actual browser modules using the project's existing compiler.
const directory = mkdtempSync(join(tmpdir(), 'countyiq-workspace-'))
for (const name of [
  'browserStorage',
  'watchlist',
  'intelligenceState',
  'siteInquiries',
  'investigationState',
]) {
  const source = readFileSync(new URL(`../src/lib/${name}.ts`, import.meta.url), 'utf8')
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 },
  })
  writeFileSync(
    join(directory, `${name}.mjs`),
    outputText.replace(/from '(\.\/[^']+)'/g, "from '$1.mjs'"),
  )
}
const state = await import(pathToFileURL(join(directory, 'investigationState.mjs')))
const storage = await import(pathToFileURL(join(directory, 'browserStorage.mjs')))
const watches = await import(pathToFileURL(join(directory, 'watchlist.mjs')))
const intelligence = await import(pathToFileURL(join(directory, 'intelligenceState.mjs')))
const inquiries = await import(pathToFileURL(join(directory, 'siteInquiries.mjs')))
after(() => rmSync(directory, { recursive: true, force: true }))
let values
let alerts
beforeEach(() => {
  storage.setWorkspaceAccount(null)
  values = new Map()
  alerts = []
  globalThis.localStorage = {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  }
  globalThis.window = { dispatchEvent() {}, alert: (message) => alerts.push(message) }
})
const workspace = () => ({
  version: 1,
  exportedAt: '2026-09-04T00:00:00Z',
  parcels: ['123'],
  projects: [],
  entities: [],
  savedSearches: [],
  comparison: [],
  triage: {},
})
const intelligenceProfile = {
  audience: 'service_business',
  municipalities: ['York Township'],
  services: ['engineering'],
  families: ['construction_timing'],
}
const intelligenceWork = [
  {
    case_key: `emerging-${'a'.repeat(64)}`,
    status: 'qualifying',
    note: 'Review the land development plan.',
    last_seen_revision: '1',
    updated_at: '2026-09-08T12:00:00Z',
  },
]

const siteInquiry = {
  id: '00000000-0000-4000-8000-000000000001',
  pidn: '123',
  label: 'Workshop inquiry',
  proposed_use: 'Workshop',
  note: 'Private client notes',
  questions: 'Confirm sewer service',
  status: 'researching',
  reviewed_revision: 'a'.repeat(64),
  updated_at: '2026-10-03T12:00:00Z',
}

test('site inquiries survive export/import without crossing account boundaries', () => {
  inquiries.saveSiteInquiry(siteInquiry)
  storage.setWorkspaceAccount('account-a')
  assert.deepEqual(inquiries.getSiteInquiries(), [])
  state.replaceWorkspace({ ...workspace(), siteInquiries: [siteInquiry] })
  assert.equal(inquiries.getSiteInquiries()[0].note, siteInquiry.note)
  storage.setWorkspaceAccount('account-b')
  assert.deepEqual(inquiries.getSiteInquiries(), [])
  storage.setWorkspaceAccount(null)
  assert.equal(inquiries.getSiteInquiries()[0].questions, siteInquiry.questions)
})

test('failed inquiry saves and malformed imports preserve the existing private work', () => {
  inquiries.saveSiteInquiry(siteInquiry)
  const original = new Map(values)
  localStorage.setItem = () => {
    throw new Error('quota exceeded')
  }
  assert.throws(() => inquiries.saveSiteInquiry({ ...siteInquiry, note: 'Changed' }))
  assert.deepEqual(values, original)
  assert.throws(() =>
    state.parseWorkspace(
      JSON.stringify({ ...workspace(), siteInquiries: [siteInquiry, siteInquiry] }),
    ),
  )
  assert.deepEqual(values, original)
})

test('malformed stored JSON shapes cannot crash investigation pages', () => {
  for (const value of ['null', '{}', '42', '"text"']) {
    values.set('countyiq_saved_searches_v1', value)
    values.set('countyiq_compare_v1', value)
    values.set('countyiq_event_triage_v1', value)
    assert.deepEqual(state.getSavedSearches(), [])
    assert.deepEqual(state.getComparison(), [])
    assert.deepEqual(state.getEventTriage(), {})
  }
})

test('invalid trailing fields cannot partially replace watchlists', () => {
  values.set('countyiq_watchlist_v1', '["original"]')
  assert.throws(() => state.replaceWorkspace({ ...workspace(), savedSearches: {} }))
  assert.equal(values.get('countyiq_watchlist_v1'), '["original"]')
})

test('workspace import restores every previous key after quota failure', () => {
  values.set('countyiq_watchlist_v1', '["original"]')
  values.set('countyiq_saved_searches_v1', '[]')
  const original = new Map(values)
  let writes = 0
  localStorage.setItem = (key, value) => {
    if (++writes === 4) throw new Error('quota exceeded')
    values.set(key, value)
  }
  assert.throws(() => state.replaceWorkspace(workspace()), /previous workspace was kept/)
  assert.deepEqual(values, original)
})

test('older exports without municipalities remain portable', () => {
  state.replaceWorkspace(workspace())
  assert.deepEqual(watches.getWatchlist(), ['123'])
  assert.deepEqual(watches.getMunicipalityWatchlist(), [])
})

test('workspace roundtrip restores intelligence profile and work', () => {
  const portable = {
    ...workspace(),
    intelligenceProfile,
    intelligenceWork,
  }
  const parsed = state.parseWorkspace(JSON.stringify(portable))

  state.replaceWorkspace(parsed)

  assert.deepEqual(intelligence.getIntelligenceProfile(), intelligenceProfile)
  assert.deepEqual(intelligence.getIntelligenceWork(), intelligenceWork)
})

test('malformed intelligence work is rejected without replacing browser state', () => {
  values.set('countyiq_watchlist_v1', '["existing"]')
  values.set('countyiq_intelligence_profile_v1', JSON.stringify(intelligenceProfile))
  values.set('countyiq_intelligence_work_v1', JSON.stringify(intelligenceWork))
  const original = new Map(values)

  assert.throws(() =>
    state.replaceWorkspace({
      ...workspace(),
      intelligenceWork: [{ case_key: `emerging-${'a'.repeat(64)}`, status: 'not-a-status' }],
    }),
  )

  assert.deepEqual(values, original)
  assert.deepEqual(intelligence.getIntelligenceProfile(), intelligenceProfile)
  assert.deepEqual(intelligence.getIntelligenceWork(), intelligenceWork)
})

test('older workspace files preserve existing intelligence state', () => {
  values.set('countyiq_intelligence_profile_v1', JSON.stringify(intelligenceProfile))
  values.set('countyiq_intelligence_work_v1', JSON.stringify(intelligenceWork))

  state.replaceWorkspace(workspace())

  assert.deepEqual(intelligence.getIntelligenceProfile(), intelligenceProfile)
  assert.deepEqual(intelligence.getIntelligenceWork(), intelligenceWork)
})

test('saved searches accept only local Feed and Radar destinations', () => {
  const search = {
    id: 'a',
    name: 'Example',
    kind: 'feed',
    createdAt: '2026-09-04',
    path: '/feed?municipality=York',
  }
  assert.equal(
    state.parseWorkspace(JSON.stringify({ ...workspace(), savedSearches: [search] })).savedSearches
      .length,
    1,
  )
  for (const path of [
    'https://example.com',
    '//example.com',
    'javascript:alert(1)',
    '/feed/../../outside',
  ]) {
    assert.throws(() =>
      state.parseWorkspace(
        JSON.stringify({ ...workspace(), savedSearches: [{ ...search, path }] }),
      ),
    )
  }
})

test('watch toggles report the previous state when persistence fails', () => {
  localStorage.setItem = () => {
    throw new Error('storage denied')
  }
  assert.equal(watches.toggleWatch('123'), false)
  assert.equal(alerts.length, 1)
  values.set('countyiq_watchlist_v1', '["123"]')
  assert.equal(watches.toggleWatch('123'), true)
  assert.equal(values.get('countyiq_watchlist_v1'), '["123"]')
})

test('CSV source text cannot become a spreadsheet formula', () => {
  assert.equal(
    state.toCsv([['=1+1', '+cmd', '-formula', '@SUM(A1)', ' =1', -12]]),
    "'=1+1,'+cmd,'-formula,'@SUM(A1),' =1,-12",
  )
  assert.equal(state.toCsv([['a,b', 'a"b', 'a\rb']]), '\"a,b\",\"a\"\"b\",\"a\rb\"')
})

test('saved searches and comparisons never claim failed writes succeeded', () => {
  localStorage.setItem = () => {
    throw new Error('storage denied')
  }
  assert.equal(state.saveSearch('Example', 'feed', '/feed'), null)
  assert.deepEqual(state.toggleComparison('123'), { selected: false, full: false })
  assert.deepEqual(state.getSavedSearches(), [])
  assert.deepEqual(state.getComparison(), [])
  assert.equal(alerts.length, 2)
})

test('verified accounts isolate watches, searches, comparisons and recent investigations', () => {
  watches.toggleWatch('guest')
  storage.setWorkspaceAccount('account-a')
  assert.deepEqual(watches.getWatchlist(), [])
  watches.toggleWatch('account-a-property')
  state.saveSearch('A search', 'feed', '/feed')
  state.toggleComparison('123')
  state.recordInvestigation('/property/123', 'Property A')
  storage.setWorkspaceAccount('account-b')
  assert.deepEqual(watches.getWatchlist(), [])
  assert.deepEqual(state.getSavedSearches(), [])
  assert.deepEqual(state.getComparison(), [])
  assert.deepEqual(state.getRecentInvestigations(), [])
  storage.setWorkspaceAccount('account-a')
  assert.deepEqual(watches.getWatchlist(), ['account-a-property'])
  assert.equal(state.getSavedSearches()[0].name, 'A search')
  assert.deepEqual(state.getComparison(), ['123'])
  assert.equal(state.getRecentInvestigations()[0].label, 'Property A')
  storage.setWorkspaceAccount(null)
  assert.deepEqual(watches.getWatchlist(), ['guest'])
})
