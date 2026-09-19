/**
 * v3.0 离线点检队列页
 * - 显示 IndexedDB 中未同步的点检记录
 * - 一键重试同步；现场离线录入入口（按任务 + 测点 + 状态）
 */
import { useEffect, useState } from 'react'
import {
  Card, Table, Tag, Button, Space, message, Form, Input, Select, Modal, Badge, Typography, Statistic, Row, Col, Alert,
} from 'antd'
import { CloudUploadOutlined, ReloadOutlined, PlusOutlined, DeleteOutlined, WifiOutlined, DisconnectOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'
import {
  listQueue, syncQueue, removeQueued, enqueueRecord, isOnline,
} from '../utils/offlineStore'
import type { QueuedRecord } from '../utils/offlineStore'


dayjs.extend(relativeTime)
const { Text } = Typography

export default function OfflineQueue() {
  const [rows, setRows] = useState<QueuedRecord[]>([])
  const [loading, setLoading] = useState(false)
  const [online, setOnline] = useState(isOnline())
  const [createOpen, setCreateOpen] = useState(false)
  const [form] = Form.useForm()

  const reload = async () => {
    setLoading(true)
    try {
      setRows(await listQueue())
    } finally { setLoading(false) }
  }

  useEffect(() => {
    reload()
    const on = () => setOnline(true)
    const off = () => setOnline(false)
    window.addEventListener('online', on)
    window.addEventListener('offline', off)
    return () => {
      window.removeEventListener('online', on)
      window.removeEventListener('offline', off)
    }
  }, [])

  const sync = async () => {
    if (!online) { message.warning('当前离线，无法同步'); return }
    setLoading(true)
    try {
      const r = await syncQueue()
      message.success(`同步完成：成功 ${r.success}，失败 ${r.failed}，剩余 ${r.remaining}`)
      reload()
    } catch (e: any) {
      message.error(e?.message || '同步失败')
    } finally { setLoading(false) }
  }

  const remove = async (id?: number) => {
    if (id === undefined) return
    await removeQueued(id)
    reload()
  }

  const onCreate = async () => {
    const v = await form.validateFields()
    try {
      await enqueueRecord({
        task_id: Number(v.task_id),
        point_id: Number(v.point_id),
        status: v.status,
        readings: v.readings_text ? safeJson(v.readings_text) : undefined,
        finding: v.finding,
      })
      message.success('已加入离线队列')
      setCreateOpen(false); form.resetFields()
      reload()
    } catch (e: any) { message.error(e?.message || '入队失败') }
  }

  const failedCount = rows.filter((r) => r.retry > 0).length

  return (
    <Card
      title={<Space>
        {online ? <Tag icon={<WifiOutlined />} color="green">在线</Tag> : <Tag icon={<DisconnectOutlined />} color="red">离线</Tag>}
        离线点检队列
      </Space>}
      extra={
        <Space>
          <Button icon={<ReloadOutlined />} onClick={reload} />
          <Button icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>离线录入</Button>
          <Button type="primary" icon={<CloudUploadOutlined />} loading={loading} disabled={!online || rows.length === 0} onClick={sync}>
            一键同步</Button>
        </Space>
      }
    >
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="弱网/无网现场也可录入点检记录：所有结果先入 IndexedDB 队列，恢复网络后自动批量上传。"
        description="仅同步当前账户的记录。内容冲突或无效记录保留待核对；旧版无账户记录请核实来源后重新录入。删除前请确认已保存原始信息。"
      />
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}><Card><Statistic title="待同步" value={rows.length} /></Card></Col>
        <Col span={6}><Card><Statistic title="重试过" value={failedCount} valueStyle={{ color: failedCount > 0 ? '#cf1322' : undefined }} /></Card></Col>
        <Col span={6}><Card><Statistic title="网络" value={online ? '在线' : '离线'} valueStyle={{ color: online ? '#3f8600' : '#cf1322' }} /></Card></Col>
        <Col span={6}><Card><Statistic title="最旧记录" value={rows[0]?.created_at ? dayjs(rows[0].created_at).fromNow?.() || rows[0].created_at : '-'} /></Card></Col>
      </Row>
      <Table
        rowKey="id"
        loading={loading}
        dataSource={rows}
        pagination={false}
        columns={[
          { title: '#', dataIndex: 'id', width: 60 },
          { title: '任务', dataIndex: 'task_id', width: 80 },
          { title: '测点', dataIndex: 'point_id', width: 80 },
          { title: '录入账户', dataIndex: 'owner', render: (v) => v || '旧记录：待核对' },
          { title: '同步状态', render: (_: any, r: QueuedRecord) => r.blocked
            ? <Tag color="red">待人工核对</Tag>
            : r.owner !== localStorage.getItem('username') ? <Tag>等待原账户</Tag> : <Tag color="blue">待同步</Tag> },
          { title: '状态', dataIndex: 'status', width: 100,
            render: (s) => <Tag color={s === 'NORMAL' ? 'green' : s === 'ABNORMAL' ? 'orange' : s === 'SEVERE' ? 'red' : 'default'}>{s}</Tag> },
          { title: '发现', dataIndex: 'finding', ellipsis: true },
          { title: '重试', dataIndex: 'retry', width: 80,
            render: (n) => n > 0 ? <Badge count={n} /> : '-' },
          { title: '最后错误', dataIndex: 'last_error', ellipsis: true, render: (v) => v ? <Text type="danger" style={{ fontSize: 12 }}>{v}</Text> : '-' },
          { title: '加入时间', dataIndex: 'created_at', width: 160, render: (v) => dayjs(v).format('MM-DD HH:mm:ss') },
          { title: '操作', width: 80, fixed: 'right' as const,
            render: (_: any, r: QueuedRecord) => <Button size="small" danger icon={<DeleteOutlined />} onClick={() => remove(r.id)} /> },
        ]}
        locale={{ emptyText: '队列为空' }}
      />

      <Modal title="离线录入点检结果" open={createOpen} onOk={onCreate} onCancel={() => setCreateOpen(false)} width={520}>
        <Form form={form} layout="vertical" initialValues={{ status: 'NORMAL' }}>
          <Form.Item name="task_id" label="任务 ID" rules={[{ required: true }]}>
            <Input placeholder="例如 12" />
          </Form.Item>
          <Form.Item name="point_id" label="测点 ID" rules={[{ required: true }]}>
            <Input placeholder="例如 45" />
          </Form.Item>
          <Form.Item name="status" label="状态" rules={[{ required: true }]}>
            <Select options={[
              { label: '正常', value: 'NORMAL' },
              { label: '异常', value: 'ABNORMAL' },
              { label: '严重', value: 'SEVERE' },
            ]} />
          </Form.Item>
          <Form.Item name="finding" label="发现">
            <Input.TextArea rows={3} placeholder="例如：振动幅值 0.8mm/s" />
          </Form.Item>
          <Form.Item name="readings_text" label="读数（JSON，可选）">
            <Input.TextArea rows={2} placeholder='{"temperature": 78.5, "vibration": 0.8}' />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}

function safeJson(text: string): any {
  try { return JSON.parse(text) } catch { return { _raw: text } }
}
