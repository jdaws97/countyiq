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
  'format',
  'floodScreening',
  'sitePacket',
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
const handoff = await import(pathToFileURL(join(directory, 'sitePacket.mjs')))
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

test('saved question responses roundtrip while older inquiries stay readable', () => {
  const question_reviews = [
    {
      key: 'zoning',
      status: 'answered',
      note: 'Planner confirmed the district on October 3; check the ordinance.',
    },
  ]
  const portable = state.parseWorkspace(
    JSON.stringify({ ...workspace(), siteInquiries: [{ ...siteInquiry, question_reviews }] }),
  )
  state.replaceWorkspace(portable)
  assert.deepEqual(inquiries.getSiteInquiries()[0].question_reviews, question_reviews)
  assert.equal(inquiries.openSiteQuestionCount(inquiries.getSiteInquiries()[0]), 4)
  assert.equal(inquiries.isSiteInquiries([siteInquiry]), true)
  assert.equal(inquiries.openSiteQuestionCount(siteInquiry), 5)
  assert.equal(
    inquiries.openSiteQuestionCount({
      ...siteInquiry,
      question_reviews: [{ ...question_reviews[0], note: ' ' }],
    }),
    5,
  )
  assert.equal(
    inquiries.isSiteInquiries([
      { ...siteInquiry, question_reviews: [{ ...question_reviews[0], note: ' ' }] },
    ]),
    false,
  )
  assert.equal(
    inquiries.isSiteInquiries([
      { ...siteInquiry, question_reviews: [...question_reviews, ...question_reviews] },
    ]),
    false,
  )
})

test('an edited draft cannot overwrite a newer saved inquiry or recreate a removed one', () => {
  inquiries.saveSiteInquiry(siteInquiry, null)
  const latest = { ...siteInquiry, note: 'Newer notes', updated_at: '2026-10-03T13:00:00Z' }
  inquiries.saveSiteInquiry(latest, siteInquiry.updated_at)
  assert.throws(
    () =>
      inquiries.saveSiteInquiry(
        { ...siteInquiry, note: 'Unsaved old draft' },
        siteInquiry.updated_at,
      ),
    /changed in another/,
  )
  assert.equal(inquiries.getSiteInquiries()[0].note, 'Newer notes')
  inquiries.removeSiteInquiry(siteInquiry.id)
  assert.throws(() => inquiries.saveSiteInquiry(latest, latest.updated_at), /changed in another/)
  assert.deepEqual(inquiries.getSiteInquiries(), [])
})

test('handoff keeps stale-review, incomplete-source and user-response qualifications together', () => {
  const packet = {
    revision: 'b'.repeat(64),
    questions: ['Confirm the parcel boundary.'],
    sources: [],
    municipal_collection: [],
    scope_note: 'This packet does not determine permitted use.',
    report: {
      parcel: { propadr: '1 Main St', municipality: 'Test Township', owner_full: 'Example Owner' },
      zoning: null,
      flood_zone: { status: 'unknown', mapped_coverage_pct: 40, freshness: { status: 'stale' } },
      soil_profile: { mapped_coverage_pct: 0, considerations: [] },
      municipal_evidence: {
        cards: [
          {
            title: 'Agenda',
            body_name: 'Planning Commission',
            meeting_date: '2026-10-01',
            proceeding_type: 'agenda',
            document_url: 'https://example.org/agenda.pdf',
            passages: [],
          },
        ],
        more: true,
        coverage: { reviewed_documents: 1, total_documents: 5 },
      },
      evidence: [],
    },
  }
  const inquiry = {
    ...siteInquiry,
    status: 'ready_for_handoff',
    question_reviews: [
      {
        key: 'identity',
        status: 'answered',
        note: 'Reviewer response retained separately from records.',
      },
    ],
  }
  const text = handoff.sitePacketText(inquiry, packet)
  assert.match(text, /DRAFT — evidence needs review/)
  assert.match(text, /Previously marked ready; current evidence needs review/)
  assert.match(text, /Reviewer response retained separately from records/)
  assert.match(text, /an agenda does not establish an outcome/)
  assert.match(text, /reviewed English excerpt is not available/)
  assert.match(text, /Additional linked passages exist/)
  assert.match(text, /Loaded mapping is stale/)
  assert.doesNotMatch(text, /No SFHA overlap/)
  assert.ok(text.includes(packet.scope_note))
  assert.ok(text.includes('https://example.org/agenda.pdf'))
  assert.ok(!text.includes(packet.revision))
})
