import { useEffect, useState } from 'react'
import { Card, Table, Tag, Space, Input, Button, Typography } from 'antd'
import { AuditOutlined, ReloadOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { auditApi, AuditEntry } from '../api'
import { useAuthStore } from '../stores/auth'

const { Text } = Typography

const ACTION_LABEL: Record<string, { label: string; color: string }> = {
  'defect.create': { label: '上报缺陷', color: 'red' },
  'defect.assign': { label: '派工', color: 'blue' },
  'defect.verify_pass': { label: '验收通过', color: 'green' },
  'defect.verify_reject': { label: '验收驳回', color: 'orange' },
  'wt.issue': { label: '工作票签发', color: 'cyan' },
  'wt.permit': { label: '许可开工', color: 'blue' },
  'wt.close': { label: '工作票归档', color: 'green' },
  'user.create': { label: '创建用户', color: 'purple' },
  'user.reset_password': { label: '重置密码', color: 'magenta' },
}

export default function AuditLog() {
  const role = useAuthStore((s) => s.role)
  const [rows, setRows] = useState<AuditEntry[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [keyword, setKeyword] = useState('')

  const load = () => {
    setLoading(true)
    auditApi.list({ page, page_size: 50, keyword: keyword || undefined })
      .then((r) => { setRows(r.data.items); setTotal(r.data.total) })
      .finally(() => setLoading(false))
  }
  useEffect(load, [page, keyword])

  if (role !== 'ADMIN') {
    return <Card><Text type="warning">仅管理员可查看审计日志。</Text></Card>
  }

  const actionTag = (action: string) => {
    const cfg = ACTION_LABEL[action]
    return cfg
      ? <Tag color={cfg.color}>{cfg.label}</Tag>
      : <Tag>{action}</Tag>
  }

  return (
    <Card
      title={<Space><AuditOutlined />审计日志</Space>}
      extra={
        <Space>
          <Input.Search placeholder="单号 / 摘要" allowClear style={{ width: 240 }}
            onSearch={(v) => { setPage(1); setKeyword(v) }} />
          <Button icon={<ReloadOutlined />} onClick={load} />
        </Space>
      }
    >
      <Table
        rowKey="id"
        loading={loading}
        dataSource={rows}
        pagination={{ current: page, pageSize: 50, total, onChange: setPage }}
        columns={[
          { title: '时间', dataIndex: 'created_at', width: 160,
            render: (v) => dayjs(v).format('YYYY-MM-DD HH:mm:ss') },
          { title: '操作人', dataIndex: 'actor', width: 120 },
          { title: '动作', dataIndex: 'action', width: 160, render: (v) => actionTag(v) },
          { title: '对象', width: 160, render: (_: any, r: AuditEntry) => (
            <Space size={4}>
              {r.target_type && <Tag>{r.target_type}</Tag>}
              {r.target_no && <Text code style={{ fontSize: 12 }}>{r.target_no}</Text>}
            </Space>
          ) },
          { title: '摘要', dataIndex: 'summary', ellipsis: true },
        ]}
        scroll={{ x: 1000 }}
      />
    </Card>
  )
}
