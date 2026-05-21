import { useEffect, useState } from 'react'
import {
  Card, Table, Tag, Button, Space, Select, Modal, Form, Input, InputNumber, message, Typography, Upload,
} from 'antd'
import { BugOutlined, PlusOutlined, ReloadOutlined, UploadOutlined, FileTextOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { useNavigate } from 'react-router-dom'
import { defectApi, equipmentApi, uploadApi } from '../api'
import { useAuthStore, canRepair, canSupervise, canWrite } from '../stores/auth'
import {
  Defect, DefectStatus, DefectSeverity, DefectSource, Equipment,
  DEFECT_STATUS_LABEL, SEVERITY_LABEL,
} from '../types'

const { Text } = Typography

const SOURCE_LABEL: Record<DefectSource, string> = {
  INSPECTION: '点检发现', MANUAL: '手动上报', ALARM: '报警转入',
}

export default function DefectList() {
  const role = useAuthStore((s) => s.role)
  const writable = canWrite(role)
  const repairer = canRepair(role)
  const supervisor = canSupervise(role)
  const navigate = useNavigate()

  const [rows, setRows] = useState<Defect[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [filters, setFilters] = useState<{ status?: DefectStatus; severity?: DefectSeverity }>({})

  const [createOpen, setCreateOpen] = useState(false)
  const [equipments, setEquipments] = useState<Equipment[]>([])
  const [createForm] = Form.useForm()

  const [assignOpen, setAssignOpen] = useState(false)
  const [assignForm] = Form.useForm()
  const [repairOpen, setRepairOpen] = useState(false)
  const [repairForm] = Form.useForm()
  const [verifyOpen, setVerifyOpen] = useState(false)
  const [verifyForm] = Form.useForm()
  const [current, setCurrent] = useState<Defect | null>(null)

  const load = () => {
    setLoading(true)
    defectApi.list({ page, page_size: 15, ...filters })
      .then((r) => { setRows(r.data.items); setTotal(r.data.total) })
      .finally(() => setLoading(false))
  }
  useEffect(load, [page, filters])

  useEffect(() => {
    equipmentApi.list({ page_size: 100 }).then((r) => setEquipments(r.data.items))
  }, [])

  const onCreate = async () => {
    const v = await createForm.validateFields()
    try {
      await defectApi.create(v)
      message.success('已上报')
      setCreateOpen(false)
      createForm.resetFields()
      load()
    } catch (e: any) { message.error(e?.detail || '失败') }
  }

  const onAssign = async () => {
    const v = await assignForm.validateFields()
    await defectApi.assign(current!.id, v.assigned_to, v.notes)
    message.success('已派工')
    setAssignOpen(false); assignForm.resetFields(); load()
  }

  const onRepair = async () => {
    const v = await repairForm.validateFields()
    await defectApi.repair(current!.id, v.repair_notes, v.repair_cost || 0)
    message.success('修复已提交')
    setRepairOpen(false); repairForm.resetFields(); load()
  }

  const onVerify = async () => {
    const v = await verifyForm.validateFields()
    await defectApi.verify(current!.id, v.pass_ === 'PASS', v.verify_notes)
    message.success(v.pass_ === 'PASS' ? '已验收' : '已驳回')
    setVerifyOpen(false); verifyForm.resetFields(); load()
  }

  const statusTag = (s: DefectStatus) => {
    const c = s === 'CLOSED' || s === 'VERIFIED' ? 'green' :
      s === 'IN_REPAIR' || s === 'ASSIGNED' ? 'blue' :
        s === 'REPAIRED' ? 'cyan' :
          s === 'OVERDUE' || s === 'NEW' ? 'red' : 'default'
    return <Tag color={c}>{DEFECT_STATUS_LABEL[s]}</Tag>
  }

  const sevTag = (s: DefectSeverity) =>
    <Tag color={s === 'CRITICAL' ? 'red' : s === 'MAJOR' ? 'orange' : 'default'}>{SEVERITY_LABEL[s]}</Tag>

  const syncTag = (r: Defect) => {
    if (r.severity !== 'CRITICAL') return <Tag>不适用</Tag>
    const s = r.safety_sync_status
    if (s === 'SYNCED') return <Tag color="green" title={r.safety_hazard_no || ''}>已联动 {r.safety_hazard_no || ''}</Tag>
    if (s === 'FAILED') return <Tag color="red">联动失败({r.safety_sync_attempts || 0})</Tag>
    if (s === 'PENDING') return <Tag color="orange">联动中</Tag>
    if (s === 'SKIPPED') return <Tag>跳过</Tag>
    return <Tag>-</Tag>
  }

  return (
    <Card title={<Space><BugOutlined />缺陷工单</Space>}
      extra={
        <Space>
          <Select<DefectStatus | undefined>
            placeholder="状态" allowClear style={{ width: 130 }} value={filters.status}
            onChange={(v) => { setPage(1); setFilters({ ...filters, status: v }) }}
            options={Object.entries(DEFECT_STATUS_LABEL).map(([k, v]) => ({ label: v, value: k }))}
          />
          <Select<DefectSeverity | undefined>
            placeholder="级别" allowClear style={{ width: 110 }} value={filters.severity}
            onChange={(v) => { setPage(1); setFilters({ ...filters, severity: v }) }}
            options={Object.entries(SEVERITY_LABEL).map(([k, v]) => ({ label: v, value: k }))}
          />
          <Button icon={<ReloadOutlined />} onClick={load} />
          <Button onClick={async () => { const r = await defectApi.sweepOverdue(); message.success(`标记 ${r.data.overdue} 个超期`); load() }}>扫描超期</Button>
          {writable && <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>上报缺陷</Button>}
        </Space>
      }
    >
      <Table
        rowKey="id"
        loading={loading}
        dataSource={rows}
        pagination={{ current: page, pageSize: 15, total, onChange: setPage }}
        columns={[
          { title: '缺陷单号', dataIndex: 'defect_no', width: 170 },
          { title: '设备', render: (_: any, r: Defect) => (<><Text>{r.equipment_name}</Text> <Text type="secondary">{r.equipment_code}</Text></>) },
          { title: '标题', dataIndex: 'title', ellipsis: true },
          { title: '来源', dataIndex: 'source', width: 90, render: (v) => SOURCE_LABEL[v as DefectSource] },
          { title: '级别', dataIndex: 'severity', width: 80, render: (v) => sevTag(v) },
          { title: '状态', dataIndex: 'status', width: 100, render: (v) => statusTag(v) },
          { title: '指派', dataIndex: 'assigned_to', width: 100 },
          { title: 'SLA 截止', dataIndex: 'sla_deadline', width: 140,
            render: (v) => v ? dayjs(v).format('MM-DD HH:mm') : '-' },
          { title: '上报时间', dataIndex: 'reported_at', width: 140, render: (v) => dayjs(v).format('MM-DD HH:mm') },
          { title: '隐患联动', width: 160, render: (_: any, r: Defect) => syncTag(r) },
          {
            title: '操作', width: 260, fixed: 'right' as const,
            render: (_: any, r: Defect) => (
              <Space size="small" wrap>
                {supervisor && (r.status === 'NEW' || r.status === 'OVERDUE') && (
                  <Button size="small" onClick={() => { setCurrent(r); setAssignOpen(true) }}>派工</Button>
                )}
                {repairer && r.status === 'ASSIGNED' && (
                  <Button size="small" onClick={async () => { await defectApi.startRepair(r.id); message.success('已开始检修'); load() }}>开始检修</Button>
                )}
                {repairer && (r.status === 'ASSIGNED' || r.status === 'IN_REPAIR') && (
                  <Button size="small" type="primary" onClick={() => { setCurrent(r); setRepairOpen(true) }}>提交修复</Button>
                )}
                {supervisor && r.status === 'REPAIRED' && (
                  <Button size="small" type="primary" onClick={() => { setCurrent(r); setVerifyOpen(true) }}>验收</Button>
                )}
                {supervisor && r.severity === 'CRITICAL' && r.safety_sync_status !== 'SYNCED' && (
                  <Button size="small" onClick={async () => {
                    const resp = await defectApi.safetySync(r.id)
                    message.info(resp.message || '已触发')
                    load()
                  }}>重推隐患</Button>
                )}
                {writable && ['ASSIGNED', 'IN_REPAIR', 'REPAIRED'].includes(r.status) && (
                  <Button size="small" icon={<FileTextOutlined />}
                    onClick={() => navigate(`/work-tickets?defect_id=${r.id}`)}>
                    工作票
                  </Button>
                )}
              </Space>
            ),
          },
        ]}
        scroll={{ x: 1560 }}
      />

      {/* 上报 */}
      <Modal title="上报缺陷" open={createOpen} onOk={onCreate} onCancel={() => setCreateOpen(false)}>
        <Form form={createForm} layout="vertical">
          <Form.Item name="equipment_id" label="设备" rules={[{ required: true }]}>
            <Select
              showSearch optionFilterProp="label"
              options={equipments.map(e => ({ label: `${e.code} · ${e.name}`, value: e.id }))}
            />
          </Form.Item>
          <Form.Item name="title" label="标题" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="description" label="详细描述"><Input.TextArea rows={3} /></Form.Item>
          <Form.Item name="severity" label="级别" initialValue="MINOR">
            <Select options={Object.entries(SEVERITY_LABEL).map(([k, v]) => ({ label: v, value: k }))} />
          </Form.Item>
          <Form.Item name="photo_url" label="现场照片">
            <Upload
              customRequest={uploadApi.customRequest}
              maxCount={1}
              accept=".jpg,.jpeg,.png,.webp,.gif"
              onChange={(info) => {
                if (info.file.status === 'done') {
                  const url = (info.file.response as any)?.data?.url
                  if (url) {
                    createForm.setFieldValue('photo_url', url)
                    message.success('照片已上传')
                  }
                } else if (info.file.status === 'error') {
                  message.error('上传失败')
                } else if (info.file.status === 'removed') {
                  createForm.setFieldValue('photo_url', undefined)
                }
              }}
            >
              <Button icon={<UploadOutlined />}>选择照片（≤5MB）</Button>
            </Upload>
          </Form.Item>
        </Form>
      </Modal>

      <Modal title="派工" open={assignOpen} onOk={onAssign} onCancel={() => setAssignOpen(false)}>
        <Form form={assignForm} layout="vertical">
          <Form.Item name="assigned_to" label="指派给（用户名）" rules={[{ required: true }]} initialValue="repairman">
            <Input />
          </Form.Item>
          <Form.Item name="notes" label="派工备注"><Input.TextArea rows={2} /></Form.Item>
        </Form>
      </Modal>

      <Modal title="提交修复" open={repairOpen} onOk={onRepair} onCancel={() => setRepairOpen(false)}>
        <Form form={repairForm} layout="vertical">
          <Form.Item name="repair_notes" label="检修记录" rules={[{ required: true }]}>
            <Input.TextArea rows={4} />
          </Form.Item>
          <Form.Item name="repair_cost" label="检修费用（元）" initialValue={0}>
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal title="验收" open={verifyOpen} onOk={onVerify} onCancel={() => setVerifyOpen(false)}>
        <Form form={verifyForm} layout="vertical" initialValues={{ pass_: 'PASS' }}>
          <Form.Item name="pass_" label="验收结果" rules={[{ required: true }]}>
            <Select options={[{ label: '通过（关闭工单）', value: 'PASS' }, { label: '驳回（回到检修中）', value: 'FAIL' }]} />
          </Form.Item>
          <Form.Item name="verify_notes" label="验收意见"><Input.TextArea rows={3} /></Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}
