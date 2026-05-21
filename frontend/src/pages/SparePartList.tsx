import { useEffect, useState } from 'react'
import {
  Card, Table, Tag, Button, Space, Input, Modal, Form, InputNumber, message, Typography,
  Drawer, Statistic, Row, Col, Select, Switch,
} from 'antd'
import { AppstoreOutlined, PlusOutlined, ReloadOutlined, SwapOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { sparePartApi, defectApi, workTicketApi } from '../api'
import { useAuthStore, canRepair, canWrite } from '../stores/auth'
import type { SparePart, StockMovement, StockMovementType, Defect, WorkTicket } from '../types'
import { MV_TYPE_LABEL } from '../types'

const { Text } = Typography

export default function SparePartList() {
  const role = useAuthStore((s) => s.role)
  const writable = canWrite(role)
  const repairer = canRepair(role)

  const [rows, setRows] = useState<SparePart[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [filters, setFilters] = useState<{ keyword?: string; category?: string; low_only?: boolean }>({})
  const [categories, setCategories] = useState<Array<{ category: string; count: number }>>([])
  const [overview, setOverview] = useState<{ total_items: number; low_stock_items: number; total_value: number } | null>(null)

  const [createOpen, setCreateOpen] = useState(false)
  const [createForm] = Form.useForm()

  const [mvOpen, setMvOpen] = useState(false)
  const [mvForm] = Form.useForm()
  const [current, setCurrent] = useState<SparePart | null>(null)
  const [openDefects, setOpenDefects] = useState<Defect[]>([])
  const [workTickets, setWorkTickets] = useState<WorkTicket[]>([])

  const [historyOpen, setHistoryOpen] = useState(false)
  const [history, setHistory] = useState<StockMovement[]>([])

  const load = () => {
    setLoading(true)
    sparePartApi.list({ page, page_size: 15, ...filters })
      .then((r) => { setRows(r.data.items); setTotal(r.data.total) })
      .finally(() => setLoading(false))
  }
  useEffect(load, [page, filters])

  useEffect(() => {
    sparePartApi.categories().then((r) => setCategories(r.data))
    sparePartApi.overview().then((r) => setOverview(r.data))
    defectApi.list({ page_size: 50 }).then((r) =>
      setOpenDefects(r.data.items.filter((d) => !['CLOSED', 'VERIFIED', 'CANCELLED'].includes(d.status))))
    workTicketApi.list({ page_size: 50 }).then((r) =>
      setWorkTickets(r.data.items.filter((w) => ['ISSUED', 'IN_WORK'].includes(w.status))))
  }, [])

  const onCreate = async () => {
    const v = await createForm.validateFields()
    try {
      await sparePartApi.create(v)
      message.success('物料已登记')
      setCreateOpen(false); createForm.resetFields()
      load()
      sparePartApi.overview().then((r) => setOverview(r.data))
    } catch (e: any) { message.error(e?.detail || '失败') }
  }

  const onMovement = async () => {
    const v = await mvForm.validateFields()
    try {
      const r = await sparePartApi.createMovement(current!.id, v)
      message.success(`已登记，当前库存：${r.data.stock_qty}` + (r.data.low_stock ? ' ⚠️低于安全库存' : ''))
      setMvOpen(false); mvForm.resetFields()
      load()
      sparePartApi.overview().then((r) => setOverview(r.data))
    } catch (e: any) { message.error(e?.detail || '失败') }
  }

  const openHistory = async (p: SparePart) => {
    setCurrent(p)
    const r = await sparePartApi.listMovements(p.id, { page_size: 50 })
    setHistory(r.data.items)
    setHistoryOpen(true)
  }

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      {overview && (
        <Card>
          <Row gutter={16}>
            <Col span={8}><Statistic title="物料总数" value={overview.total_items} /></Col>
            <Col span={8}><Statistic title="低库存物料" value={overview.low_stock_items} valueStyle={{ color: overview.low_stock_items > 0 ? '#ff4d4f' : undefined }} /></Col>
            <Col span={8}><Statistic title="库存总价值" value={overview.total_value} precision={2} prefix="¥" /></Col>
          </Row>
        </Card>
      )}

      <Card
        title={<Space><AppstoreOutlined />备品备件</Space>}
        extra={
          <Space>
            <Input.Search
              placeholder="名称/编号/规格" allowClear style={{ width: 200 }}
              onSearch={(v) => { setPage(1); setFilters({ ...filters, keyword: v || undefined }) }}
            />
            <Select
              placeholder="分类" allowClear style={{ width: 130 }} value={filters.category}
              onChange={(v) => { setPage(1); setFilters({ ...filters, category: v }) }}
              options={categories.map(c => ({ label: `${c.category} (${c.count})`, value: c.category === '未分类' ? null : c.category }))}
            />
            <Space size={4}>
              <Text type="secondary">仅低库存</Text>
              <Switch checked={!!filters.low_only} onChange={(v) => { setPage(1); setFilters({ ...filters, low_only: v }) }} />
            </Space>
            <Button icon={<ReloadOutlined />} onClick={load} />
            {writable && <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>登记物料</Button>}
          </Space>
        }
      >
        <Table
          rowKey="id"
          loading={loading}
          dataSource={rows}
          pagination={{ current: page, pageSize: 15, total, onChange: setPage }}
          columns={[
            { title: '编号', dataIndex: 'code', width: 110 },
            { title: '物料', render: (_: any, r: SparePart) => (
              <Space direction="vertical" size={0}>
                <Text strong>{r.name}</Text>
                {r.spec && <Text type="secondary" style={{ fontSize: 12 }}>{r.spec}</Text>}
              </Space>
            ) },
            { title: '分类', dataIndex: 'category', width: 100, render: (v) => v || '-' },
            { title: '单位', dataIndex: 'unit', width: 60 },
            { title: '当前库存', dataIndex: 'stock_qty', width: 110,
              render: (v: number, r: SparePart) => (
                <Text strong style={{ color: r.low_stock ? '#ff4d4f' : undefined }}>
                  {Number(v).toFixed(2)} {r.low_stock && <Tag color="red">不足</Tag>}
                </Text>
              ) },
            { title: '安全库存', dataIndex: 'min_qty', width: 100, render: (v) => Number(v).toFixed(2) },
            { title: '单价', dataIndex: 'unit_price', width: 90, render: (v) => `¥${Number(v).toFixed(2)}` },
            { title: '位置', dataIndex: 'location', width: 120, render: (v) => v || '-' },
            { title: '操作', width: 160, fixed: 'right' as const,
              render: (_: any, r: SparePart) => (
                <Space size="small">
                  {repairer && (
                    <Button size="small" icon={<SwapOutlined />} onClick={() => { setCurrent(r); setMvOpen(true) }}>出入库</Button>
                  )}
                  <Button size="small" type="link" onClick={() => openHistory(r)}>流水</Button>
                </Space>
              ) },
          ]}
          scroll={{ x: 1400 }}
        />
      </Card>

      <Modal title="登记物料" open={createOpen} onOk={onCreate} onCancel={() => setCreateOpen(false)} width={620}>
        <Form form={createForm} layout="vertical" initialValues={{ unit: '件', stock_qty: 0, min_qty: 0, unit_price: 0 }}>
          <Form.Item name="name" label="物料名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="spec" label="规格型号"><Input /></Form.Item>
          <Space>
            <Form.Item name="category" label="分类" style={{ width: 200 }}>
              <Select allowClear options={[
                '轴承', '密封件', '电子件', '油料', '工具', '管阀',
              ].map(v => ({ label: v, value: v }))} />
            </Form.Item>
            <Form.Item name="unit" label="单位" style={{ width: 100 }} rules={[{ required: true }]}>
              <Input />
            </Form.Item>
          </Space>
          <Space>
            <Form.Item name="stock_qty" label="初始库存"><InputNumber min={0} step={0.5} /></Form.Item>
            <Form.Item name="min_qty" label="安全库存"><InputNumber min={0} step={0.5} /></Form.Item>
            <Form.Item name="unit_price" label="单价 (¥)"><InputNumber min={0} step={0.01} /></Form.Item>
          </Space>
          <Space>
            <Form.Item name="location" label="存放位置" style={{ width: 220 }}><Input placeholder="如：备件库 A-12" /></Form.Item>
            <Form.Item name="supplier" label="供应商" style={{ width: 220 }}><Input /></Form.Item>
          </Space>
          <Form.Item name="notes" label="备注"><Input.TextArea rows={2} /></Form.Item>
        </Form>
      </Modal>

      <Modal title={current ? `出入库登记 · ${current.code} ${current.name}` : '出入库'}
        open={mvOpen} onOk={onMovement} onCancel={() => setMvOpen(false)} width={560}>
        <Form form={mvForm} layout="vertical" initialValues={{ movement_type: 'OUT', qty: 1 }}>
          <Form.Item name="movement_type" label="类型" rules={[{ required: true }]}>
            <Select options={Object.entries(MV_TYPE_LABEL).map(([k, v]) => ({ label: v, value: k }))} />
          </Form.Item>
          <Form.Item name="qty" label="数量" rules={[{ required: true }]}>
            <InputNumber min={0.01} step={0.5} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="defect_id" label="关联缺陷（领用场景）">
            <Select allowClear showSearch optionFilterProp="label"
              options={openDefects.map(d => ({ label: `${d.defect_no} · ${d.title}`, value: d.id }))} />
          </Form.Item>
          <Form.Item name="work_ticket_id" label="关联工作票">
            <Select allowClear showSearch optionFilterProp="label"
              options={workTickets.map(w => ({ label: `${w.ticket_no} · ${w.work_content?.slice(0, 24)}`, value: w.id }))} />
          </Form.Item>
          <Form.Item name="notes" label="备注"><Input.TextArea rows={2} /></Form.Item>
        </Form>
      </Modal>

      <Drawer title={current ? `${current.code} ${current.name} · 出入库流水` : '流水'}
        open={historyOpen} onClose={() => setHistoryOpen(false)} width={680}>
        <Table
          size="small"
          rowKey="id"
          dataSource={history}
          pagination={false}
          columns={[
            { title: '时间', dataIndex: 'created_at', render: (v) => dayjs(v).format('MM-DD HH:mm') },
            { title: '类型', dataIndex: 'movement_type', render: (v: StockMovementType) =>
              <Tag color={v === 'IN' ? 'green' : v === 'OUT' ? 'orange' : 'blue'}>{MV_TYPE_LABEL[v]}</Tag> },
            { title: '数量', dataIndex: 'qty', render: (v) => Number(v).toFixed(2) },
            { title: '关联', render: (_: any, r: StockMovement) => (
              <Space size={4}>
                {r.defect_id && <Tag color="red">缺陷#{r.defect_id}</Tag>}
                {r.work_ticket_id && <Tag color="blue">工作票#{r.work_ticket_id}</Tag>}
              </Space>
            ) },
            { title: '操作员', dataIndex: 'operator' },
            { title: '备注', dataIndex: 'notes', ellipsis: true },
          ]}
        />
      </Drawer>
    </Space>
  )
}
