import assert from 'node:assert/strict'
import { test } from 'node:test'
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import ts from 'typescript'

const snapshot = {
  version: 3,
  items: [],
  saved_searches: [],
  comparison: [],
  recent_investigations: [],
}
const inbox = { notifications: [], has_more: false, next_before_id: null, summary: '' }
const session = (id) => ({
  authenticated: true,
  configured: true,
  sync_enabled: true,
  user: { id, email: id + '@example.com' },
  workspace_id: id,
  login_url: '/',
})
const json = (body, status = 200) => new Response(JSON.stringify(body), { status })
const deferred = () => {
  let resolve
  const promise = new Promise((r) => {
    resolve = r
  })
  return { promise, resolve }
}
async function harness(t, values = new Map()) {
  const directory = mkdtempSync(join(tmpdir(), 'countyiq-sync-'))
  t.after(() => rmSync(directory, { recursive: true, force: true }))
  for (const name of ['browserStorage', 'watchlist', 'investigationState', 'watchSync']) {
    const source = readFileSync(new URL('../src/lib/' + name + '.ts', import.meta.url), 'utf8')
    const { outputText } = ts.transpileModule(source, {
      compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 },
    })
    writeFileSync(
      join(directory, name + '.mjs'),
      outputText.replace(/from '(\.\/[^']+)'/g, "from '$1.mjs'"),
    )
  }
  globalThis.localStorage = {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  }
  globalThis.window = Object.assign(new EventTarget(), {
    setInterval: () => 1,
    clearInterval: () => {},
    alert: () => {},
    location: { assign: () => {} },
  })
  globalThis.document = { visibilityState: 'visible' }
  const sync = await import(pathToFileURL(join(directory, 'watchSync.mjs')))
  const watches = await import(pathToFileURL(join(directory, 'watchlist.mjs')))
  return { sync, watches, values }
}
function changedUntil(predicate) {
  return new Promise((resolve) => {
    const listener = () => {
      if (predicate()) {
        window.removeEventListener('countyiq-watch-sync-changed', listener)
        resolve()
      }
    }
    window.addEventListener('countyiq-watch-sync-changed', listener)
  })
}

for (const status of [401, 409])
  test('delayed ' + status + ' from account A cannot invalidate account B', async (t) => {
    const { sync } = await harness(t)
    let account = 'account-a'
    let delayed = null
    globalThis.fetch = async (path) =>
      path === '/api/session'
        ? json(session(account))
        : path.includes('notifications')
          ? json(inbox)
          : delayed
            ? delayed.promise
            : json(snapshot)
    await sync.refreshAccount()
    delayed = deferred()
    const pending = sync.syncWatches()
    account = 'account-b'
    await sync.refreshAccount()
    delayed.resolve(json({ detail: 'old session' }, status))
    await pending
    assert.equal(sync.watchSyncState().account.user.id, 'account-b')
    assert.equal(sync.watchSyncState().account.authenticated, true)
    assert.equal(sync.watchSyncState().conflict, false)
  })

test('edits during initial hydration survive responses, retries and page reload', async (t) => {
  const { sync, watches, values } = await harness(t)
  const requested = deferred(),
    response = deferred()
  let puts = 0
  globalThis.fetch = async (path, options) => {
    if (path === '/api/session') return json(session('account-a'))
    if (options.method === 'PUT') puts++
    if (path.includes('notifications')) return json(inbox)
    requested.resolve()
    return response.promise
  }
  const stop = sync.startWatchSync()
  t.after(stop)
  await requested.promise
  watches.toggleWatch('123')
  const completed = changedUntil(() => sync.watchSyncState().conflict)
  response.resolve(json(snapshot))
  await completed
  await sync.syncWatches()
  assert.deepEqual(watches.getWatchlist(), ['123'])
  assert.equal(puts, 0)
  assert.equal(JSON.parse(values.get('countyiq_account_sync:account-a')).requiresReview, true)
  stop()
  const reloaded = await harness(t, values)
  globalThis.fetch = async (path) =>
    path === '/api/session' ? json(session('account-a')) : json(snapshot)
  await reloaded.sync.refreshAccount()
  assert.deepEqual(reloaded.watches.getWatchlist(), ['123'])
  assert.equal(reloaded.sync.watchSyncState().conflict, true)
  await reloaded.sync.loadServerWatches()
  assert.deepEqual(reloaded.watches.getWatchlist(), [])
  assert.equal(reloaded.sync.watchSyncState().conflict, false)
  assert.equal(JSON.parse(values.get('countyiq_account_sync:account-a')).dirty, false)
})

for (const clear of [false, true])
  test(
    (clear ? 'clear' : 'load') + ' preserves edits made after confirmation and serializes sync',
    async (t) => {
      const { sync, watches, values } = await harness(t)
      globalThis.fetch = async (path) =>
        path === '/api/session'
          ? json(session('account-a'))
          : path.includes('notifications')
            ? json(inbox)
            : json(snapshot)
      const ready = changedUntil(() => sync.watchSyncState().message === 'Saved to your account.')
      t.after(sync.startWatchSync())
      await ready
      // Let the initial refresh release its guard.
      await new Promise((resolve) => setImmediate(resolve))
      const response = deferred()
      const calls = []
      globalThis.fetch = async (path, options) => {
        calls.push(options.method)
        if (options.method === 'DELETE') return response.promise
        return clear ? json({ ...snapshot, version: 4 }) : response.promise
      }
      const pending = clear ? sync.clearAccountWorkspace() : sync.loadServerWatches()
      watches.toggleWatch('123')
      await sync.syncWatches()
      assert.deepEqual(calls, [clear ? 'DELETE' : 'GET'])
      response.resolve(clear ? new Response(null, { status: 204 }) : json(snapshot))
      await pending
      assert.deepEqual(watches.getWatchlist(), ['123'])
      assert.equal(sync.watchSyncState().conflict, true)
      assert.equal(JSON.parse(values.get('countyiq_account_sync:account-a')).requiresReview, true)
      await sync.syncWatches()
      assert.equal(calls.includes('PUT'), false)
    },
  )

test('successful clear holds synchronization until the empty snapshot is applied', async (t) => {
  const { sync, watches } = await harness(t)
  globalThis.fetch = async (path) =>
    path === '/api/session'
      ? json(session('account-a'))
      : path.includes('notifications')
        ? json(inbox)
        : json({ ...snapshot, items: [{ kind: 'parcel', subject_key: '123', label: '123' }] })
  await sync.refreshAccount()
  const calls = []
  globalThis.fetch = async (path, options) => {
    calls.push(options.method)
    return options.method === 'DELETE'
      ? new Response(null, { status: 204 })
      : json({ ...snapshot, version: 4 })
  }
  await sync.clearAccountWorkspace()
  assert.deepEqual(calls, ['DELETE', 'GET'])
  assert.deepEqual(watches.getWatchlist(), [])
  assert.equal(sync.watchSyncState().message, 'Cleared your saved account workspace.')
})

test('failed refresh after deletion cannot automatically restore the cleared workspace', async (t) => {
  const { sync, values } = await harness(t)
  globalThis.fetch = async (path) =>
    path === '/api/session'
      ? json(session('account-a'))
      : path.includes('notifications')
        ? json(inbox)
        : json(snapshot)
  await sync.refreshAccount()
  const calls = []
  globalThis.fetch = async (path, options) => {
    calls.push(options.method)
    return options.method === 'DELETE' ? new Response(null, { status: 204 }) : json({}, 503)
  }
  await assert.rejects(sync.clearAccountWorkspace(), /unavailable/)
  await sync.syncWatches()
  assert.deepEqual(calls, ['DELETE', 'GET'])
  assert.equal(sync.watchSyncState().conflict, true)
  assert.equal(JSON.parse(values.get('countyiq_account_sync:account-a')).requiresReview, true)
})

const latestInbox = {
  notifications: [{ id: 200, event: {} }],
  has_more: true,
  next_before_id: 101,
  summary: 'Latest',
}
const olderInbox = {
  notifications: [{ id: 100, event: {} }],
  has_more: false,
  next_before_id: null,
  summary: 'Older',
}
async function inboxHarness(t) {
  const h = await harness(t)
  globalThis.fetch = async (path) =>
    path === '/api/session'
      ? json(session('account-a'))
      : path.includes('notifications')
        ? json(path.includes('before_id=') ? olderInbox : latestInbox)
        : json(snapshot)
  await h.sync.refreshAccount()
  return h
}
test('background sync preserves the older inbox and newest navigation restores the first page', async (t) => {
  const { sync } = await inboxHarness(t)
  await sync.olderWatchChanges()
  await sync.syncWatches()
  assert.equal(sync.watchSyncState().inbox.summary, 'Older')
  assert.equal(sync.watchSyncState().olderInbox, true)
  await sync.latestWatchChanges()
  assert.equal(sync.watchSyncState().inbox.summary, 'Latest')
  assert.equal(sync.watchSyncState().olderInbox, false)
})
test('delayed older page cannot overwrite a newer navigation request', async (t) => {
  const { sync } = await inboxHarness(t)
  const delayed = deferred()
  globalThis.fetch = async (path) =>
    path.includes('before_id=') ? delayed.promise : json(latestInbox)
  const pending = sync.olderWatchChanges()
  await sync.latestWatchChanges()
  delayed.resolve(json(olderInbox))
  await pending
  assert.equal(sync.watchSyncState().inbox.summary, 'Latest')
  assert.equal(sync.watchSyncState().olderInbox, false)
})
test('acknowledgment refreshes the displayed older page and submits only its IDs', async (t) => {
  const { sync } = await inboxHarness(t)
  await sync.olderWatchChanges()
  const requests = []
  globalThis.fetch = async (path, options) => {
    requests.push({ path, body: options.body })
    return json(options.method === 'POST' ? { ok: true } : { ...olderInbox, notifications: [] })
  }
  await sync.acknowledgeWatchChanges()
  assert.deepEqual(JSON.parse(requests[0].body), { notification_ids: [100] })
  assert.equal(requests[1].path, '/api/watchspaces/notifications?before_id=101')
  assert.equal(sync.watchSyncState().olderInbox, true)
  assert.deepEqual(sync.watchSyncState().inbox.notifications, [])
})
test('failed older page keeps the current inbox and remains retryable', async (t) => {
  const { sync } = await inboxHarness(t)
  globalThis.fetch = async () => json({}, 503)
  await assert.rejects(sync.olderWatchChanges(), /unavailable/)
  assert.equal(sync.watchSyncState().inbox.summary, 'Latest')
  assert.equal(sync.watchSyncState().olderInbox, false)
  globalThis.fetch = async () => json(olderInbox)
  await sync.olderWatchChanges()
  assert.equal(sync.watchSyncState().inbox.summary, 'Older')
})

test('background refresh started during navigation cannot restore the previous inbox page', async (t) => {
  const { sync } = await inboxHarness(t)
  const older = deferred(),
    latest = deferred(),
    requested = deferred()
  globalThis.fetch = async (path) => {
    if (!path.includes('notifications')) return json(snapshot)
    if (path.includes('before_id=')) return older.promise
    requested.resolve()
    return latest.promise
  }
  const navigation = sync.olderWatchChanges()
  const refresh = sync.syncWatches()
  await requested.promise
  older.resolve(json(olderInbox))
  await navigation
  latest.resolve(json(latestInbox))
  await refresh
  assert.equal(sync.watchSyncState().inbox.summary, 'Older')
  assert.equal(sync.watchSyncState().olderInbox, true)
})
