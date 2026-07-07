/* Service Worker v3.0
 * - 静态 shell 离线可用
 * - 点检任务 GET（/api/tasks 列表 + /api/tasks/{id} 详情 + /api/routes）走 stale-while-revalidate
 * - 其余 API 走网络优先（不缓存）
 * - 点检结果 POST 由前端 IndexedDB 自行排队，SW 不拦截
 */
const CACHE = 'eq-inspect-v2'
const SHELL = ['/', '/m/scan', '/manifest.webmanifest', '/icon-192.svg', '/icon-512.svg']

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).catch(() => null))
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  )
  self.clients.claim()
})

function isCacheableTaskGet(url) {
  return url.pathname === '/api/tasks' ||
    /^\/api\/tasks\/\d+(\/.*)?$/.test(url.pathname) ||
    url.pathname === '/api/routes'
}

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url)
  if (event.request.method !== 'GET' || url.origin !== self.location.origin) return
  if (url.pathname.startsWith('/ws')) return

  // 任务相关 GET：stale-while-revalidate
  if (url.pathname.startsWith('/api/') && isCacheableTaskGet(url)) {
    event.respondWith((async () => {
      const cached = await caches.match(event.request)
      const networkFetch = fetch(event.request).then((res) => {
        if (res.ok) caches.open(CACHE).then((c) => c.put(event.request, res.clone()))
        return res
      }).catch(() => null)
      return cached || (await networkFetch) || new Response(JSON.stringify({
        code: 0, message: '离线模式：返回空数据', data: { items: [], total: 0 },
      }), { headers: { 'Content-Type': 'application/json' } })
    })())
    return
  }

  // 其他 API：网络优先，不缓存
  if (url.pathname.startsWith('/api/')) return

  // 静态资源：网络优先 + 回退缓存
  event.respondWith(
    fetch(event.request).then((res) => {
      const copy = res.clone()
      if (res.ok && (url.pathname.endsWith('.js') || url.pathname.endsWith('.css') ||
        url.pathname.endsWith('.svg') || url.pathname.endsWith('.webmanifest') ||
        url.pathname === '/')) {
        caches.open(CACHE).then((c) => c.put(event.request, copy))
      }
      return res
    }).catch(() => caches.match(event.request).then((m) => m || caches.match('/')))
  )
})
