import { randomUUID } from 'node:crypto'
import { expect, test } from '@playwright/test'

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
  await dialog.getByRole('button', { name: 'OK', exact: true }).click()
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
