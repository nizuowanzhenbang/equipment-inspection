import { randomUUID } from 'node:crypto'
import { expect, test, type Page } from '@playwright/test'

async function login(page: Page) {
  await page.goto('/login')
  await page.getByPlaceholder('用户名', { exact: true }).fill('admin')
  await page.getByPlaceholder('密码', { exact: true }).fill('admin123')
  await page.getByRole('button', { name: /^登\s*录$/ }).click()
  await expect(page).toHaveURL(/\/dashboard$/)
}

async function expectPaintedCharts(page: Page, count: number) {
  const charts = page.locator('.echarts-for-react canvas')
  await expect(charts).toHaveCount(count)
  for (let index = 0; index < count; index++) {
    await expect.poll(() => charts.nth(index).evaluate((canvas: HTMLCanvasElement) => {
      const context = canvas.getContext('2d')
      if (!context || canvas.width < 100 || canvas.height < 100) return false
      const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data
      let painted = 0
      for (let offset = 3; offset < pixels.length; offset += 4) {
        if (pixels[offset] > 0 && ++painted > 100) return true
      }
      return false
    })).toBe(true)
    // ECharts animates on its canvas; DOM visibility alone can capture an empty first frame.
    let previous = ''
    let stableSamples = 0
    await expect.poll(async () => {
      const current = await charts.nth(index).evaluate((canvas: HTMLCanvasElement) => canvas.toDataURL())
      stableSamples = current === previous ? stableSamples + 1 : 0
      previous = current
      return stableSamples
    }, { intervals: [100] }).toBeGreaterThanOrEqual(3)
  }
}

test('guarded routes, menu navigation, refresh and logout remain compatible', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('/reports')
  await expect(page).toHaveURL(/\/login$/)
  await login(page)
  await page.getByRole('menuitem', { name: '设备台账' }).click()
  await expect(page).toHaveURL(/\/equipments$/)
  await page.reload()
  await expect(page.getByRole('button', { name: /登\s*记/ })).toBeVisible()
  await page.getByRole('button', { name: /退\s*出/ }).click()
  await expect(page).toHaveURL(/\/login$/)
  expect(await page.evaluate(() => localStorage.getItem('token'))).toBeNull()
  await page.goto('/equipments')
  await expect(page).toHaveURL(/\/login$/)
  expect(errors).toEqual([])
})

test('dashboard, reports and prediction charts render after the ECharts upgrade', async ({ page, request }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  const session = await request.post('/api/auth/login', { form: { username: 'admin', password: 'admin123' } })
  expect(session.status()).toBe(200)
  const { access_token } = await session.json()
  const created = await request.post('/api/equipments', {
    headers: { Authorization: `Bearer ${access_token}` },
    data: { name: `图表测试-${randomUUID().slice(0, 8)}`, equipment_system: 'AUXILIARY' },
  })
  expect(created.status()).toBe(200)
  const overview = page.waitForResponse(response => response.url().endsWith('/api/dashboard/overview'))
  await login(page)
  const overviewResponse = await overview
  expect(overviewResponse.status()).toBe(200)
  const total = (await overviewResponse.json()).data.equipment.total
  expect(total).toBeGreaterThan(0)
  await expect(page.locator('.ant-statistic').filter({ hasText: '设备总数' }).locator('.ant-statistic-content-value')).toHaveText(String(total))
  await expect(page.getByText('近 30 天缺陷新增/关闭趋势', { exact: true })).toBeVisible()
  await expectPaintedCharts(page, 2)
  await page.screenshot({ path: 'test-results/dashboard-upgraded.png', fullPage: true })

  const availability = page.waitForResponse(response => response.url().includes('/api/reports/equipment-availability?'))
  await page.getByRole('menuitem', { name: '报表导出' }).click()
  const availabilityResponse = await availability
  expect(availabilityResponse.status()).toBe(200)
  expect((await availabilityResponse.json()).data.by_system.length).toBeGreaterThan(0)
  await expect(page).toHaveURL(/\/reports$/)
  await expect(page.getByText('近 6 个月缺陷处理趋势', { exact: true })).toBeVisible()
  await expectPaintedCharts(page, 2)
  await page.screenshot({ path: 'test-results/reports-upgraded.png', fullPage: true })

  const ranking = page.waitForResponse(response => response.url().includes('/api/predictive/ranking?'))
  await page.getByRole('menuitem', { name: '预测维护' }).click()
  const rankingResponse = await ranking
  expect(rankingResponse.status()).toBe(200)
  expect((await rankingResponse.json()).data.length).toBeGreaterThan(0)
  await expect(page).toHaveURL(/\/predictive$/)
  await expect(page.getByText('风险分布（健康度 × 风险分）', { exact: true })).toBeVisible()
  await expectPaintedCharts(page, 1)
  await page.screenshot({ path: 'test-results/predictive-upgraded.png', fullPage: true })
  expect(errors).toEqual([])
})
