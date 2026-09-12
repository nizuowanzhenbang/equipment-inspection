import { useEffect, useState } from 'react'
import {
  Card, Table, Tag, Button, Space, Select, Modal, Form, Input, message,
  Drawer, Descriptions, List, Divider, Typography, Steps,
} from 'antd'
import { OrderedListOutlined, PlusOutlined, ReloadOutlined, SaveOutlined, SafetyCertificateOutlined, AuditOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { opTicketApi, workTicketApi, equipmentApi } from '../api'
import type { OperationTemplate, SignatureEntry, SignatureVerifyResult } from '../api'
import SignatureModal from '../components/SignatureModal'
import { useAuthStore, canInspect, canSupervise, canWrite } from '../stores/auth'
import type {
  OperationTicket, OperationTicketStatus, OperationTicketType, OperationStep,
  Equipment, WorkTicket,
} from '../types'
import { OT_STATUS_LABEL, OT_TYPE_LABEL } from '../types'

const { Text } = Typography

export default function OperationTicketList() {
  const role = useAuthStore((s) => s.role)
  const writable = canWrite(role)
  const inspector = canInspect(role)
  const supervisor = canSupervise(role)

  const [rows, setRows] = useState<OperationTicket[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [filters, setFilters] = useState<{ status?: OperationTicketStatus; operation_type?: OperationTicketType }>({})

  const [createOpen, setCreateOpen] = useState(false)
  const [createForm] = Form.useForm()
  const [equipments, setEquipments] = useState<Equipment[]>([])
  const [workTickets, setWorkTickets] = useState<WorkTicket[]>([])

  const [detailOpen, setDetailOpen] = useState(false)
  const [detail, setDetail] = useState<OperationTicket | null>(null)

  const [stepOpen, setStepOpen] = useState(false)
  const [stepForm] = Form.useForm()
  const [currentStep, setCurrentStep] = useState<OperationStep | null>(null)

  const [templates, setTemplates] = useState<OperationTemplate[]>([])
  const [saveTplOpen, setSaveTplOpen] = useState(false)
  const [saveTplForm] = Form.useForm()
  const [sigStage, setSigStage] = useState<'review' | 'approve' | 'step' | null>(null)
  const [verifyResult, setVerifyResult] = useState<SignatureVerifyResult | null>(null)
  const [verifyOpen, setVerifyOpen] = useState(false)

  const reloadTemplates = () => opTicketApi.listTemplates().then((r) => setTemplates(r.data))

  const load = () => {
    setLoading(true)
    opTicketApi.list({ page, page_size: 15, ...filters })
      .then((r) => { setRows(r.data.items); setTotal(r.data.total) })
      .finally(() => setLoading(false))
  }
  useEffect(load, [page, filters])

  useEffect(() => {
    equipmentApi.list({ page_size: 100 }).then((r) => setEquipments(r.data.items))
    workTicketApi.list({ page_size: 50 }).then((r) => setWorkTickets(r.data.items))
    reloadTemplates()
  }, [])

  const useTemplate = (tpl: OperationTemplate) => {
    const text = tpl.steps.map((s) => s.expected ? `${s.action} | ${s.expected}` : s.action).join('\n')
    createForm.setFieldsValue({
      title: tpl.name,
      operation_type: tpl.operation_type,
      steps_text: text,
    })
    if (!createOpen) setCreateOpen(true)
    message.success(`已复用模板 ${tpl.name}（被引用 ${tpl.use_count} 次）`)
  }

  const onSaveAsTemplate = async () => {
    const v = await saveTplForm.validateFields()
    try {
      await opTicketApi.saveAsTemplate(detail!.id, v.name, v.description)
      message.success('已另存为模板')
      setSaveTplOpen(false); saveTplForm.resetFields()
      reloadTemplates()
    } catch (e: any) { message.error(e?.detail || '失败') }
  }

  const reloadDetail = async (id: number) => {
    const res = await opTicketApi.get(id)
    setDetail(res.data)
  }

  const openDetail = async (id: number) => {
    await reloadDetail(id)
    setDetailOpen(true)
  }

  const onCreate = async () => {
    const v = await createForm.validateFields()
    try {
      const stepLines = (v.steps_text || '').split('\n').map((l: string) => l.trim()).filter(Boolean)
      if (stepLines.length === 0) {
        message.error('至少要填一条操作步骤')
        return
      }
      const steps = stepLines.map((line: string, i: number) => {
        const [action, expected] = line.split(/[|｜]/).map((s) => s.trim())
        return { seq: i + 1, action: action || line, expected: expected || null }
      })
      await opTicketApi.create({
        title: v.title,
        operation_type: v.operation_type,
        work_ticket_id: v.work_ticket_id || null,
        equipment_id: v.equipment_id || null,
        operator: v.operator,
        supervisor: v.supervisor,
        steps,
        notes: v.notes,
      })
      message.success('操作票已起草')
      setCreateOpen(false); createForm.resetFields(); load()
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

  const submitStep = async () => {
    const v = await stepForm.validateFields()
    if (!v.signature_password) { message.error('请输入签名密码'); return }
    try {
      await opTicketApi.executeStep(detail!.id, currentStep!.seq, v.result, v.notes, v.signature_password)
      message.success('步骤已记录（已签名）')
      setStepOpen(false); stepForm.resetFields()
      reloadDetail(detail!.id)
      load()
    } catch (e: any) { message.error(e?.detail || '失败') }
  }

  const handleSignedAction = async (password: string, _extra: Record<string, any>) => {
    if (!detail || !sigStage) return
    try {
      if (sigStage === 'review') {
        await opTicketApi.review(detail.id, password)
        message.success('已审核')
      } else if (sigStage === 'approve') {
        await opTicketApi.approve(detail.id, password)
        message.success('已批准')
      }
      setSigStage(null)
      reloadDetail(detail.id)
      load()
    } catch (e: any) {
      message.error(e?.detail || '签名失败')
      throw e
    }
  }

  const verifyChain = async () => {
    if (!detail) return
    try {
      const res = await opTicketApi.verifySignatures(detail.id)
      setVerifyResult(res.data)
      setVerifyOpen(true)
    } catch (e: any) { message.error(e?.detail || '校验失败') }
  }

  const statusTag = (s: OperationTicketStatus) => {
    const c = s === 'COMPLETED' ? 'green' : s === 'EXECUTING' ? 'blue' :
      s === 'APPROVED' ? 'cyan' : s === 'REVIEWED' ? 'gold' :
      s === 'CANCELLED' ? 'default' : 'orange'
    return <Tag color={c}>{OT_STATUS_LABEL[s]}</Tag>
  }

  const stepProgress = (steps: OperationStep[]) => {
    const done = steps.filter(s => s.result === 'PASS').length
    return `${done}/${steps.length}`
  }

  return (
    <Card title={<Space><OrderedListOutlined />操作票</Space>}
      extra={
        <Space>
          <Select<OperationTicketStatus | undefined>
            placeholder="状态" allowClear style={{ width: 120 }} value={filters.status}
            onChange={(v) => { setPage(1); setFilters({ ...filters, status: v }) }}
            options={Object.entries(OT_STATUS_LABEL).map(([k, v]) => ({ label: v, value: k }))}
          />
          <Select<OperationTicketType | undefined>
            placeholder="类型" allowClear style={{ width: 120 }} value={filters.operation_type}
            onChange={(v) => { setPage(1); setFilters({ ...filters, operation_type: v }) }}
            options={Object.entries(OT_TYPE_LABEL).map(([k, v]) => ({ label: v, value: k }))}
          />
          <Select<number | undefined>
            placeholder={`模板 (${templates.length})`} allowClear style={{ width: 200 }}
            onChange={(id) => { const tpl = templates.find(t => t.id === id); if (tpl) useTemplate(tpl) }}
            value={undefined}
            options={templates.map((t) => ({ label: `${t.name} · 用${t.use_count}次`, value: t.id }))}
          />
          <Button icon={<ReloadOutlined />} onClick={() => { load(); reloadTemplates() }} />
          {writable && <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>开操作票</Button>}
        </Space>
      }
    >
      <Table
        rowKey="id"
        loading={loading}
        dataSource={rows}
        pagination={{ current: page, pageSize: 15, total, onChange: setPage }}
        columns={[
          { title: '票号', dataIndex: 'ticket_no', width: 170 },
          { title: '标题', dataIndex: 'title', ellipsis: true },
          { title: '类型', dataIndex: 'operation_type', width: 110,
            render: (v: OperationTicketType) => <Tag>{OT_TYPE_LABEL[v]}</Tag> },
          { title: '状态', dataIndex: 'status', width: 110, render: (v) => statusTag(v) },
          { title: '操作员', dataIndex: 'operator', width: 100 },
          { title: '监护人', dataIndex: 'supervisor', width: 100 },
          { title: '进度', width: 80, render: (_: any, r: OperationTicket) => stepProgress(r.steps || []) },
          { title: '关联工作票', dataIndex: 'work_ticket_id', width: 110,
            render: (v) => v ? <Tag color="blue">#{v}</Tag> : '-' },
          { title: '操作', width: 90, fixed: 'right' as const,
            render: (_: any, r: OperationTicket) => <Button size="small" onClick={() => openDetail(r.id)}>详情</Button> },
        ]}
        scroll={{ x: 1300 }}
      />

      <Modal title="新开操作票" open={createOpen} onOk={onCreate} onCancel={() => setCreateOpen(false)} width={680}>
        <Form form={createForm} layout="vertical" initialValues={{ operation_type: 'SWITCHING' }}>
          <Form.Item name="title" label="标题" rules={[{ required: true }]}>
            <Input placeholder="如：1#引风机检修停电操作" />
          </Form.Item>
          <Form.Item name="operation_type" label="操作类型">
            <Select options={Object.entries(OT_TYPE_LABEL).map(([k, v]) => ({ label: v, value: k }))} />
          </Form.Item>
          <Space>
            <Form.Item name="equipment_id" label="设备">
              <Select allowClear showSearch optionFilterProp="label" style={{ width: 260 }}
                options={equipments.map(e => ({ label: `${e.code} · ${e.name}`, value: e.id }))} />
            </Form.Item>
            <Form.Item name="work_ticket_id" label="关联工作票">
              <Select allowClear showSearch optionFilterProp="label" style={{ width: 260 }}
                options={workTickets.map(w => ({ label: `${w.ticket_no} · ${w.work_content?.slice(0, 18)}`, value: w.id }))} />
            </Form.Item>
          </Space>
          <Space>
            <Form.Item name="operator" label="操作员" initialValue="inspector" rules={[{ required: true }]}>
              <Input style={{ width: 180 }} />
            </Form.Item>
            <Form.Item name="supervisor" label="监护人" initialValue="supervisor">
              <Input style={{ width: 180 }} />
            </Form.Item>
          </Space>
          <Form.Item name="steps_text" label="操作步骤（每行一条，可用 | 分隔预期结果）" rules={[{ required: true }]}>
            <Input.TextArea rows={6} placeholder={'断开 1#引风机电源开关 | 红灯灭、绿灯亮\n验电、装设接地线 | 接地良好\n挂"禁止合闸"标识牌'} />
          </Form.Item>
          <Form.Item name="notes" label="备注"><Input.TextArea rows={2} /></Form.Item>
        </Form>
      </Modal>

      <Drawer
        title={detail ? `${detail.ticket_no} · ${detail.title}` : '操作票详情'}
        open={detailOpen} onClose={() => setDetailOpen(false)} width={720}
        extra={detail && writable && (
          <Button icon={<SaveOutlined />} onClick={() => {
            saveTplForm.setFieldsValue({ name: detail.title, description: '' })
            setSaveTplOpen(true)
          }}>另存为模板</Button>
        )}
      >
        {detail && (
          <>
            <Space style={{ marginBottom: 12 }}>
              {statusTag(detail.status)}
              <Tag>{OT_TYPE_LABEL[detail.operation_type]}</Tag>
              {detail.work_ticket_id && <Tag color="blue">关联工作票 #{detail.work_ticket_id}</Tag>}
            </Space>
            <Descriptions column={2} size="small" bordered>
              <Descriptions.Item label="操作员">{detail.operator}</Descriptions.Item>
              <Descriptions.Item label="监护人">{detail.supervisor || '-'}</Descriptions.Item>
              <Descriptions.Item label="批准人">{detail.approver || '-'}</Descriptions.Item>
              <Descriptions.Item label="开始/完成">
                {detail.started_at ? dayjs(detail.started_at).format('MM-DD HH:mm') : '-'} ~ {detail.completed_at ? dayjs(detail.completed_at).format('MM-DD HH:mm') : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="备注" span={2}>{detail.notes || '-'}</Descriptions.Item>
            </Descriptions>

            {detail.steps.some(s => s.result === 'FAIL') && <Text type="danger">步骤未通过，已停止后续执行。请主管核实并作废后重新开票。</Text>}
            <Divider orientation="left">步骤（{stepProgress(detail.steps || [])}）</Divider>
            <Steps
              direction="vertical"
              size="small"
              current={(detail.steps || []).findIndex((s) => s.result !== 'PASS')}
              items={(detail.steps || []).map((s) => ({
                title: `${s.seq}. ${s.action}`,
                description: (
                  <Space direction="vertical" size={2}>
                    {s.expected && <Text type="secondary">预期：{s.expected}</Text>}
                    {s.result && (
                      <Space>
                        <Tag color={s.result === 'PASS' ? 'green' : 'red'}>{s.result === 'PASS' ? '通过' : '不通过'}</Tag>
                        <Text type="secondary">{s.executed_by} · {s.executed_at ? dayjs(s.executed_at).format('MM-DD HH:mm') : ''}</Text>
                        {s.notes && <Text type="secondary">{s.notes}</Text>}
                      </Space>
                    )}
                    {inspector && detail.status === 'EXECUTING' && !s.result &&
                      !detail.steps.some(step => step.result === 'FAIL') &&
                      detail.steps.find(step => !step.result)?.seq === s.seq && (
                      <Button size="small" type="primary" onClick={() => { setCurrentStep(s); setStepOpen(true) }}>执行</Button>
                    )}
                  </Space>
                ),
                status: s.result ? (s.result === 'PASS' ? 'finish' : 'error') : undefined,
              }))}
            />

            <Divider orientation="left">流转</Divider>
            <Space wrap>
              {supervisor && detail.status === 'DRAFT' && (
                <Button icon={<SafetyCertificateOutlined />} onClick={() => setSigStage('review')}>审核（签名）</Button>
              )}
              {supervisor && detail.status === 'REVIEWED' && (
                <Button type="primary" icon={<SafetyCertificateOutlined />} onClick={() => setSigStage('approve')}>批准（签名）</Button>
              )}
              {inspector && detail.status === 'APPROVED' && (
                <Button type="primary" onClick={() => transition(() => opTicketApi.start(detail.id), '开始执行')}>开始执行</Button>
              )}
              {supervisor && !['COMPLETED', 'CANCELLED'].includes(detail.status) && (
                <Button danger onClick={() => transition(() => opTicketApi.cancel(detail.id), '已取消')}>作废</Button>
              )}
            </Space>

            <Divider orientation="left">签名链 <Button size="small" icon={<AuditOutlined />} onClick={verifyChain}>校验</Button></Divider>
            <List
              size="small"
              bordered
              dataSource={(detail.signatures as SignatureEntry[]) || []}
              locale={{ emptyText: '尚未签名' }}
              renderItem={(s) => (
                <List.Item>
                  <Tag color="purple">{s.stage}</Tag>
                  <Text strong style={{ marginRight: 8 }}>{s.signer}</Text>
                  <Text type="secondary" style={{ marginRight: 8 }}>{dayjs(s.signed_at).format('MM-DD HH:mm:ss')}</Text>
                  <Text code style={{ fontSize: 11 }}>{s.sig_hash.slice(0, 16)}…</Text>
                </List.Item>
              )}
            />
          </>
        )}
      </Drawer>

      <SignatureModal
        open={sigStage === 'review' || sigStage === 'approve'}
        title={sigStage === 'review' ? '审核操作票（电子签名）' : '批准操作票（电子签名）'}
        stage={sigStage || ''}
        onCancel={() => setSigStage(null)}
        onConfirm={handleSignedAction}
      />

      <Modal
        open={verifyOpen}
        title="操作票签名链校验"
        footer={null}
        onCancel={() => setVerifyOpen(false)}
        width={600}
      >
        {verifyResult && (
          <>
            <Tag color={verifyResult.all_valid ? 'green' : 'red'} style={{ marginBottom: 12 }}>
              {verifyResult.all_valid ? '✓ 所有签名有效' : '✗ 检测到无效签名'}
            </Tag>
            <List
              dataSource={verifyResult.signatures}
              renderItem={(s) => (
                <List.Item>
                  <Tag color={s.valid ? 'green' : 'red'}>{s.valid ? '✓' : '✗'}</Tag>
                  <Tag>{s.stage}</Tag>
                  <Text>{s.signer}</Text>
                  <Text type="secondary" style={{ marginLeft: 8 }}>{dayjs(s.signed_at).format('YYYY-MM-DD HH:mm:ss')}</Text>
                </List.Item>
              )}
            />
          </>
        )}
      </Modal>

      <Modal title="另存为操作模板" open={saveTplOpen} onOk={onSaveAsTemplate} onCancel={() => setSaveTplOpen(false)}>
        <Form form={saveTplForm} layout="vertical">
          <Form.Item name="name" label="模板名称" rules={[{ required: true }]}>
            <Input placeholder="如：1#引风机停电操作（标准）" />
          </Form.Item>
          <Form.Item name="description" label="模板说明"><Input.TextArea rows={2} /></Form.Item>
        </Form>
      </Modal>

      <Modal title={currentStep ? `执行步骤 ${currentStep.seq}：${currentStep.action}（电子签名）` : '执行'}
        open={stepOpen} onOk={submitStep} onCancel={() => setStepOpen(false)} okText="签名提交">
        <Form form={stepForm} layout="vertical" initialValues={{ result: 'PASS' }}>
          <Form.Item name="result" label="结果" rules={[{ required: true }]}>
            <Select options={[
              { label: '通过', value: 'PASS' }, { label: '不通过', value: 'FAIL' },
            ]} />
          </Form.Item>
          <Form.Item name="notes" label="备注"><Input.TextArea rows={3} /></Form.Item>
          <Form.Item name="signature_password" label="签名密码" rules={[{ required: true, message: '请输入登录密码' }]}>
            <Input.Password autoComplete="current-password" />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}
