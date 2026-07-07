import { useEffect, useState } from 'react'
import {
  Card, Table, Tag, Button, Space, Select, Modal, Form, Input, DatePicker, message,
  Drawer, Descriptions, List, Checkbox, Typography, Divider,
} from 'antd'
import { FileTextOutlined, PlusOutlined, ReloadOutlined, PrinterOutlined, SafetyCertificateOutlined, AuditOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { useSearchParams } from 'react-router-dom'
import { workTicketApi, equipmentApi, defectApi } from '../api'
import type { SignatureEntry, SignatureVerifyResult } from '../api'
import { useAuthStore, canRepair, canSupervise, canWrite } from '../stores/auth'
import type {
  WorkTicket, WorkTicketStatus, WorkTicketType, Equipment, Defect, SafetyMeasure,
} from '../types'
import { WT_STATUS_LABEL, WT_TYPE_LABEL } from '../types'
import SignatureModal from '../components/SignatureModal'

const { Text } = Typography

export default function WorkTicketList() {
  const role = useAuthStore((s) => s.role)
  const writable = canWrite(role)
  const repairer = canRepair(role)
  const supervisor = canSupervise(role)

  const [rows, setRows] = useState<WorkTicket[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [searchParams] = useSearchParams()
  const presetDefectId = searchParams.get('defect_id') ? Number(searchParams.get('defect_id')) : undefined
  const [filters, setFilters] = useState<{ status?: WorkTicketStatus; ticket_type?: WorkTicketType; defect_id?: number }>(
    presetDefectId ? { defect_id: presetDefectId } : {}
  )

  const [createOpen, setCreateOpen] = useState(false)
  const [createForm] = Form.useForm()
  const [equipments, setEquipments] = useState<Equipment[]>([])
  const [openDefects, setOpenDefects] = useState<Defect[]>([])

  const [detailOpen, setDetailOpen] = useState(false)
  const [detail, setDetail] = useState<WorkTicket | null>(null)
  const [sigStage, setSigStage] = useState<'issue' | 'permit' | 'complete' | 'close' | null>(null)
  const [verifyResult, setVerifyResult] = useState<SignatureVerifyResult | null>(null)
  const [verifyOpen, setVerifyOpen] = useState(false)

  const load = () => {
    setLoading(true)
    workTicketApi.list({ page, page_size: 15, ...filters })
      .then((r) => { setRows(r.data.items); setTotal(r.data.total) })
      .finally(() => setLoading(false))
  }
  useEffect(load, [page, filters])

  useEffect(() => {
    equipmentApi.list({ page_size: 100 }).then((r) => setEquipments(r.data.items))
    defectApi.list({ page_size: 100 }).then((r) =>
      setOpenDefects(r.data.items.filter((d) => !['CLOSED', 'VERIFIED', 'CANCELLED'].includes(d.status))))
    // 如果带了 defect_id 参数，自动打开起草 Modal 并预选
    if (presetDefectId) {
      defectApi.get(presetDefectId).then((r) => {
        createForm.setFieldsValue({
          equipment_id: r.data.equipment_id,
          defect_id: presetDefectId,
          work_content: `处理缺陷 ${r.data.defect_no || ''}：${r.data.title || ''}`,
          ticket_type: r.data.severity === 'CRITICAL' ? 'FIRST' : 'SECOND',
          principal: 'repairman',
        })
        setCreateOpen(true)
      }).catch(() => {})
    }
  }, [presetDefectId])

  const reloadDetail = async (id: number) => {
    const res = await workTicketApi.get(id)
    setDetail(res.data)
  }

  const openDetail = async (id: number) => {
    await reloadDetail(id)
    setDetailOpen(true)
  }

  const onCreate = async () => {
    const v = await createForm.validateFields()
    try {
      const measures = (v.safety_measures_text || '')
        .split('\n').map((line: string) => line.trim()).filter(Boolean)
        .map((measure: string, i: number) => ({ seq: i + 1, measure, checked: false }))
      const teamArr = (v.team_members_text || '').split(/[,，\s]+/).filter(Boolean)
      await workTicketApi.create({
        ticket_type: v.ticket_type,
        defect_id: v.defect_id || null,
        equipment_id: v.equipment_id,
        work_content: v.work_content,
        risk_notes: v.risk_notes,
        safety_measures: measures,
        planned_start: v.planned_start?.toISOString(),
        planned_end: v.planned_end?.toISOString(),
        principal: v.principal,
        team_members: teamArr,
      })
      message.success('工作票已起草')
      setCreateOpen(false); createForm.resetFields(); load()
    } catch (e: any) {
      message.error(e?.detail || '失败')
    }
  }

  const transition = async (action: () => Promise<any>, okMsg: string) => {
    try {
      await action()
      message.success(okMsg)
      if (detail) reloadDetail(detail.id)
      load()
    } catch (e: any) { message.error(e?.detail || '失败') }
  }

  const handleSignedAction = async (password: string, extra: Record<string, any>) => {
    if (!detail || !sigStage) return
    try {
      if (sigStage === 'issue') {
        await workTicketApi.issue(detail.id, extra.approval_notes, password)
        message.success('已签发')
      } else if (sigStage === 'permit') {
        await workTicketApi.permit(detail.id, extra.permitter, extra.notes, password)
        message.success('已许可开工')
      } else if (sigStage === 'complete') {
        await workTicketApi.complete(detail.id, extra.closing_notes, password)
        message.success('工作终结')
      } else if (sigStage === 'close') {
        await workTicketApi.close(detail.id, password)
        message.success('已归档')
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
      const res = await workTicketApi.verifySignatures(detail.id)
      setVerifyResult(res.data)
      setVerifyOpen(true)
    } catch (e: any) { message.error(e?.detail || '校验失败') }
  }

  const statusTag = (s: WorkTicketStatus) => {
    const c =
      s === 'CLOSED' ? 'green' :
      s === 'IN_WORK' ? 'blue' :
      s === 'ISSUED' ? 'cyan' :
      s === 'COMPLETED' ? 'geekblue' :
      s === 'SUBMITTED' ? 'orange' :
      s === 'CANCELLED' ? 'default' : 'gold'
    return <Tag color={c}>{WT_STATUS_LABEL[s]}</Tag>
  }

  const typeTag = (t: WorkTicketType) => {
    const c = t === 'FIRST' ? 'red' : t === 'EMERGENCY' ? 'orange' : 'blue'
    return <Tag color={c}>{WT_TYPE_LABEL[t]}</Tag>
  }

  return (
    <Card title={<Space><FileTextOutlined />工作票</Space>}
      extra={
        <Space>
          <Select<WorkTicketStatus | undefined>
            placeholder="状态" allowClear style={{ width: 120 }} value={filters.status}
            onChange={(v) => { setPage(1); setFilters({ ...filters, status: v }) }}
            options={Object.entries(WT_STATUS_LABEL).map(([k, v]) => ({ label: v, value: k }))}
          />
          <Select<WorkTicketType | undefined>
            placeholder="类型" allowClear style={{ width: 140 }} value={filters.ticket_type}
            onChange={(v) => { setPage(1); setFilters({ ...filters, ticket_type: v }) }}
            options={Object.entries(WT_TYPE_LABEL).map(([k, v]) => ({ label: v, value: k }))}
          />
          {filters.defect_id && (
            <Tag color="red" closable onClose={() => setFilters({ ...filters, defect_id: undefined })}>
              仅看缺陷 #{filters.defect_id}
            </Tag>
          )}
          <Button icon={<ReloadOutlined />} onClick={load} />
          {writable && <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>开工作票</Button>}
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
          { title: '类型', dataIndex: 'ticket_type', width: 130, render: (v) => typeTag(v) },
          { title: '设备', render: (_: any, r: WorkTicket) => <><Text>{r.equipment_name}</Text> <Text type="secondary">{r.equipment_code}</Text></> },
          { title: '工作内容', dataIndex: 'work_content', ellipsis: true },
          { title: '关联缺陷', dataIndex: 'defect_no', width: 160, render: (v) => v || '-' },
          { title: '工作负责人', dataIndex: 'principal', width: 100 },
          { title: '状态', dataIndex: 'status', width: 110, render: (v) => statusTag(v) },
          { title: '计划起止', width: 200,
            render: (_: any, r: WorkTicket) => r.planned_start
              ? `${dayjs(r.planned_start).format('MM-DD HH:mm')} ~ ${r.planned_end ? dayjs(r.planned_end).format('MM-DD HH:mm') : '?'}`
              : '-',
          },
          { title: '操作', width: 90, fixed: 'right' as const,
            render: (_: any, r: WorkTicket) => (<Button size="small" onClick={() => openDetail(r.id)}>详情</Button>) },
        ]}
        scroll={{ x: 1400 }}
      />

      {/* 起草 */}
      <Modal title="新开工作票" open={createOpen} onOk={onCreate} onCancel={() => setCreateOpen(false)} width={680}
        okText="起草保存">
        <Form form={createForm} layout="vertical" initialValues={{ ticket_type: 'SECOND' }}>
          <Form.Item name="ticket_type" label="工作票类型" rules={[{ required: true }]}>
            <Select options={Object.entries(WT_TYPE_LABEL).map(([k, v]) => ({ label: v, value: k }))} />
          </Form.Item>
          <Form.Item name="equipment_id" label="检修设备" rules={[{ required: true }]}>
            <Select
              showSearch optionFilterProp="label"
              options={equipments.map(e => ({ label: `${e.code} · ${e.name}`, value: e.id }))}
            />
          </Form.Item>
          <Form.Item name="defect_id" label="关联缺陷（可选）">
            <Select allowClear showSearch optionFilterProp="label"
              options={openDefects.map(d => ({ label: `${d.defect_no} · ${d.title}`, value: d.id }))}
            />
          </Form.Item>
          <Form.Item name="work_content" label="工作内容" rules={[{ required: true }]}>
            <Input.TextArea rows={3} placeholder="如：更换 1 号引风机轴承及动平衡校验" />
          </Form.Item>
          <Form.Item name="risk_notes" label="危险点分析">
            <Input.TextArea rows={2} placeholder="如：高处坠落、机械伤害..." />
          </Form.Item>
          <Form.Item name="safety_measures_text" label="安全措施（每行一条）">
            <Input.TextArea rows={4} placeholder={'断开 6kV 开关并悬挂"禁止合闸"\n验电后挂接地线\n工作区域围栏隔离'} />
          </Form.Item>
          <Form.Item name="principal" label="工作负责人（用户名）" initialValue="repairman" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="team_members_text" label="工作班成员（逗号分隔）">
            <Input placeholder="repairman, inspector" />
          </Form.Item>
          <Space>
            <Form.Item name="planned_start" label="计划开始"><DatePicker showTime /></Form.Item>
            <Form.Item name="planned_end" label="计划结束"><DatePicker showTime /></Form.Item>
          </Space>
        </Form>
      </Modal>

      <Drawer
        title={detail ? `${detail.ticket_no} · ${WT_TYPE_LABEL[detail.ticket_type]}` : '工作票详情'}
        open={detailOpen} onClose={() => setDetailOpen(false)} width={720}
        extra={detail && (
          <Button
            icon={<PrinterOutlined />}
            onClick={() => window.open(`/work-tickets/${detail.id}/print`, '_blank')}
          >
            打印 / PDF
          </Button>
        )}
      >
        {detail && (
          <>
            <Space style={{ marginBottom: 12 }}>
              {statusTag(detail.status)}
              {typeTag(detail.ticket_type)}
              {detail.defect_no && <Tag color="red">缺陷 {detail.defect_no}</Tag>}
            </Space>
            <Descriptions column={2} size="small" bordered>
              <Descriptions.Item label="设备" span={2}>{detail.equipment_name} · {detail.equipment_code}</Descriptions.Item>
              <Descriptions.Item label="工作内容" span={2}>{detail.work_content}</Descriptions.Item>
              <Descriptions.Item label="危险点">{detail.risk_notes || '-'}</Descriptions.Item>
              <Descriptions.Item label="计划起止">
                {detail.planned_start ? dayjs(detail.planned_start).format('MM-DD HH:mm') : '-'} ~ {detail.planned_end ? dayjs(detail.planned_end).format('MM-DD HH:mm') : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="申请人">{detail.applicant}</Descriptions.Item>
              <Descriptions.Item label="工作负责人">{detail.principal}</Descriptions.Item>
              <Descriptions.Item label="签发人">{detail.issuer || '-'}</Descriptions.Item>
              <Descriptions.Item label="许可人">{detail.permitter || '-'}</Descriptions.Item>
              <Descriptions.Item label="工作班成员" span={2}>{(detail.team_members || []).join('、') || '-'}</Descriptions.Item>
            </Descriptions>

            <Divider orientation="left">安全措施</Divider>
            <List
              size="small"
              bordered
              dataSource={detail.safety_measures || []}
              renderItem={(m: SafetyMeasure) => (
                <List.Item
                  actions={
                    repairer && (detail.status === 'ISSUED' || detail.status === 'IN_WORK') && !m.checked
                      ? [<Button size="small" onClick={() => transition(() => workTicketApi.checkSafety(detail.id, m.seq), '已勾选')}>勾选</Button>]
                      : []
                  }
                >
                  <Checkbox checked={!!m.checked} disabled style={{ marginRight: 8 }} />
                  <span style={{ flex: 1 }}>{m.seq}. {m.measure}</span>
                  {m.checked_by && <Text type="secondary" style={{ fontSize: 12 }}>by {m.checked_by} {m.checked_at ? dayjs(m.checked_at).format('MM-DD HH:mm') : ''}</Text>}
                </List.Item>
              )}
              locale={{ emptyText: '未配置安全措施' }}
            />

            <Divider orientation="left">流转</Divider>
            <Space wrap>
              {writable && detail.status === 'DRAFT' && (
                <Button onClick={() => transition(() => workTicketApi.submit(detail.id), '已提交')}>提交</Button>
              )}
              {supervisor && detail.status === 'SUBMITTED' && (
                <Button type="primary" icon={<SafetyCertificateOutlined />} onClick={() => setSigStage('issue')}>签发（电子签名）</Button>
              )}
              {supervisor && detail.status === 'ISSUED' && (
                <Button type="primary" icon={<SafetyCertificateOutlined />} onClick={() => setSigStage('permit')}>许可开工（签名）</Button>
              )}
              {repairer && detail.status === 'IN_WORK' && (
                <Button type="primary" icon={<SafetyCertificateOutlined />} onClick={() => setSigStage('complete')}>工作终结（签名）</Button>
              )}
              {supervisor && detail.status === 'COMPLETED' && (
                <Button type="primary" icon={<SafetyCertificateOutlined />} onClick={() => setSigStage('close')}>收票归档（签名）</Button>
              )}
              {supervisor && !['CLOSED', 'COMPLETED', 'CANCELLED'].includes(detail.status) && (
                <Button danger onClick={() => transition(() => workTicketApi.cancel(detail.id), '已取消')}>作废</Button>
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
        open={sigStage !== null}
        title={
          sigStage === 'issue' ? '签发工作票（电子签名）' :
          sigStage === 'permit' ? '许可开工（电子签名）' :
          sigStage === 'complete' ? '工作终结（电子签名）' :
          sigStage === 'close' ? '收票归档（电子签名）' : '电子签名'
        }
        stage={sigStage || ''}
        extraForm={
          sigStage === 'issue' ? (
            <Form.Item name="approval_notes" label="签发备注"><Input.TextArea rows={2} /></Form.Item>
          ) : sigStage === 'permit' ? (
            <>
              <Form.Item name="permitter" label="许可人"><Input placeholder="默认当前用户" /></Form.Item>
              <Form.Item name="notes" label="备注"><Input.TextArea rows={2} /></Form.Item>
            </>
          ) : sigStage === 'complete' ? (
            <Form.Item name="closing_notes" label="收尾说明"><Input.TextArea rows={2} /></Form.Item>
          ) : null
        }
        onCancel={() => setSigStage(null)}
        onConfirm={handleSignedAction}
      />

      <Modal
        open={verifyOpen}
        title="签名链校验"
        footer={null}
        onCancel={() => setVerifyOpen(false)}
        width={600}
      >
        {verifyResult && (
          <>
            <Tag color={verifyResult.all_valid ? 'green' : 'red'} style={{ marginBottom: 12 }}>
              {verifyResult.all_valid ? '✓ 所有签名有效，未被篡改' : '✗ 检测到无效签名'}
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
    </Card>
  )
}
