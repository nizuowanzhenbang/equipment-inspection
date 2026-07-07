/**
 * 备件采购申请页（v3.0）
 *
 * 流程：DRAFT → SUBMITTED → APPROVED/REJECTED → SENT(fuel-procurement) → RECEIVED(入库回填)
 * - 自动生成：扫描低库存备件批量建草稿（手动按钮 + 调度器）
 * - 推送：APPROVED → POST 至 fuel-procurement 的 /api/integration/material-requests
 */
import { useEffect, useState } from 'react'
import {
  Card, Table, Tag, Button, Space, Select, Modal, Form, Input, InputNumber, message, Drawer, Descriptions,
} from 'antd'
import { ShoppingCartOutlined, PlusOutlined, ReloadOutlined, SendOutlined, ThunderboltOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { purchaseRequestApi, sparePartApi, PR_STATUS_LABEL } from '../api'
import type { PurchaseRequest, PRStatus } from '../api'
import type { SparePart } from '../types'
import { useAuthStore, canSupervise, canWrite } from '../stores/auth'

export default function PurchaseRequestList() {
  const role = useAuthStore((s) => s.role)
  const writable = canWrite(role)
  const supervisor = canSupervise(role)

  const [rows, setRows] = useState<PurchaseRequest[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [filters, setFilters] = useState<{ status?: PRStatus }>({})

  const [createOpen, setCreateOpen] = useState(false)
  const [form] = Form.useForm()
  const [spareParts, setSpareParts] = useState<SparePart[]>([])

  const [detail, setDetail] = useState<PurchaseRequest | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)
  const [rejectOpen, setRejectOpen] = useState(false)
  const [rejectForm] = Form.useForm()
  const [receiveOpen, setReceiveOpen] = useState(false)
  const [receiveForm] = Form.useForm()

  const load = () => {
    setLoading(true)
    purchaseRequestApi.list({ page, page_size: 15, ...filters })
      .then((r) => { setRows(r.data.items); setTotal(r.data.total) })
      .finally(() => setLoading(false))
  }
  useEffect(load, [page, filters])

  useEffect(() => {
    sparePartApi.list({ page_size: 100 }).then((r) => setSpareParts(r.data.items))
  }, [])

  const reloadDetail = async (id: number) => {
    const r = await purchaseRequestApi.get(id)
    setDetail(r.data)
  }

  const openDetail = async (id: number) => {
    await reloadDetail(id)
    setDetailOpen(true)
  }

  const onCreate = async () => {
    const v = await form.validateFields()
    try {
      await purchaseRequestApi.create({
        spare_part_id: v.spare_part_id,
        qty: v.qty,
        urgency: v.urgency,
        reason: v.reason,
      })
      message.success('已创建采购申请')
      setCreateOpen(false); form.resetFields(); load()
    } catch (e: any) { message.error(e?.detail || '失败') }
  }

  const autoGenerate = async () => {
    try {
      const r = await purchaseRequestApi.autoGenerate()
      message.success(`已为低库存备件生成 ${r.data.created.length} 张采购申请`)
      load()
    } catch (e: any) { message.error(e?.detail || '失败') }
  }

  const transition = async (action: () => Promise<any>, okMsg: string) => {
    try {
      await action()
      message.success(okMsg)
      if (detail) reloadDetail(detail.id)
      load()
    } catch (e: any) { message.error(e?.detail || '失败') }
  }

  const onReject = async () => {
    const v = await rejectForm.validateFields()
    await transition(() => purchaseRequestApi.reject(detail!.id, v.reason), '已驳回')
    setRejectOpen(false); rejectForm.resetFields()
  }

  const onReceive = async () => {
    const v = await receiveForm.validateFields()
    await transition(() => purchaseRequestApi.receive(detail!.id, v.received_qty), '入库已登记')
    setReceiveOpen(false); receiveForm.resetFields()
  }

  const statusTag = (s: PRStatus) => {
    const c =
      s === 'RECEIVED' ? 'green' :
      s === 'SENT' ? 'blue' :
      s === 'APPROVED' ? 'cyan' :
      s === 'SUBMITTED' ? 'orange' :
      s === 'REJECTED' ? 'red' :
      s === 'CANCELLED' ? 'default' : 'gold'
    return <Tag color={c}>{PR_STATUS_LABEL[s]}</Tag>
  }

  return (
    <Card title={<Space><ShoppingCartOutlined />备件采购申请</Space>}
      extra={
        <Space>
          <Select<PRStatus | undefined>
            placeholder="状态" allowClear style={{ width: 130 }} value={filters.status}
            onChange={(v) => { setPage(1); setFilters({ ...filters, status: v }) }}
            options={Object.entries(PR_STATUS_LABEL).map(([k, v]) => ({ label: v, value: k }))}
          />
          <Button icon={<ReloadOutlined />} onClick={load} />
          {writable && <Button icon={<ThunderboltOutlined />} onClick={autoGenerate}>低库存自动生成</Button>}
          {writable && <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>新建</Button>}
        </Space>
      }
    >
      <Table
        rowKey="id"
        loading={loading}
        dataSource={rows}
        pagination={{ current: page, pageSize: 15, total, onChange: setPage }}
        columns={[
          { title: '申请单号', dataIndex: 'pr_no', width: 170 },
          { title: '备件', render: (_: any, r: PurchaseRequest) => `${r.spare_part_code} · ${r.spare_part_name}` },
          { title: '数量', dataIndex: 'qty', width: 80 },
          { title: '预估金额', dataIndex: 'estimated_amount', width: 110,
            render: (v) => v ? `¥ ${Number(v).toFixed(2)}` : '-' },
          { title: '紧急度', dataIndex: 'urgency', width: 100,
            render: (v) => <Tag color={v === 'URGENT' ? 'red' : 'blue'}>{v}</Tag> },
          { title: '来源', dataIndex: 'source', width: 110,
            render: (v) => <Tag color={v === 'AUTO_LOW_STOCK' ? 'purple' : 'default'}>{v}</Tag> },
          { title: '状态', dataIndex: 'status', width: 110, render: (v) => statusTag(v) },
          { title: '申请人', dataIndex: 'applicant', width: 100 },
          { title: '外部订单', dataIndex: 'external_order_no', width: 150,
            render: (v) => v ? <Tag color="blue">{v}</Tag> : '-' },
          { title: '操作', width: 90, fixed: 'right' as const,
            render: (_: any, r: PurchaseRequest) => <Button size="small" onClick={() => openDetail(r.id)}>详情</Button> },
        ]}
        scroll={{ x: 1500 }}
      />

      <Modal title="新建采购申请" open={createOpen} onOk={onCreate} onCancel={() => setCreateOpen(false)} width={560}>
        <Form form={form} layout="vertical" initialValues={{ urgency: 'NORMAL' }}>
          <Form.Item name="spare_part_id" label="备件" rules={[{ required: true }]}>
            <Select
              showSearch optionFilterProp="label"
              options={spareParts.map(s => ({
                label: `${s.code} · ${s.name}（库存 ${s.stock_qty}/${s.min_qty}）`,
                value: s.id,
              }))}
            />
          </Form.Item>
          <Form.Item name="qty" label="数量" rules={[{ required: true, type: 'number', min: 0.01 }]}>
            <InputNumber style={{ width: '100%' }} min={0.01} step={1} />
          </Form.Item>
          <Form.Item name="urgency" label="紧急度">
            <Select options={[{ label: '普通', value: 'NORMAL' }, { label: '紧急', value: 'URGENT' }]} />
          </Form.Item>
          <Form.Item name="reason" label="申请理由">
            <Input.TextArea rows={3} placeholder="例如：1#引风机轴承备件不足，下次大修需备货 2 套" />
          </Form.Item>
        </Form>
      </Modal>

      <Drawer
        title={detail ? `${detail.pr_no} · ${detail.spare_part_code}` : '采购申请'}
        open={detailOpen} onClose={() => setDetailOpen(false)} width={680}
      >
        {detail && (
          <>
            <Space style={{ marginBottom: 12 }}>
              {statusTag(detail.status)}
              <Tag color={detail.urgency === 'URGENT' ? 'red' : 'blue'}>{detail.urgency}</Tag>
              <Tag color={detail.source === 'AUTO_LOW_STOCK' ? 'purple' : 'default'}>{detail.source}</Tag>
            </Space>
            <Descriptions column={2} size="small" bordered>
              <Descriptions.Item label="备件" span={2}>{detail.spare_part_code} · {detail.spare_part_name}</Descriptions.Item>
              <Descriptions.Item label="数量">{detail.qty}</Descriptions.Item>
              <Descriptions.Item label="预估金额">¥ {Number(detail.estimated_amount).toFixed(2)}</Descriptions.Item>
              <Descriptions.Item label="申请人">{detail.applicant}</Descriptions.Item>
              <Descriptions.Item label="审批人">{detail.approver || '-'}</Descriptions.Item>
              <Descriptions.Item label="提交时间">{detail.submitted_at ? dayjs(detail.submitted_at).format('YYYY-MM-DD HH:mm') : '-'}</Descriptions.Item>
              <Descriptions.Item label="批准时间">{detail.approved_at ? dayjs(detail.approved_at).format('YYYY-MM-DD HH:mm') : '-'}</Descriptions.Item>
              <Descriptions.Item label="推送时间">{detail.sent_at ? dayjs(detail.sent_at).format('YYYY-MM-DD HH:mm') : '-'}</Descriptions.Item>
              <Descriptions.Item label="外部订单号">{detail.external_order_no || '-'}</Descriptions.Item>
              <Descriptions.Item label="已到货">{detail.received_qty || 0} / {detail.qty}</Descriptions.Item>
              <Descriptions.Item label="申请理由" span={2}>{detail.reason || '-'}</Descriptions.Item>
              {detail.rejected_reason && (
                <Descriptions.Item label="驳回原因" span={2}>{detail.rejected_reason}</Descriptions.Item>
              )}
            </Descriptions>

            <div style={{ marginTop: 16 }}>
              <Space wrap>
                {writable && detail.status === 'DRAFT' && (
                  <Button onClick={() => transition(() => purchaseRequestApi.submit(detail.id), '已提交')}>提交</Button>
                )}
                {supervisor && detail.status === 'SUBMITTED' && (
                  <>
                    <Button type="primary" onClick={() => transition(() => purchaseRequestApi.approve(detail.id), '已批准')}>批准</Button>
                    <Button danger onClick={() => setRejectOpen(true)}>驳回</Button>
                  </>
                )}
                {supervisor && detail.status === 'APPROVED' && (
                  <Button type="primary" icon={<SendOutlined />}
                    onClick={() => transition(() => purchaseRequestApi.send(detail.id), '已推送采购系统')}>
                    推送 fuel-procurement
                  </Button>
                )}
                {writable && (detail.status === 'SENT' || detail.status === 'APPROVED') && (
                  <Button onClick={() => setReceiveOpen(true)}>到货入库</Button>
                )}
                {supervisor && !['RECEIVED', 'CANCELLED'].includes(detail.status) && (
                  <Button onClick={() => transition(() => purchaseRequestApi.cancel(detail.id), '已取消')}>取消</Button>
                )}
              </Space>
            </div>
          </>
        )}
      </Drawer>

      <Modal title="驳回采购申请" open={rejectOpen} onOk={onReject} onCancel={() => setRejectOpen(false)}>
        <Form form={rejectForm} layout="vertical">
          <Form.Item name="reason" label="驳回原因" rules={[{ required: true }]}>
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal title="到货入库" open={receiveOpen} onOk={onReceive} onCancel={() => setReceiveOpen(false)}>
        <Form form={receiveForm} layout="vertical">
          <Form.Item name="received_qty" label="本次入库数量" rules={[{ required: true, type: 'number', min: 0.01 }]}>
            <InputNumber style={{ width: '100%' }} min={0.01} />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}
