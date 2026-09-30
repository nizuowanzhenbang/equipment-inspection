import { randomUUID } from 'node:crypto'
import { expect, test } from '@playwright/test'

// Synthetic demo accounts only. Run against an isolated, disposable Compose project.
test('browser login reads a persisted device through nginx and PostgreSQL', async ({ page, request }) => {
  const name = `CI-device-${randomUUID()}`
  const login = await request.post('/api/auth/login', {
    form: { username: 'admin', password: 'admin123' },
  })
  expect(login.status()).toBe(200)
  const { access_token } = await login.json()
  const created = await request.post('/api/equipments', {
    headers: { Authorization: `Bearer ${access_token}` },
    data: { name, equipment_system: 'AUXILIARY', criticality: 'B' },
  })
  expect(created.status()).toBe(200)

  await page.goto('/login')
  await page.getByPlaceholder('用户名', { exact: true }).fill('admin')
  await page.getByPlaceholder('密码', { exact: true }).fill('admin123')
  await page.getByRole('button', { name: '登录' }).click()
  await expect(page).toHaveURL(/\/dashboard$/)
  const equipmentResponse = page.waitForResponse(response =>
    response.url().includes('/api/equipments?') && response.request().method() === 'GET',
  )
  await page.goto('/equipments')
  expect((await equipmentResponse).status()).toBe(200)
  await expect(page.getByRole('cell', { name, exact: true })).toBeVisible()
  await page.screenshot({ path: 'test-results/equipment-list.png', fullPage: true })
})

test('anonymous and viewer requests cannot create devices', async ({ request }) => {
  const data = { name: `forbidden-${randomUUID()}`, equipment_system: 'AUXILIARY' }
  expect((await request.post('/api/equipments', { data })).status()).toBe(401)
  const login = await request.post('/api/auth/login', {
    form: { username: 'viewer', password: 'viewer123' },
  })
  expect(login.status()).toBe(200)
  const { access_token } = await login.json()
  const headers = { Authorization: `Bearer ${access_token}` }
  expect((await request.get('/api/equipments', { headers })).status()).toBe(200)
  expect((await request.post('/api/equipments', { headers, data })).status()).toBe(403)
  const result = await request.get('/api/equipments', { headers, params: { keyword: data.name } })
  expect((await result.json()).data.total).toBe(0)
})
