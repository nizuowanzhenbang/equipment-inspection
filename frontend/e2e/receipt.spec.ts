import { randomUUID } from 'node:crypto'
import { expect, test } from '@playwright/test'

async function prepareReceipt(page: any, request: any) {
  const login = await request.post('/api/auth/login', { form: { username: 'admin', password: 'admin123' } })
  expect(login.status()).toBe(200)
  const headers = { Authorization: `Bearer ${(await login.json()).access_token}` }
  const name = `收货重试-${randomUUID().slice(0, 8)}`
  const partResponse = await request.post('/api/spare-parts', { headers, data: { name, stock_qty: 10, min_qty: 1, unit_price: 2 } })
  expect(partResponse.status()).toBe(200)
  const part = (await partResponse.json()).data
  const created = await request.post('/api/purchase-requests', { headers, data: { spare_part_id: part.id, qty: 5 } })
  expect(created.status()).toBe(200)
  const purchase = (await created.json()).data
  for (const action of ['submit', 'approve']) {
    expect((await request.post(`/api/purchase-requests/${purchase.id}/${action}`, { headers, data: {} })).status()).toBe(200)
  }
  await page.goto('/login')
  await page.getByPlaceholder('用户名', { exact: true }).fill('admin')
  await page.getByPlaceholder('密码', { exact: true }).fill('admin123')
  await page.getByRole('button', { name: /^登\s*录$/ }).click()
  await expect(page).toHaveURL(/\/dashboard$/)
  await page.goto('/purchase-requests')
  const open = async (target = page) => {
    await target.getByRole('row').filter({ hasText: name }).getByRole('button', { name: /^详\s*情$/ }).click()
    await target.getByRole('button', { name: /^(到货入库|确认上次收货)$/ }).click()
  }
  return { headers, name, part, purchase, open }
}

test('lost committed receipt response survives reload and does not double stock', async ({ page, request }) => {
  const { headers, name, part, purchase, open } = await prepareReceipt(page, request)
  const bodies: any[] = []
  let committed: () => void = () => {}
  const firstCommit = new Promise<void>(resolve => { committed = resolve })
  await page.route(`**/api/purchase-requests/${purchase.id}/receive`, async route => {
    bodies.push(route.request().postDataJSON())
    if (bodies.length === 1) {
      const response = await route.fetch()
      expect(response.status()).toBe(200)
      await route.abort('failed')
      committed()
    } else await route.continue()
  })
  await open()
  const dialog = page.getByRole('dialog', { name: '到货入库', exact: true })
  await dialog.getByLabel('本次入库数量').fill('2')
  await dialog.getByRole('button', { name: 'OK', exact: true }).click()
  await firstCommit
  expect(bodies[0].request_id).toMatch(/^[0-9a-f-]{36}$/)
  await expect(dialog).toBeVisible()
  await page.reload()
  await open()
  await expect(dialog.getByLabel('本次入库数量')).toHaveValue(/^2(?:\.0+)?$/)
  await expect(dialog.getByLabel('本次入库数量')).toBeDisabled()
  const replay = page.waitForResponse(r => r.url().endsWith(`/api/purchase-requests/${purchase.id}/receive`) && r.request().method() === 'POST')
  await dialog.getByRole('button', { name: '确认上次收货', exact: true }).click()
  expect((await replay).status()).toBe(200)
  await expect(dialog).not.toBeVisible()
  expect(bodies[1]).toEqual(bodies[0])
  const assertState = async (stock: number, received: number, count: number) => {
    expect(Number((await (await request.get(`/api/spare-parts/${part.id}`, { headers })).json()).data.stock_qty)).toBe(stock)
    expect(Number((await (await request.get(`/api/purchase-requests/${purchase.id}`, { headers })).json()).data.received_qty)).toBe(received)
    expect((await (await request.get(`/api/spare-parts/${part.id}/movements`, { headers })).json()).data.items).toHaveLength(count)
  }
  await assertState(12, 2, 1)
  await page.getByRole('button', { name: '到货入库', exact: true }).click()
  await dialog.getByLabel('本次入库数量').fill('1')
  const next = page.waitForResponse(r => r.url().endsWith(`/api/purchase-requests/${purchase.id}/receive`) && r.request().method() === 'POST')
  await dialog.getByRole('button', { name: 'OK', exact: true }).click()
  expect((await next).status()).toBe(200)
  await expect(dialog).not.toBeVisible()
  expect(bodies[2].request_id).not.toBe(bodies[0].request_id)
  await assertState(13, 3, 2)
})

test('a stale tab replays its original receipt and cannot discard a newer pending shipment', async ({ page, request, context }) => {
  const { purchase, part, headers, open } = await prepareReceipt(page, request)
  const path = `/api/purchase-requests/${purchase.id}/receive`
  const bodies: any[] = []
  await page.route(`**${path}`, async route => {
    bodies.push(route.request().postDataJSON())
    if (bodies.length === 1) { expect((await route.fetch()).status()).toBe(200); await route.abort('failed') }
    else await route.continue()
  })
  await open()
  const dialog = page.getByRole('dialog', { name: '到货入库', exact: true })
  await dialog.getByLabel('本次入库数量').fill('2')
  await dialog.getByRole('button', { name: 'OK', exact: true }).click()
  await expect(dialog.getByRole('button', { name: '确认上次收货', exact: true })).toBeEnabled()
  await dialog.getByRole('button', { name: '核对流水后放弃待确认记录' }).click()
  const warning = page.getByRole('dialog', { name: '放弃待确认收货？' })
  await expect(warning).toBeVisible()
  const other = await context.newPage()
  await other.goto('/purchase-requests')
  await open(other)
  const otherDialog = other.getByRole('dialog', { name: '到货入库', exact: true })
  await otherDialog.getByRole('button', { name: '确认上次收货', exact: true }).click()
  await expect(otherDialog).not.toBeVisible()
  await other.getByRole('button', { name: '到货入库', exact: true }).click()
  let newer: any
  await other.route(`**${path}`, async route => {
    newer = route.request().postDataJSON()
    expect((await route.fetch()).status()).toBe(200)
    await route.abort('failed')
  })
  await otherDialog.getByLabel('本次入库数量').fill('1')
  await otherDialog.getByRole('button', { name: 'OK', exact: true }).click()
  await expect(otherDialog.getByRole('button', { name: '确认上次收货', exact: true })).toBeEnabled()
  await warning.getByRole('button', { name: '已核对，放弃待确认记录' }).click()
  const stored = () => page.evaluate(id => JSON.parse(localStorage.getItem(`purchase-receipt:admin:${id}`) || 'null'), purchase.id)
  expect((await stored())?.requestId).toBe(newer.request_id)
  await dialog.getByRole('button', { name: '确认上次收货', exact: true }).click()
  await expect(dialog).not.toBeVisible()
  expect(bodies[1]).toEqual(bodies[0])
  expect((await stored())?.requestId).toBe(newer.request_id)
  expect(Number((await (await request.get(`/api/spare-parts/${part.id}`, { headers })).json()).data.stock_qty)).toBe(13)
  expect((await (await request.get(`/api/spare-parts/${part.id}/movements`, { headers })).json()).data.items).toHaveLength(2)
})

test('another tab switching account blocks confirmation from the stale account', async ({ page, request }) => {
  const { purchase, part, headers, open } = await prepareReceipt(page, request)
  const path = `/api/purchase-requests/${purchase.id}/receive`
  let count = 0
  await page.route(`**${path}`, async route => {
    count++
    if (count === 1) await route.abort('failed')
    else await route.continue()
  })
  await open()
  const dialog = page.getByRole('dialog', { name: '到货入库', exact: true })
  await dialog.getByLabel('本次入库数量').fill('2')
  await dialog.getByRole('button', { name: 'OK', exact: true }).click()
  await expect(dialog.getByRole('button', { name: /确认上次收货$/ })).not.toHaveClass(/ant-btn-loading/)
  const switched = await request.post('/api/auth/login', { form: { username: 'inspector', password: 'inspector123' } })
  expect(switched.status()).toBe(200)
  await page.evaluate(token => {
    localStorage.setItem('username', 'inspector'); localStorage.setItem('role', 'INSPECTOR'); localStorage.setItem('token', token)
  }, (await switched.json()).access_token)
  await dialog.getByRole('button', { name: /确认上次收货$/ }).click()
  await expect(page.getByText('登录账户已变化，请刷新页面后使用原账户确认收货', { exact: true })).toBeVisible()
  expect(count).toBe(1)
  expect(Number((await (await request.get(`/api/spare-parts/${part.id}`, { headers })).json()).data.stock_qty)).toBe(10)
  expect((await (await request.get(`/api/spare-parts/${part.id}/movements`, { headers })).json()).data.items).toHaveLength(0)
})
