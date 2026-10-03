import assert from 'node:assert/strict'
import { after, test } from 'node:test'
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import ts from 'typescript'

const directory = mkdtempSync(join(tmpdir(), 'countyiq-intelligence-flow-'))
const source = readFileSync(new URL('../src/lib/intelligenceFlow.ts', import.meta.url), 'utf8')
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 },
})
writeFileSync(join(directory, 'flow.mjs'), outputText)
const flow = await import(pathToFileURL(join(directory, 'flow.mjs')))
after(() => rmSync(directory, { recursive: true, force: true }))

const profile = {
  audience: 'service_business',
  services: ['engineering'],
  municipalities: [],
  families: [],
}
const early = { audience: 'service_business', services: ['engineering'], readiness: 'research' }
const qualified = { ...early, readiness: 'qualify' }
const caseValue = {
  opportunities: [],
  implications: [early],
  project_types: [],
  municipalities: ['YORK TWP'],
  family: 'use_transition',
  revision: '12',
}

test('early commercial relevance stays available without creating an opportunity', () => {
  assert.deepEqual(flow.matchingPossibilities(caseValue, profile), [early])
  assert.deepEqual(flow.matchingPossibilities(caseValue, profile, true), [])
  assert.match(flow.caseFit(caseValue, profile), /research stage/)
})

test('service and timing must match the same commercial possibility', () => {
  const mixed = {
    ...caseValue,
    opportunities: [{ ...qualified, services: ['electrical'] }],
  }
  const criteria = { ...profile, preferred_readiness: ['qualify'] }
  assert.deepEqual(flow.matchingPossibilities(mixed, criteria), [])
  assert.match(flow.caseFit(mixed, criteria), /No commercial fit/)
  assert.deepEqual(
    flow.matchingPossibilities({ ...mixed, opportunities: [qualified] }, criteria, true),
    [qualified],
  )
})

test('unknown project type and outside geography do not claim customer fit', () => {
  assert.match(
    flow.caseFit(caseValue, { ...profile, project_types: ['housing'] }),
    /has not been established/,
  )
  assert.match(
    flow.caseFit(caseValue, { ...profile, municipalities: ['Another place'] }),
    /Outside/,
  )
  assert.match(
    flow.caseFit(caseValue, { ...profile, municipalities: ['York Twp'] }),
    /research stage/,
  )
})

test('old service selections do not hide investor cases after changing business type', () => {
  const investorProfile = { ...profile, audience: 'investor' }
  const investorCase = {
    ...caseValue,
    implications: [{ ...early, audience: 'investor', services: [] }],
  }
  assert.equal(flow.matchingPossibilities(investorCase, investorProfile).length, 1)
  assert.equal(flow.profileQuery(investorProfile).has('service'), false)
})

test('profile query carries all criteria without transmitting personal notes', () => {
  const query = flow.profileQuery({
    ...profile,
    municipalities: ['YORK TWP', 'CONEWAGO TWP'],
    project_types: ['housing'],
    preferred_readiness: ['qualify', 'act'],
  })
  assert.deepEqual(query.getAll('municipality'), ['YORK TWP', 'CONEWAGO TWP'])
  assert.deepEqual(query.getAll('readiness'), ['qualify', 'act'])
  assert.equal(query.get('project_type'), 'housing')
  assert.equal(query.has('note'), false)
})

test('revised or unavailable followed cases need review; dismissed cases stay dismissed', () => {
  const saved = { status: 'waiting', last_seen_revision: '11' }
  assert.equal(flow.workNeedsReview(saved, caseValue), true)
  assert.equal(flow.workNeedsReview(saved), true)
  assert.equal(flow.workNeedsReview({ ...saved, last_seen_revision: '12' }, caseValue), false)
  assert.equal(flow.workNeedsReview({ ...saved, status: 'rejected' }, caseValue), false)
})
