/* 简单 Service Worker：缓存核心 shell + 优先网络回退缓存 */
const CACHE = 'eq-inspect-v1'
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

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url)
  // 仅 GET + 同源
  if (event.request.method !== 'GET' || url.origin !== self.location.origin) return
  // API 走网络优先（不缓存避免脏数据）
  if (url.pathname.startsWith('/api') || url.pathname.startsWith('/ws')) return

  event.respondWith(
    fetch(event.request).then((res) => {
      // 静态资源 + manifest + 图标缓存一份
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
