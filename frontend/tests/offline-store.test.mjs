import 'fake-indexeddb/auto'
import { test, beforeEach } from 'node:test'
import assert from 'node:assert/strict'
import { enqueueRecord, listQueue, removeQueued, syncQueue } from '../src/utils/offlineStore.ts'

const storage = new Map()
globalThis.localStorage = { getItem: (key) => storage.get(key) ?? null }
const record = { task_id: 1, point_id: 2, status: 'NORMAL' }

beforeEach(async () => {
  for (const row of await listQueue()) await removeQueued(row.id)
  storage.clear()
  storage.set('username', 'inspector')
  storage.set('token', 'test-token')
})

test('successful retry removes a queued record after a lost response', async () => {
  await enqueueRecord(record)
  globalThis.fetch = async () => { throw new TypeError('connection lost') }
  assert.equal((await syncQueue()).remaining, 1)
  globalThis.fetch = async () => new Response('{}', { status: 200 })
  assert.equal((await syncQueue()).success, 1)
  assert.deepEqual(await listQueue(), [])
})

test('conflicts stay visible and are not automatically submitted again', async () => {
  await enqueueRecord(record)
  let calls = 0
  globalThis.fetch = async () => { calls++; return new Response('{}', { status: 409 }) }
  await syncQueue()
  await syncQueue()
  assert.equal(calls, 1)
  assert.equal((await listQueue())[0].blocked, true)
})

test('switching accounts never uploads another user\'s offline work', async () => {
  await enqueueRecord(record)
  storage.set('username', 'another-user')
  let calls = 0
  globalThis.fetch = async () => { calls++; return new Response('{}', { status: 200 }) }
  await syncQueue()
  assert.equal(calls, 0)
  assert.equal((await listQueue()).length, 1)
  storage.set('username', 'inspector')
  assert.equal((await syncQueue()).success, 1)
})

test('parallel sync triggers share one upload batch', async () => {
  await enqueueRecord(record)
  let calls = 0
  globalThis.fetch = async () => {
    calls++
    await new Promise(resolve => setTimeout(resolve, 10))
    return new Response('{}', { status: 200 })
  }
  await Promise.all([syncQueue(), syncQueue()])
  assert.equal(calls, 1)
  assert.equal((await listQueue()).length, 0)
})

test('missing authentication preserves the queue without sending requests', async () => {
  await enqueueRecord(record)
  storage.delete('token')
  let calls = 0
  globalThis.fetch = async () => { calls++; return new Response('{}', { status: 200 }) }
  await syncQueue()
  assert.equal(calls, 0)
  assert.equal((await listQueue()).length, 1)
})
