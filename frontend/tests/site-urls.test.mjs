import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

const source = readFileSync(new URL('../src/lib/siteUrls.ts', import.meta.url), 'utf8')
const { outputText } = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 } })
const { siteUrls } = await import('data:text/javascript;base64,' + Buffer.from(outputText).toString('base64'))

test('production sign-in crosses to the app host and About returns to marketing', () => {
  for (const hostname of ['countyiq.net', 'app.countyiq.net']) {
    assert.deepEqual(siteUrls({ hostname, protocol: 'https:', port: '' }), {
      marketing: 'https://countyiq.net', app: 'https://app.countyiq.net',
    })
  }
})
test('local host split preserves the preview port without visiting production', () => {
  for (const hostname of ['localhost', '127.0.0.1', 'app.localhost']) {
    assert.deepEqual(siteUrls({ hostname, protocol: 'http:', port: '5180' }), {
      marketing: 'http://localhost:5180', app: 'http://app.localhost:5180',
    })
  }
})
