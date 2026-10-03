import assert from 'node:assert/strict'
import test from 'node:test'
import { loadReceiptAttempt, getReceiptAttempt, clearReceiptAttempt, discardReceiptAttempt, receiptAccountToken } from '../src/utils/receiptAttempt.ts'
const store = () => {
  const values = new Map()
  return { getItem: k => values.get(k) ?? null, setItem: (k, v) => values.set(k, v), removeItem: k => values.delete(k), values }
}
test('reload recovers the same identity and original quantity', () => {
  const storage = store()
  const first = getReceiptAttempt(storage, 'admin', 7, 2)
  assert.match(first.requestId, /^[0-9a-f-]{36}$/)
  assert.deepEqual(loadReceiptAttempt(storage, 'admin', 7), first)
  assert.throws(() => getReceiptAttempt(storage, 'admin', 7, 3))
})
test('user and order namespaces isolate attempts; later real shipment gets a new identity', () => {
  const storage = store()
  const first = getReceiptAttempt(storage, 'admin', 7, 2)
  assert.equal(loadReceiptAttempt(storage, 'other', 7), null)
  assert.notEqual(getReceiptAttempt(storage, 'other', 7, 2).requestId, first.requestId)
  assert.notEqual(getReceiptAttempt(storage, 'admin', 8, 2).requestId, first.requestId)
  clearReceiptAttempt(storage, 'admin', 7, 'unrelated-key')
  assert.deepEqual(loadReceiptAttempt(storage, 'admin', 7), first)
  clearReceiptAttempt(storage, 'admin', 7, first.requestId)
  assert.equal(loadReceiptAttempt(storage, 'admin', 7), null)
  assert.notEqual(getReceiptAttempt(storage, 'admin', 7, 2).requestId, first.requestId)
})
test('corrupted attempts fail closed without replacing evidence', () => {
  for (const corrupt of ['oops', '{}', '{"requestId":"bad","quantity":2}', '{"requestId":"00000000-0000-0000-0000-000000000000","quantity":0}']) {
    const storage = store()
    getReceiptAttempt(storage, 'admin', 7, 2)
    const key = [...storage.values.keys()][0]
    storage.setItem(key, corrupt)
    assert.throws(() => getReceiptAttempt(storage, 'admin', 7, 2))
    assert.equal(storage.getItem(key), corrupt)
  }
})
test('unavailable persistence blocks sending; invalid quantity never creates an attempt', () => {
  assert.throws(() => getReceiptAttempt({ getItem: () => null, setItem: () => { throw Error('quota') } }, 'admin', 7, 2))
  for (const quantity of [0, -1, NaN, Infinity, 0.001, 100000000]) {
    const storage = store()
    assert.throws(() => getReceiptAttempt(storage, 'admin', 7, quantity))
    assert.equal(storage.values.size, 0)
  }
})

test('stale tab confirms the displayed intent after another tab clears or replaces storage', () => {
  const storage = store()
  const displayed = getReceiptAttempt(storage, 'admin', 7, 2)
  clearReceiptAttempt(storage, 'admin', 7, displayed.requestId)
  assert.deepEqual(getReceiptAttempt(storage, 'admin', 7, 2, displayed), displayed)
  assert.equal(storage.values.size, 0)
  const newer = getReceiptAttempt(storage, 'admin', 7, 1)
  assert.deepEqual(getReceiptAttempt(storage, 'admin', 7, 2, displayed), displayed)
  clearReceiptAttempt(storage, 'admin', 7, displayed.requestId)
  assert.deepEqual(loadReceiptAttempt(storage, 'admin', 7), newer)
})
test('an unseen pending intent with another quantity requires explicit confirmation', () => {
  const storage = store()
  const pending = getReceiptAttempt(storage, 'admin', 7, 2)
  assert.throws(() => getReceiptAttempt(storage, 'admin', 7, 3))
  assert.deepEqual(loadReceiptAttempt(storage, 'admin', 7), pending)
})

test('abandoning an old confirmation preserves a later pending attempt', () => {
  const storage = store()
  const first = getReceiptAttempt(storage, 'admin', 7, 2)
  const raw = [...storage.values.values()][0]
  clearReceiptAttempt(storage, 'admin', 7, first.requestId)
  const later = getReceiptAttempt(storage, 'admin', 7, 1)
  assert.throws(() => discardReceiptAttempt(storage, 'admin', 7, raw))
  assert.deepEqual(loadReceiptAttempt(storage, 'admin', 7), later)
  const laterRaw = [...storage.values.values()][0]
  discardReceiptAttempt(storage, 'admin', 7, laterRaw)
  assert.equal(loadReceiptAttempt(storage, 'admin', 7), null)
})
test('stale account or token blocks a receipt before sending', () => {
  const storage = store()
  storage.setItem('username', 'admin'); storage.setItem('token', 'admin-token')
  assert.equal(receiptAccountToken(storage, 'admin', 'admin-token'), 'admin-token')
  storage.setItem('username', 'writer-b'); storage.setItem('token', 'b-token')
  assert.throws(() => receiptAccountToken(storage, 'admin', 'admin-token'))
  assert.throws(() => receiptAccountToken(storage, 'writer-b', 'admin-token'))
  assert.throws(() => receiptAccountToken(storage, 'writer-b', null))
})
