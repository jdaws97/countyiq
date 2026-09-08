import assert from 'node:assert/strict'
import { after, test } from 'node:test'
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import ts from 'typescript'

const directory = mkdtempSync(join(tmpdir(), 'countyiq-record-dates-'))
for (const name of ['format', 'recordDates']) {
  const source = readFileSync(new URL(`../src/lib/${name}.ts`, import.meta.url), 'utf8')
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 },
  })
  writeFileSync(
    join(directory, `${name}.mjs`),
    outputText.replace(/from '(\.\/[^']+)'/g, "from '$1.mjs'"),
  )
}
const dates = await import(pathToFileURL(join(directory, 'recordDates.mjs')))
after(() => rmSync(directory, { recursive: true, force: true }))

test('county DD-MON-YYYY dates sort chronologically rather than lexically', () => {
  const sales = [
    { pidn: 'older', saledt: '31-DEC-2025' },
    { pidn: 'newer', saledt: '02-JAN-2026' },
  ]
  const latest = sales.reduce((current, sale) => {
    return dates.recordDateTimestamp(sale.saledt) > dates.recordDateTimestamp(current.saledt)
      ? sale
      : current
  })
  assert.equal(latest.pidn, 'newer')
})

test('passed proposed dates preserve their status and keep the outcome unverified', () => {
  assert.match(
    dates.describeRecordDate(
      {
        date: '2026-01-10',
        time: null,
        label: 'Hearing',
        status: 'proposed',
        quote: '',
        source_id: 'P1',
      },
      new Date(2026, 1, 1),
    ),
    /proposed date passed; outcome unverified/,
  )
})
