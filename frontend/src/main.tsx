import React from 'react'
import ReactDOM from 'react-dom/client'
import { ConfigProvider, notification } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import 'antd/dist/reset.css'
import App from './App'
import { autoSync } from './utils/offlineStore'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ConfigProvider locale={zhCN} theme={{ token: { colorPrimary: '#fa541c' } }}>
      <App />
    </ConfigProvider>
  </React.StrictMode>,
)

// PWA：注册 Service Worker（仅在生产 https 或 localhost 下生效）
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {})
  })
}

// v3.0 离线点检：恢复网络后自动重放暂存的点检记录
autoSync((r) => {
  if (r.success > 0 || r.failed > 0) {
    notification.info({
      message: '离线点检同步',
      description: `已上传 ${r.success} 条，失败 ${r.failed} 条，剩余 ${r.remaining} 条待重试`,
      placement: 'bottomRight',
    })
  }
})
