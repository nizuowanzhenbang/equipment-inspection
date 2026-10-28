import { randomUUID } from 'node:crypto'
import { expect, test } from '@playwright/test'

test('saved skipped safety reason is visible after reloading daily defects', async ({ page, request }) => {
  const login = await request.post('/api/auth/login', { form: { username: 'admin', password: 'admin123' } })
  expect(login.ok()).toBeTruthy()
  const headers = { Authorization: `Bearer ${(await login.json()).access_token}` }
  const equipment = await request.post('/api/equipments', { headers, data: {
    name: `原因核对-${randomUUID()}`, equipment_system: 'BOILER', criticality: 'A',
  } })
  expect(equipment.ok()).toBeTruthy()
  const title = `联动原因-${randomUUID()}`
  const created = await request.post('/api/defects', { headers, data: {
    equipment_id: (await equipment.json()).data.id, title, severity: 'CRITICAL',
  } })
  expect(created.ok()).toBeTruthy()
  await page.goto('/login')
  await page.getByPlaceholder('用户名', { exact: true }).fill('admin')
  await page.getByPlaceholder('密码', { exact: true }).fill('admin123')
  await page.getByRole('button', { name: /^登\s*录$/ }).click()
  await expect(page).toHaveURL(/\/dashboard$/)
  await page.goto('/defects')
  await page.reload()
  const row = page.getByRole('row').filter({ hasText: title })
  await expect(row.getByText('跳过', { exact: true })).toBeVisible()
  await expect(row.getByText('SAFETY_SYSTEM_URL 未配置', { exact: true })).toBeVisible()
})
