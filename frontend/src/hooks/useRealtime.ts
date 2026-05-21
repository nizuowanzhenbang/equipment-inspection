import { useEffect, useRef } from 'react'
import { notification } from 'antd'

export interface RealtimeEvent {
  event: string
  ts: string
  data: any
}

export function useRealtime(enabled: boolean, onEvent?: (e: RealtimeEvent) => void) {
  const wsRef = useRef<WebSocket | null>(null)
  const retryRef = useRef<number>(0)
  const timerRef = useRef<number | null>(null)

  useEffect(() => {
    if (!enabled) return
    const token = localStorage.getItem('token')
    if (!token) return

    const connect = () => {
      const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
      // Vite 代理转发：/ws → 后端 8003
      const url = `${proto}://${window.location.host}/ws?token=${encodeURIComponent(token)}`
      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => {
        retryRef.current = 0
      }
      ws.onmessage = (ev) => {
        try {
          const msg: RealtimeEvent = JSON.parse(ev.data)
          handleNotify(msg)
          onEvent?.(msg)
        } catch {}
      }
      ws.onerror = () => { /* swallow, onclose will retry */ }
      ws.onclose = (ev) => {
        wsRef.current = null
        if (ev.code === 4401) return  // 鉴权失败不重试
        retryRef.current += 1
        const delay = Math.min(30000, 1000 * 2 ** retryRef.current)
        timerRef.current = window.setTimeout(connect, delay)
      }
    }
    connect()

    return () => {
      if (timerRef.current) window.clearTimeout(timerRef.current)
      wsRef.current?.close()
      wsRef.current = null
    }
  }, [enabled])
}

function handleNotify(msg: RealtimeEvent) {
  const { event, data } = msg
  switch (event) {
    case 'defect.critical_created':
      notification.error({
        message: `紧急缺陷：${data.equipment_name || data.equipment_code || ''}`,
        description: `${data.defect_no} ${data.title}`,
        duration: 8,
      })
      break
    case 'defect.overdue_swept':
      notification.warning({
        message: `${data.count} 条缺陷已超期`,
        description: `示例：${(data.defects || []).slice(0, 3).join('、')}`,
        duration: 6,
      })
      break
    case 'task.missed_swept':
      notification.warning({
        message: `${data.count} 条任务被标记漏检`,
        description: `示例：${(data.tasks || []).slice(0, 3).join('、')}`,
        duration: 6,
      })
      break
    case 'defect.safety_synced':
      notification.success({
        message: '隐患单已联动',
        description: `${data.defect_no} → ${data.hazard_no || '隐患单已建'}`,
        duration: 4,
      })
      break
    case 'defect.safety_sync_failed':
      notification.error({
        message: '隐患联动失败',
        description: `${data.defect_no}：${data.error || '未知错误'}`,
        duration: 6,
      })
      break
    case 'system.welcome':
      // 静默
      break
  }
}
