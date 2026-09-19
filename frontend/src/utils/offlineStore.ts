/**
 * 离线点检 IndexedDB 暂存（v3.0）
 *
 * 当点检员在弱网/无网现场录入测点结果时，先写入 IDB 队列；
 * 恢复网络后由 syncQueue() 自动批量重放 POST /api/tasks/{id}/records。
 *
 * 同时提供任务/测点的离线缓存表 `cached_tasks`，供首页"我的点检"在离线时仍可看到任务。
 */

const DB_NAME = 'equipment-inspection-offline'
const DB_VERSION = 1

interface DB {
  db: IDBDatabase | null
}

const state: DB = { db: null }

export interface QueuedRecord {
  id?: number               // IDB 自增主键
  task_id: number
  point_id: number
  status: 'NORMAL' | 'ABNORMAL' | 'SEVERE'
  owner?: string            // 入队账户；旧数据缺失时保留待人工核对
  blocked?: boolean         // 业务冲突/无效输入停止自动重试
  readings?: Record<string, any>
  finding?: string
  photo_url?: string
  created_at: string        // ISO
  retry: number             // 失败次数
  last_error?: string
}

export interface CachedTask {
  id: number
  task_no?: string
  route_id?: number
  scheduled_at?: string
  status?: string
  pending_points?: Array<{ id: number; equipment_name?: string; sequence?: number; standard?: string; check_items?: any[] }>
  cached_at: string
}

function openDB(): Promise<IDBDatabase> {
  if (state.db) return Promise.resolve(state.db)
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION)
    req.onupgradeneeded = () => {
      const db = req.result
      if (!db.objectStoreNames.contains('queue')) {
        const s = db.createObjectStore('queue', { keyPath: 'id', autoIncrement: true })
        s.createIndex('task_id', 'task_id', { unique: false })
      }
      if (!db.objectStoreNames.contains('cached_tasks')) {
        db.createObjectStore('cached_tasks', { keyPath: 'id' })
      }
    }
    req.onsuccess = () => { state.db = req.result; resolve(req.result) }
    req.onerror = () => reject(req.error)
  })
}

export async function enqueueRecord(record: Omit<QueuedRecord, 'id' | 'retry' | 'created_at'>): Promise<number> {
  const owner = localStorage.getItem('username')
  if (!owner) throw new Error('请先登录后再录入离线记录')
  const db = await openDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction('queue', 'readwrite')
    const store = tx.objectStore('queue')
    const req = store.add({
      ...record,
      owner,
      blocked: false,
      retry: 0,
      created_at: new Date().toISOString(),
    } as QueuedRecord)
    tx.oncomplete = () => resolve(req.result as number)
    tx.onabort = () => reject(tx.error)
    req.onerror = () => reject(req.error)
  })
}

export async function listQueue(): Promise<QueuedRecord[]> {
  const db = await openDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction('queue', 'readonly')
    const req = tx.objectStore('queue').getAll()
    req.onsuccess = () => resolve(req.result || [])
    req.onerror = () => reject(req.error)
  })
}

export async function removeQueued(id: number): Promise<void> {
  const db = await openDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction('queue', 'readwrite')
    tx.objectStore('queue').delete(id)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
}

export async function bumpRetry(id: number, err: string, blocked = false): Promise<void> {
  const db = await openDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction('queue', 'readwrite')
    const store = tx.objectStore('queue')
    const req = store.get(id)
    req.onsuccess = () => {
      const r = req.result as QueuedRecord | undefined
      if (!r) return resolve()
      r.retry = (r.retry || 0) + 1
      r.last_error = err
      r.blocked = blocked
      store.put(r)
    }
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
}

export async function cacheTask(task: CachedTask): Promise<void> {
  const db = await openDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction('cached_tasks', 'readwrite')
    tx.objectStore('cached_tasks').put({ ...task, cached_at: new Date().toISOString() })
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
}

export async function listCachedTasks(): Promise<CachedTask[]> {
  const db = await openDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction('cached_tasks', 'readonly')
    const req = tx.objectStore('cached_tasks').getAll()
    req.onsuccess = () => resolve(req.result || [])
    req.onerror = () => reject(req.error)
  })
}

export async function clearCachedTasks(): Promise<void> {
  const db = await openDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction('cached_tasks', 'readwrite')
    tx.objectStore('cached_tasks').clear()
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
}

type SyncResult = { success: number; failed: number; remaining: number }
let inFlight: Promise<SyncResult> | null = null

/** 同一页面的自动/手动同步共享批次，跨标签页由后端幂等保护。 */
export function syncQueue(): Promise<SyncResult> {
  if (!inFlight) inFlight = syncBatch().finally(() => { inFlight = null })
  return inFlight
}

async function syncBatch(): Promise<SyncResult> {
  const queued = await listQueue()
  let success = 0
  let failed = 0
  const token = localStorage.getItem('token')
  const owner = localStorage.getItem('username')
  if (!token || !owner) return { success: 0, failed: 0, remaining: queued.length }
  for (const item of queued) {
    if (item.blocked || item.owner !== owner) continue
    if (localStorage.getItem('token') !== token || localStorage.getItem('username') !== owner) break
    try {
      const resp = await fetch(`/api/tasks/${item.task_id}/records`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          point_id: item.point_id,
          status: item.status,
          readings: item.readings,
          finding: item.finding,
          photo_url: item.photo_url,
        }),
      })
      if (!resp.ok) {
        const text = await resp.text().catch(() => '')
        const blocked = [400, 404, 409, 422].includes(resp.status)
        await bumpRetry(item.id!, `HTTP ${resp.status} ${text}`, blocked)
        failed += 1
        if (resp.status === 401 || resp.status === 403) break
        continue
      }
      await removeQueued(item.id!)
      success += 1
    } catch (e: any) {
      await bumpRetry(item.id!, e?.message || String(e))
      failed += 1
    }
  }
  const remaining = (await listQueue()).length
  return { success, failed, remaining }
}

export function isOnline(): boolean {
  return typeof navigator !== 'undefined' ? navigator.onLine : true
}

/** 一次性绑定全局 online 监听，online 时自动 sync */
let bound = false
export function autoSync(onResult?: (r: { success: number; failed: number; remaining: number }) => void) {
  if (bound || typeof window === 'undefined') return
  bound = true
  const trigger = async () => {
    if (!isOnline()) return
    const r = await syncQueue().catch(() => ({ success: 0, failed: 0, remaining: -1 }))
    onResult?.(r)
  }
  window.addEventListener('online', trigger)
  // 启动时先跑一次
  setTimeout(trigger, 1500)
}
