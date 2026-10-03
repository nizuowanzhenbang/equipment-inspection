import assert from 'node:assert/strict'
import test from 'node:test'
import axios from 'axios'

test('receipt transport preserves the account snapshot if shared credentials change', async () => {
  const originalAdapter = axios.defaults.adapter
  const originalStorage = globalThis.localStorage
  let sent
  axios.defaults.adapter = async config => {
    sent = config
    return { data: { code: 0, data: { stock_qty: 12, status: 'APPROVED' } }, status: 200, statusText: 'OK', headers: {}, config }
  }
  try {
    // A second tab can replace shared credentials after the UI checks them.
    globalThis.localStorage = { getItem: () => 'another-account-token' }
    const { purchaseRequestApi } = await import('../src/api/index.ts')
    await purchaseRequestApi.receive(7, 2, '3014691d-a594-4676-970d-60e4de4ca770', 'original-account-token')
    assert.equal(sent.headers.Authorization, 'Bearer original-account-token')
    assert.deepEqual(JSON.parse(sent.data), { received_qty: 2, request_id: '3014691d-a594-4676-970d-60e4de4ca770' })
  } finally {
    axios.defaults.adapter = originalAdapter
    if (originalStorage === undefined) delete globalThis.localStorage
    else globalThis.localStorage = originalStorage
  }
})
