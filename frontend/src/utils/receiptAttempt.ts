/** Persist before POST so a lost response can be confirmed with the same identity. */
export interface ReceiptAttempt { requestId: string; quantity: number }
type AttemptStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>
const key = (username: string, purchaseId: number) => {
  if (!username || !Number.isSafeInteger(purchaseId) || purchaseId <= 0) throw new Error('无法识别当前用户或采购单')
  return `purchase-receipt:${encodeURIComponent(username)}:${purchaseId}`
}
const validQuantity = (n: unknown): n is number => typeof n === 'number' && Number.isFinite(n)
  && n > 0 && n <= 99999999.99 && Math.abs(n * 100 - Math.round(n * 100)) < 0.000001
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
export function loadReceiptAttempt(storage: AttemptStorage, username: string, purchaseId: number): ReceiptAttempt | null {
  const raw = storage.getItem(key(username, purchaseId))
  if (raw === null) return null
  const attempt = JSON.parse(raw)
  if (!attempt || !uuid.test(attempt.requestId) || !validQuantity(attempt.quantity)) {
    throw new Error('待确认收货记录损坏，请先核对采购单和库存流水')
  }
  return { requestId: attempt.requestId, quantity: attempt.quantity }
}
export function getReceiptAttempt(storage: AttemptStorage, username: string, purchaseId: number, quantity: number, displayed?: ReceiptAttempt | null): ReceiptAttempt {
  // A stale tab must confirm what it displays, even if another tab cleared X
  // or started Y. Replaying X is safe and must never regenerate its identity.
  if (displayed) return displayed
  const previous = loadReceiptAttempt(storage, username, purchaseId)
  if (previous) {
    if (previous.quantity !== quantity) throw new Error('已有其他数量的待确认收货，请先确认原记录')
    return previous
  }
  if (!validQuantity(quantity)) throw new Error('入库数量须为正数且最多两位小数')
  const attempt = { requestId: crypto.randomUUID(), quantity }
  storage.setItem(key(username, purchaseId), JSON.stringify(attempt))
  return attempt
}
export function clearReceiptAttempt(storage: AttemptStorage, username: string, purchaseId: number, requestId: string): void {
  if (loadReceiptAttempt(storage, username, purchaseId)?.requestId === requestId) {
    storage.removeItem(key(username, purchaseId))
  }
}
/** Only an explicit user decision may discard unconfirmed or corrupted evidence. */
export function receiptAttemptRaw(storage: AttemptStorage, username: string, purchaseId: number): string | null {
  return storage.getItem(key(username, purchaseId))
}
export function discardReceiptAttempt(storage: AttemptStorage, username: string, purchaseId: number, reviewedRaw: string | null): void {
  const storageKey = key(username, purchaseId)
  if (reviewedRaw === undefined || storage.getItem(storageKey) !== reviewedRaw) {
    throw new Error('待确认记录已变化，请重新打开并核对，已保留新记录')
  }
  storage.removeItem(storageKey)
}
export function receiptAccountToken(storage: Pick<Storage, 'getItem'>, username: string, token: string | null): string {
  if (!username || !token || storage.getItem('username') !== username || storage.getItem('token') !== token) {
    throw new Error('登录账户已变化，请刷新页面后使用原账户确认收货')
  }
  return token
}
