import assert from 'node:assert/strict'
import { after, before, test } from 'node:test'
import http from 'node:http'
import { createServer } from 'vite'

let vite
let api
let port
before(async () => {
  api = http.createServer((request, response) => {
    response.setHeader('Content-Type', 'application/json')
    response.end(JSON.stringify({ path: request.url }))
  })
  await new Promise((resolve) => api.listen(0, '127.0.0.1', resolve))
  vite = await createServer({
    logLevel: 'silent',
    server: {
      host: '127.0.0.1',
      port: 0,
      strictPort: false,
      open: false,
      proxy: { '/api': { target: `http://127.0.0.1:${api.address().port}`, changeOrigin: true } },
    },
  })
  await vite.listen()
  port = vite.httpServer.address().port
})
after(async () => {
  await vite?.close()
  if (api) await new Promise((resolve) => api.close(resolve))
})
function request(host, path) {
  return new Promise((resolve, reject) => {
    http
      .get(
        { hostname: '127.0.0.1', port, path, headers: { Host: `${host}:${port}` } },
        (response) => {
          let body = ''
          response.setEncoding('utf8')
          response.on('data', (chunk) => {
            body += chunk
          })
          response.on('end', () =>
            resolve({ status: response.statusCode, headers: response.headers, body }),
          )
        },
      )
      .on('error', reject)
  })
}
test('app API root and descendants reach the API rather than HTML', async () => {
  for (const path of ['/api', '/api/ready?probe=1']) {
    const response = await request('app.localhost', path)
    assert.equal(response.status, 200)
    assert.deepEqual(JSON.parse(response.body), { path })
  }
})
test('marketing host never proxies API routes', async () => {
  for (const path of ['/api', '/api/ready']) {
    assert.equal((await request('localhost', path)).status, 404)
  }
})
test('explicit product entry redirects from marketing to the app root', async () => {
  for (const path of ['/app', '/app.html']) {
    const response = await request('localhost', path)
    assert.equal(response.status, 302)
    assert.equal(response.headers.location, `http://app.localhost:${port}/`)
  }
})
test('app index and nested route use the product entry', async () => {
  for (const path of ['/index.html', '/watchlist']) {
    const response = await request('app.localhost', path)
    assert.equal(response.status, 200)
    assert.match(response.body, /src="\/src\/main.tsx"/)
    assert.doesNotMatch(response.body, /src="\/src\/marketing.tsx"/)
  }
})
