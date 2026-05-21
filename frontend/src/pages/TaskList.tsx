import { useEffect, useState } from 'react'
import {
  Card, Table, Tag, Button, Space, Select, Drawer, List, Modal,
  Form, Input, Radio, message, Progress, Typography, Upload,
} from 'antd'
import { AuditOutlined, ReloadOutlined, UploadOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { taskApi, uploadApi } from '../api'
import { useAuthStore, canInspect } from '../stores/auth'
import { InspectionTask, TaskStatus, PointStatus, TASK_STATUS_LABEL } from '../types'

const { Text } = Typography

export default function TaskList() {
  const role = useAuthStore((s) => s.role)
  const inspector = canInspect(role)

  const [rows, setRows] = useState<InspectionTask[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [statusFilter, setStatusFilter] = useState<TaskStatus | undefined>()

  const [drawerOpen, setDrawerOpen] = useState(false)
  const [detail, setDetail] = useState<any>(null)
  const [recordOpen, setRecordOpen] = useState(false)
  const [currentPoint, setCurrentPoint] = useState<any>(null)
  const [form] = Form.useForm()

  const load = () => {
    setLoading(true)
    taskApi.list({ page, page_size: 15, status: statusFilter })
      .then((r) => { setRows(r.data.items); setTotal(r.data.total) })
      .finally(() => setLoading(false))
  }
  useEffect(load, [page, statusFilter])

  const openDetail = async (id: number) => {
    const res = await taskApi.get(id)
    setDetail(res.data)
    setDrawerOpen(true)
  }

  const startTask = async () => {
    await taskApi.start(detail.id)
    message.success('已开始')
    openDetail(detail.id)
    load()
  }

  const submitRecord = async () => {
    const v = await form.validateFields()
    try {
      await taskApi.submitRecord(detail.id, { point_id: currentPoint.id, ...v })
      message.success('已录入')
      setRecordOpen(false)
      form.resetFields()
      openDetail(detail.id)
      load()
    } catch (e: any) { message.error(e?.detail || '失败') }
  }

  const taskStatusTag = (s: TaskStatus) => {
    const color = s === 'COMPLETED' ? 'green' : s === 'IN_PROGRESS' ? 'blue' :
      s === 'MISSED' ? 'red' : s === 'CANCELLED' ? 'default' : 'orange'
    return <Tag color={color}>{TASK_STATUS_LABEL[s]}</Tag>
  }

  return (
    <Card title={<Space><AuditOutlined />点检任务</Space>}
      extra={
        <Space>
          <Select<TaskStatus | undefined>
            placeholder="状态" allowClear style={{ width: 130 }} value={statusFilter}
            onChange={(v) => { setPage(1); setStatusFilter(v) }}
            options={Object.entries(TASK_STATUS_LABEL).map(([k, v]) => ({ label: v, value: k }))}
          />
          <Button icon={<ReloadOutlined />} onClick={load} />
          <Button onClick={async () => { const r = await taskApi.sweepMissed(); message.success(`扫描完毕，标记 ${r.data.missed} 条漏检`); load() }}>
            扫描漏检
          </Button>
        </Space>
      }
    >
      <Table
        rowKey="id"
        loading={loading}
        dataSource={rows}
        pagination={{ current: page, pageSize: 15, total, onChange: setPage }}
        columns={[
          { title: '任务号', dataIndex: 'task_no', width: 170 },
          { title: '路线', dataIndex: 'route_name' },
          { title: '计划时间', dataIndex: 'scheduled_at', width: 160,
            render: (v) => dayjs(v).format('MM-DD HH:mm') },
          { title: '指派', dataIndex: 'assigned_to', width: 100 },
          { title: '状态', dataIndex: 'status', width: 100, render: (v) => taskStatusTag(v) },
          { title: '进度', width: 160, render: (_: any, r: InspectionTask) => (
            <Space size={4}>
              <Progress percent={r.total_points ? Math.round(r.record_count * 100 / r.total_points) : 0} size="small" style={{ width: 100 }} />
              <Text type="secondary" style={{ fontSize: 12 }}>{r.record_count}/{r.total_points}</Text>
            </Space>
          ) },
          { title: '异常', dataIndex: 'abnormal_count', width: 70,
            render: (v) => v > 0 ? <Tag color="red">{v}</Tag> : '-' },
          { title: '操作', width: 100, fixed: 'right' as const,
            render: (_: any, r: InspectionTask) => <Button size="small" onClick={() => openDetail(r.id)}>详情</Button> },
        ]}
        scroll={{ x: 1100 }}
      />

      <Drawer
        title={detail ? `${detail.task_no} · ${detail.route_name}` : '任务详情'}
        open={drawerOpen} onClose={() => setDrawerOpen(false)} width={680}
      >
        {detail && (
          <>
            <Space style={{ marginBottom: 12 }}>
              {taskStatusTag(detail.status)}
              <Text type="secondary">计划：{dayjs(detail.scheduled_at).format('YYYY-MM-DD HH:mm')}</Text>
              {detail.status === 'PENDING' && inspector && (
                <Button type="primary" size="small" onClick={startTask}>开始执行</Button>
              )}
            </Space>
            <Typography.Title level={5}>待执行测点（{(detail.pending_points || []).length}）</Typography.Title>
            <List
              dataSource={detail.pending_points || []}
              renderItem={(p: any) => (
                <List.Item
                  actions={inspector && detail.status !== 'COMPLETED' && detail.status !== 'CANCELLED' && detail.status !== 'MISSED' ? [
                    <Button size="small" type="primary" onClick={() => { setCurrentPoint(p); setRecordOpen(true) }}>录入</Button>,
                  ] : []}
                >
                  <List.Item.Meta
                    title={<Space><Tag>{p.point_no}</Tag>#{p.sequence} {p.equipment_name}<Text type="secondary">{p.equipment_code}</Text></Space>}
                    description={<>检查：{(p.check_items || []).map((c: any) => c.name).join('、')}{p.standard ? ` ｜ 标准：${p.standard}` : ''}</>}
                  />
                </List.Item>
              )}
            />
            <Typography.Title level={5} style={{ marginTop: 16 }}>已录入测点（{(detail.records || []).length}）</Typography.Title>
            <List
              dataSource={detail.records || []}
              renderItem={(r: any) => (
                <List.Item>
                  <List.Item.Meta
                    title={<Space>
                      <Tag color={r.status === 'NORMAL' ? 'green' : r.status === 'SEVERE' ? 'red' : 'orange'}>
                        {r.status === 'NORMAL' ? '正常' : r.status === 'SEVERE' ? '严重' : '异常'}
                      </Tag>
                      {r.point_no} · {r.equipment_name}
                      {r.defect_id && <Tag color="red">已建缺陷</Tag>}
                    </Space>}
                    description={<>{r.finding || '正常'} ｜ {dayjs(r.recorded_at).format('MM-DD HH:mm')} by {r.recorded_by}</>}
                  />
                </List.Item>
              )}
            />
          </>
        )}
      </Drawer>

      <Modal title={currentPoint ? `录入测点 ${currentPoint.equipment_name}` : '录入'}
        open={recordOpen} onOk={submitRecord} onCancel={() => setRecordOpen(false)}>
        <Form form={form} layout="vertical" initialValues={{ status: 'NORMAL' as PointStatus }}>
          <Form.Item name="status" label="检查结果" rules={[{ required: true }]}>
            <Radio.Group>
              <Radio.Button value="NORMAL">正常</Radio.Button>
              <Radio.Button value="ABNORMAL">异常</Radio.Button>
              <Radio.Button value="SEVERE">严重异常</Radio.Button>
            </Radio.Group>
          </Form.Item>
          <Form.Item name="finding" label="发现说明（异常必填）"><Input.TextArea rows={3} /></Form.Item>
          <Form.Item name="photo_url" label="现场照片">
            <Upload
              customRequest={uploadApi.customRequest}
              maxCount={1}
              accept=".jpg,.jpeg,.png,.webp,.gif"
              onChange={(info) => {
                if (info.file.status === 'done') {
                  const url = (info.file.response as any)?.data?.url
                  if (url) {
                    form.setFieldValue('photo_url', url)
                    message.success('照片已上传')
                  }
                } else if (info.file.status === 'error') {
                  message.error('上传失败')
                } else if (info.file.status === 'removed') {
                  form.setFieldValue('photo_url', undefined)
                }
              }}
            >
              <Button icon={<UploadOutlined />}>选择照片（≤5MB）</Button>
            </Upload>
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}
