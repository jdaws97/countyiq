import assert from 'node:assert/strict'
import { after, test } from 'node:test'
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import ts from 'typescript'

const directory = mkdtempSync(join(tmpdir(), 'countyiq-radar-filters-'))
const source = readFileSync(new URL('../src/lib/radarFilters.ts', import.meta.url), 'utf8')
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 },
})
writeFileSync(join(directory, 'radarFilters.mjs'), outputText)
const { appendRadarCriteria, planStatusFor } = await import(
  pathToFileURL(join(directory, 'radarFilters.mjs'))
)
after(() => rmSync(directory, { recursive: true, force: true }))

test('plan status keeps opportunity bookmarks free of linked plans by default', () => {
  assert.equal(planStatusFor('opportunity', null), 'none')
  assert.equal(planStatusFor('momentum', null), 'any')
  assert.equal(planStatusFor('readiness', 'active'), 'active')
})

test('radar map criteria retain the complete regular screening screen', () => {
  const params = appendRadarCriteria(new URLSearchParams(), {
    minScore: '40',
    municipality: 'York Township',
    minAcres: '5',
    maxAcres: '25',
    parcelClass: 'I,C',
    planStatus: 'none',
  })

  assert.equal(
    params.toString(),
    'min_score=40&plan_status=none&municipality=York+Township&min_acres=5&max_acres=25&class=I%2CC',
  )
})
