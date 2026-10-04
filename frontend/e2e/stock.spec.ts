import { randomUUID } from 'node:crypto'
import { expect, test } from '@playwright/test'
import type { APIRequestContext, Page } from '@playwright/test'

test('stocktake can record zero and display the persisted low stock', async ({ page, request }) => {
  const login = await request.post('/api/auth/login', { form: { username: 'admin', password: 'admin123' } })
  expect(login.status()).toBe(200)
  const { access_token } = await login.json()
  const headers = { Authorization: `Bearer ${access_token}` }
  const name = `盘点归零-${randomUUID().slice(0, 8)}`
  const created = await request.post('/api/spare-parts', {
    headers, data: { name, stock_qty: 10, min_qty: 1, unit_price: 2 },
  })
  expect(created.status()).toBe(200)
  const { id } = (await created.json()).data
  await page.goto('/login')
  await page.getByPlaceholder('用户名', { exact: true }).fill('admin')
  await page.getByPlaceholder('密码', { exact: true }).fill('admin123')
  await page.getByRole('button', { name: /^登\s*录$/ }).click()
  await expect(page).toHaveURL(/\/dashboard$/)
  await page.getByRole('menuitem', { name: '备品备件' }).click()
  await page.getByPlaceholder('名称/编号/规格').fill(name)
  await page.getByPlaceholder('名称/编号/规格').press('Enter')
  const row = page.getByRole('row').filter({ hasText: name })
  await row.getByRole('button', { name: '出入库' }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByText('出库', { exact: true }).click()
  await page.getByTitle('盘点调整', { exact: true }).click()
  await dialog.getByLabel('数量', { exact: true }).fill('0')
  await dialog.getByLabel('数量', { exact: true }).press('Tab')
  // An InputNumber with a positive minimum clamps zero on blur.
  await expect(dialog.getByLabel('数量', { exact: true })).toHaveValue(/^0(?:\.0+)?$/)
  const saved = page.waitForResponse(response => response.url().endsWith(`/api/spare-parts/${id}/movements`)
    && response.request().method() === 'POST')
  await dialog.getByRole('button', { name: /^(?:loading )?OK$/ }).click()
  expect((await saved).status()).toBe(200)
  await expect(dialog).not.toBeVisible()
  await expect(row.getByRole('cell').nth(4)).toHaveText(/0\.00.*不足/)
  const part = await request.get(`/api/spare-parts/${id}`, { headers })
  expect(part.status()).toBe(200)
  expect(Number((await part.json()).data.stock_qty)).toBe(0)
  const ledger = await request.get(`/api/spare-parts/${id}/movements`, { headers })
  expect(ledger.status()).toBe(200)
  const movements = (await ledger.json()).data.items
  expect(movements).toHaveLength(1)
  expect(movements[0].movement_type).toBe('ADJUST')
  expect(Number(movements[0].qty)).toBe(0)
})

async function stocktakeDialog(page: Page, request: APIRequestContext) {
  const login = await request.post('/api/auth/login', { form: { username: 'admin', password: 'admin123' } })
  expect(login.status()).toBe(200)
  const { access_token } = await login.json()
  const headers = { Authorization: `Bearer ${access_token}` }
  const name = `过时盘点-${randomUUID().slice(0, 8)}`
  const created = await request.post('/api/spare-parts', {
    headers, data: { name, stock_qty: 10, min_qty: 1, unit_price: 2 },
  })
  expect(created.status()).toBe(200)
  const { id } = (await created.json()).data
  await page.goto('/login')
  await page.getByPlaceholder('用户名', { exact: true }).fill('admin')
  await page.getByPlaceholder('密码', { exact: true }).fill('admin123')
  await page.getByRole('button', { name: /^登\s*录$/ }).click()
  await expect(page).toHaveURL(/\/dashboard$/)
  await page.getByRole('menuitem', { name: '备品备件' }).click()
  await page.getByPlaceholder('名称/编号/规格').fill(name)
  await page.getByPlaceholder('名称/编号/规格').press('Enter')
  const row = page.getByRole('row').filter({ hasText: name })
  await row.getByRole('button', { name: '出入库' }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByText('出库', { exact: true }).click()
  await page.getByTitle('盘点调整', { exact: true }).click()
  return { headers, id, row, dialog }
}

test('stale stocktake requires a fresh snapshot and explicit new quantity', async ({ page, request }) => {
  const { headers, id, row, dialog } = await stocktakeDialog(page, request)
  const path = `/api/spare-parts/${id}/movements`
  const quantity = dialog.getByLabel('数量', { exact: true })
  await expect(quantity).toHaveValue('')
  await quantity.fill('0')
  const incoming = await request.post(path, { headers, data: { movement_type: 'IN', qty: 2 } })
  expect(incoming.status()).toBe(200)
  const sent: unknown[] = []
  page.on('request', r => { if (r.url().endsWith(path) && r.method() === 'POST') sent.push(r.postDataJSON()) })
  for (let attempt = 0; attempt < 2; attempt++) {
    const rejected = page.waitForResponse(r => r.url().endsWith(path) && r.request().method() === 'POST')
    await dialog.getByRole('button', { name: /^(?:loading )?OK$/ }).click()
    expect((await rejected).status()).toBe(409)
    await expect(dialog).toBeVisible()
    await expect(quantity).toHaveValue(/^0(?:\.0+)?$/)
    await expect(dialog.getByText(/盘点基准库存：10\.00/)).toBeVisible()
    expect(sent).toHaveLength(attempt + 1)
    expect(sent[attempt]).toMatchObject({ movement_type: 'ADJUST', expected_stock_revision: 0, qty: 0 })
  }
  let ledger = (await (await request.get(path, { headers })).json()).data.items
  expect(ledger).toHaveLength(1)
  await dialog.getByRole('button', { name: '关闭并刷新库存', exact: true }).click()
  await expect(dialog).not.toBeVisible()
  await expect(row.getByRole('cell').nth(4)).toHaveText(/12\.00/)
  await row.getByRole('button', { name: '出入库' }).click()
  await dialog.getByText('出库', { exact: true }).click()
  await page.getByTitle('盘点调整', { exact: true }).click()
  await expect(dialog.getByText(/盘点基准库存：12\.00/)).toBeVisible()
  await expect(quantity).toHaveValue('')
  await dialog.getByRole('button', { name: /^(?:loading )?OK$/ }).click()
  await expect(dialog.locator('.ant-form-item-explain-error')).toBeVisible()
  expect(sent).toHaveLength(2)
  await quantity.fill('11')
  const saved = page.waitForResponse(r => r.url().endsWith(path) && r.request().method() === 'POST')
  await dialog.getByRole('button', { name: /^(?:loading )?OK$/ }).click()
  expect((await saved).status()).toBe(200)
  await expect(dialog).not.toBeVisible()
  expect(sent).toHaveLength(3)
  ledger = (await (await request.get(path, { headers })).json()).data.items
  expect(ledger).toHaveLength(2)
  expect(ledger[0].movement_type).toBe('ADJUST')
  expect(Number(ledger[0].qty)).toBe(11)
  const current = (await (await request.get(`/api/spare-parts/${id}`, { headers })).json()).data
  expect(Number(current.stock_qty)).toBe(11)
  expect(current.stock_revision).toBe(ledger[0].id)
})

test('same quantity after transfers still conflicts and cancel clears the old stocktake', async ({ page, request }) => {
  const { headers, id, dialog, row } = await stocktakeDialog(page, request)
  await dialog.getByLabel('数量', { exact: true }).fill('9')
  const path = `/api/spare-parts/${id}/movements`
  for (const movement_type of ['IN', 'OUT']) {
    const moved = await request.post(path, { headers, data: { movement_type, qty: 2 } })
    expect(moved.status()).toBe(200)
  }
  const rejected = page.waitForResponse(r => r.url().endsWith(path) && r.request().method() === 'POST')
  await dialog.getByRole('button', { name: /^(?:loading )?OK$/ }).click()
  expect((await rejected).status()).toBe(409)
  await expect(dialog.getByLabel('数量', { exact: true })).toHaveValue(/^9(?:\.0+)?$/)
  const current = (await (await request.get(`/api/spare-parts/${id}`, { headers })).json()).data
  expect(Number(current.stock_qty)).toBe(10)
  expect((await (await request.get(path, { headers })).json()).data.items).toHaveLength(2)
  await dialog.getByRole('button', { name: 'Cancel', exact: true }).click()
  await expect(dialog).not.toBeVisible()
  await row.getByRole('button', { name: '出入库' }).click()
  await dialog.getByText('出库', { exact: true }).click()
  await page.getByTitle('盘点调整', { exact: true }).click()
  await expect(dialog.getByLabel('数量', { exact: true })).toHaveValue('')
})

test('pending movement keeps its dialog fixed until the actual response arrives', async ({ page, request }) => {
  const { id, dialog } = await stocktakeDialog(page, request)
  await dialog.getByTitle('盘点调整', { exact: true }).click()
  await page.getByTitle('出库', { exact: true }).click()
  await dialog.getByLabel('数量', { exact: true }).fill('2')
  const path = `/api/spare-parts/${id}/movements`
  let release!: () => void
  let committed!: () => void
  const held = new Promise<void>(resolve => { release = resolve })
  const entered = new Promise<void>(resolve => { committed = resolve })
  await page.route(`**${path}`, async route => {
    const response = await route.fetch()
    expect(response.status()).toBe(200)
    committed()
    await held
    await route.fulfill({ response })
  })
  const completed = page.waitForResponse(r => r.url().endsWith(path) && r.request().method() === 'POST')
  try {
    await dialog.getByRole('button', { name: /^(?:loading )?OK$/ }).click()
    await entered
    await expect(dialog.getByRole('button', { name: 'Cancel', exact: true })).toBeDisabled()
    await expect(dialog.getByLabel('数量', { exact: true })).toBeDisabled()
    await page.keyboard.press('Escape')
    await expect(dialog).toBeVisible()
  } finally {
    release()
    await completed
  }
  await expect(dialog).not.toBeVisible()
})
