import assert from 'node:assert/strict'
import test from 'node:test'
import { WebMercatorViewport } from '@deck.gl/core'
import { after } from 'node:test'
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import ts from 'typescript'

const directory = mkdtempSync(join(process.cwd(), '.tmp-map-viewport-'))
const source = readFileSync(new URL('../src/lib/mapViewport.ts', import.meta.url), 'utf8')
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 },
})
writeFileSync(join(directory, 'mapViewport.mjs'), outputText)
const { fitGeometry, urlView, visibleBounds } = await import(
  pathToFileURL(join(directory, 'mapViewport.mjs'))
)
after(() => rmSync(directory, { recursive: true, force: true }))

const fallback = { longitude: -76.73, latitude: 39.92, zoom: 10, bearing: 0, pitch: 0 }

test('invalid map URL coordinates retain the county default', () => {
  for (const query of [
    'lat=hello&lng=-76.7',
    'lat=+&lng=-76.7',
    'lat=85.2&lng=-76.7',
    'lat=40&lng=181',
    'lat=40&lng=-76.7&zoom=Infinity',
  ]) {
    assert.equal(urlView(new URLSearchParams(query), fallback), fallback)
  }
  assert.deepEqual(urlView(new URLSearchParams('lat=40&lng=-76.7&zoom=15'), fallback), {
    ...fallback,
    latitude: 40,
    longitude: -76.7,
    zoom: 15,
  })
})

test('visible bounds cover every canvas corner at mobile and desktop sizes', () => {
  for (const size of [
    { width: 390, height: 700 },
    { width: 1440, height: 900 },
  ]) {
    const bounds = visibleBounds({ ...fallback, zoom: 13 }, size)
    const viewport = new WebMercatorViewport({ ...fallback, zoom: 13, ...size })
    for (const corner of [
      [bounds.west, bounds.south],
      [bounds.east, bounds.north],
    ]) {
      const [x, y] = viewport.project(corner)
      assert.ok(x >= -1 && x <= size.width + 1 && y >= -1 && y <= size.height + 1)
    }
  }
})

test('fitting a polygon keeps its distant corners on screen and caps zoom', () => {
  const polygon = {
    type: 'Polygon',
    coordinates: [
      [
        [-76.8, 39.9],
        [-76.8, 39.94],
        [-76.72, 39.94],
        [-76.72, 39.9],
        [-76.8, 39.9],
      ],
    ],
  }
  const size = { width: 390, height: 700 }
  const fitted = fitGeometry(fallback, size, polygon)
  assert.ok(fitted)
  assert.ok(fitted.zoom <= 17)
  const viewport = new WebMercatorViewport({ ...fitted, ...size })
  for (const point of polygon.coordinates[0]) {
    const [x, y] = viewport.project(point)
    assert.ok(x > 0 && x < size.width && y > 0 && y < size.height)
  }
})
