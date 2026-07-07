import { useEffect, useState } from 'react'
import {
  Card, Table, Tag, Button, Space, Select, Input, Form, Modal, message, Progress,
  Drawer, Descriptions, Tabs, Typography, List, Empty, Statistic, Row, Col,
} from 'antd'
import { PlusOutlined, ToolOutlined, ReloadOutlined, EyeOutlined, QrcodeOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { equipmentApi } from '../api'
import { useAuthStore, canWrite } from '../stores/auth'
import {
  Equipment, EquipmentSystem, Criticality, EquipmentStatus, EquipmentProfile,
  SYSTEM_LABEL, CRITICALITY_LABEL, EQ_STATUS_LABEL,
  SEVERITY_LABEL, DEFECT_STATUS_LABEL, WT_STATUS_LABEL, WT_TYPE_LABEL,
} from '../types'

const { Text } = Typography

const { Search } = Input

export default function EquipmentList() {
  const role = useAuthStore((s) => s.role)
  const writable = canWrite(role)

  const [rows, setRows] = useState<Equipment[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [filters, setFilters] = useState<{
    equipment_system?: EquipmentSystem
    criticality?: Criticality
    status?: EquipmentStatus
    keyword?: string
  }>({})
  const [createOpen, setCreateOpen] = useState(false)
  const [form] = Form.useForm()

  const [profileOpen, setProfileOpen] = useState(false)
  const [profile, setProfile] = useState<EquipmentProfile | null>(null)
  const [profileLoading, setProfileLoading] = useState(false)

  const openProfile = async (id: number) => {
    setProfileLoading(true); setProfileOpen(true)
    try {
      const r = await equipmentApi.profile(id)
      setProfile(r.data)
    } catch (e: any) {
      message.error(e?.detail || '加载失败')
    } finally { setProfileLoading(false) }
  }

  const load = () => {
    setLoading(true)
    equipmentApi.list({ page, page_size: 15, ...filters })
      .then((r) => { setRows(r.data.items); setTotal(r.data.total) })
      .finally(() => setLoading(false))
  }
  useEffect(load, [page, filters])

  const onCreate = async () => {
    const values = await form.validateFields()
    try {
      await equipmentApi.create(values)
      message.success('已登记')
      setCreateOpen(false)
      form.resetFields()
      load()
    } catch (e: any) { message.error(e?.detail || '失败') }
  }

  return (
    <Card
      title={<Space><ToolOutlined />设备台账</Space>}
      extra={
        <Space>
          <Select<EquipmentSystem | undefined>
            placeholder="系统" allowClear style={{ width: 130 }}
            value={filters.equipment_system}
            onChange={(v) => { setPage(1); setFilters({ ...filters, equipment_system: v }) }}
            options={Object.entries(SYSTEM_LABEL).map(([k, v]) => ({ label: v, value: k }))}
          />
          <Select<Criticality | undefined>
            placeholder="等级" allowClear style={{ width: 110 }}
            value={filters.criticality}
            onChange={(v) => { setPage(1); setFilters({ ...filters, criticality: v }) }}
            options={Object.entries(CRITICALITY_LABEL).map(([k, v]) => ({ label: v, value: k }))}
          />
          <Select<EquipmentStatus | undefined>
            placeholder="状态" allowClear style={{ width: 110 }}
            value={filters.status}
            onChange={(v) => { setPage(1); setFilters({ ...filters, status: v }) }}
            options={Object.entries(EQ_STATUS_LABEL).map(([k, v]) => ({ label: v, value: k }))}
          />
          <Search placeholder="编号/名称" allowClear style={{ width: 180 }}
            onSearch={(v) => { setPage(1); setFilters({ ...filters, keyword: v || undefined }) }} />
          <Button icon={<ReloadOutlined />} onClick={load} />
          <Button icon={<QrcodeOutlined />} onClick={() => window.open('/equipment-qr-print', '_blank')}>批量 QR 打印</Button>
          {writable && <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>登记</Button>}
        </Space>
      }
    >
      <Table
        rowKey="id"
        loading={loading}
        dataSource={rows}
        pagination={{ current: page, pageSize: 15, total, onChange: setPage }}
        columns={[
          { title: '编号', dataIndex: 'code', width: 140 },
          { title: '名称', dataIndex: 'name' },
          { title: '系统', dataIndex: 'equipment_system', width: 110,
            render: (v) => SYSTEM_LABEL[v as EquipmentSystem] },
          { title: '等级', dataIndex: 'criticality', width: 80,
            render: (v) => <Tag color={v === 'A' ? 'red' : v === 'B' ? 'orange' : 'default'}>{CRITICALITY_LABEL[v as Criticality]}</Tag> },
          { title: '状态', dataIndex: 'status', width: 90,
            render: (v) => <Tag color={v === 'RUNNING' ? 'green' : v === 'MAINTENANCE' ? 'orange' : v === 'STANDBY' ? 'blue' : 'default'}>{EQ_STATUS_LABEL[v as EquipmentStatus]}</Tag> },
          { title: '健康度', dataIndex: 'health_score', width: 130,
            render: (v) => <Progress percent={v} size="small" strokeColor={v >= 85 ? '#52c41a' : v >= 60 ? '#faad14' : '#fa541c'} /> },
          { title: '位置', dataIndex: 'location', width: 140 },
          { title: '厂家', dataIndex: 'manufacturer', width: 120 },
          {
            title: '操作', width: 220, fixed: 'right' as const,
            render: (_: any, r: Equipment) => (
              <Space size="small">
                <Button size="small" icon={<EyeOutlined />} onClick={() => openProfile(r.id)}>详情</Button>
{writable && r.status === 'RUNNING' && <Button size="small" onClick={async () => { await equipmentApi.toMaintenance(r.id); message.success('已转检修'); load() }}>转检修</Button>}
{writable && (r.status === 'MAINTENANCE' || r.status === 'STANDBY') && <Button size="small" type="primary" onClick={async () => { await equipmentApi.restore(r.id); message.success('已恢复'); load() }}>恢复</Button>}
              </Space>
            ),
          },
        ]}
        scroll={{ x: 1100 }}
      />

      <Drawer
        title={profile ? `${profile.equipment.code} · ${profile.equipment.name}` : '设备 360'}
        open={profileOpen} onClose={() => { setProfileOpen(false); setProfile(null) }}
        width={780}
        loading={profileLoading}
      >
        {profile && (
          <>
            <Space size={8} wrap style={{ marginBottom: 12 }}>
              <Tag color={profile.equipment.criticality === 'A' ? 'red' : profile.equipment.criticality === 'B' ? 'orange' : 'default'}>
                {CRITICALITY_LABEL[profile.equipment.criticality]}
              </Tag>
              <Tag>{SYSTEM_LABEL[profile.equipment.equipment_system]}</Tag>
              <Tag color={profile.equipment.status === 'RUNNING' ? 'green' : profile.equipment.status === 'MAINTENANCE' ? 'orange' : 'default'}>
                {EQ_STATUS_LABEL[profile.equipment.status]}
              </Tag>
              {profile.open_defect_count > 0 && <Tag color="red">未结缺陷 {profile.open_defect_count}</Tag>}
              {profile.open_ticket_count > 0 && <Tag color="blue">在工/待办票 {profile.open_ticket_count}</Tag>}
            </Space>

            <Row gutter={12} style={{ marginBottom: 12 }}>
              <Col span={6}><Statistic title="健康度" value={profile.equipment.health_score} suffix="/100" /></Col>
              <Col span={6}><Statistic title="90天点检" value={profile.record_stats.total} /></Col>
              <Col span={6}><Statistic title="异常记录" value={(profile.record_stats.abnormal || 0) + (profile.record_stats.severe || 0)}
                valueStyle={{ color: ((profile.record_stats.abnormal || 0) + (profile.record_stats.severe || 0)) > 0 ? '#fa541c' : undefined }} /></Col>
              <Col span={6}><Statistic title="备件领用" value={profile.spare_usage.length} /></Col>
            </Row>

            <Descriptions column={2} size="small" bordered>
              <Descriptions.Item label="位置">{profile.equipment.location || '-'}</Descriptions.Item>
              <Descriptions.Item label="型号">{profile.equipment.model || '-'}</Descriptions.Item>
              <Descriptions.Item label="厂家">{profile.equipment.manufacturer || '-'}</Descriptions.Item>
              <Descriptions.Item label="投运日期">{profile.equipment.install_date || '-'}</Descriptions.Item>
              <Descriptions.Item label="QR" span={2}>{profile.equipment.qr_code || '-'}</Descriptions.Item>
            </Descriptions>

            <Tabs
              style={{ marginTop: 16 }}
              items={[
                {
                  key: 'records', label: `近期点检 (${profile.recent_records.length})`,
                  children: profile.recent_records.length === 0 ? <Empty description="近 90 天无点检记录" /> : (
                    <List size="small" bordered dataSource={profile.recent_records}
                      renderItem={(r) => (
                        <List.Item>
                          <Space wrap>
                            <Tag color={r.status === 'NORMAL' ? 'green' : r.status === 'SEVERE' ? 'red' : 'orange'}>
                              {r.status === 'NORMAL' ? '正常' : r.status === 'SEVERE' ? '严重' : '异常'}
                            </Tag>
                            <Text>{r.finding || '正常'}</Text>
                            <Text type="secondary" style={{ fontSize: 12 }}>{r.recorded_by} · {dayjs(r.recorded_at).format('MM-DD HH:mm')}</Text>
                            {r.defect_id && <Tag color="red">缺陷#{r.defect_id}</Tag>}
                          </Space>
                        </List.Item>
                      )} />
                  ),
                },
                {
                  key: 'defects', label: `近期缺陷 (${profile.recent_defects.length})`,
                  children: profile.recent_defects.length === 0 ? <Empty description="近 90 天无缺陷" /> : (
                    <List size="small" bordered dataSource={profile.recent_defects}
                      renderItem={(d) => (
                        <List.Item>
                          <Space wrap>
                            <Tag color={d.severity === 'CRITICAL' ? 'red' : d.severity === 'MAJOR' ? 'orange' : 'default'}>
                              {SEVERITY_LABEL[d.severity as keyof typeof SEVERITY_LABEL] || d.severity}
                            </Tag>
                            <Tag>{DEFECT_STATUS_LABEL[d.status as keyof typeof DEFECT_STATUS_LABEL] || d.status}</Tag>
                            <Text strong>{d.defect_no}</Text>
                            <Text>{d.title}</Text>
                            <Text type="secondary" style={{ fontSize: 12 }}>{dayjs(d.reported_at).format('MM-DD HH:mm')}</Text>
                          </Space>
                        </List.Item>
                      )} />
                  ),
                },
                {
                  key: 'tickets', label: `工作票 (${profile.recent_tickets.length})`,
                  children: profile.recent_tickets.length === 0 ? <Empty description="无工作票" /> : (
                    <List size="small" bordered dataSource={profile.recent_tickets}
                      renderItem={(t) => (
                        <List.Item>
                          <Space wrap>
                            <Tag color={t.ticket_type === 'FIRST' ? 'red' : t.ticket_type === 'EMERGENCY' ? 'orange' : 'blue'}>
                              {WT_TYPE_LABEL[t.ticket_type as keyof typeof WT_TYPE_LABEL] || t.ticket_type}
                            </Tag>
                            <Tag>{WT_STATUS_LABEL[t.status as keyof typeof WT_STATUS_LABEL] || t.status}</Tag>
                            <Text strong>{t.ticket_no}</Text>
                            <Text type="secondary">{t.work_content}</Text>
                            <Text type="secondary" style={{ fontSize: 12 }}>{t.principal} · {dayjs(t.created_at).format('MM-DD HH:mm')}</Text>
                          </Space>
                        </List.Item>
                      )} />
                  ),
                },
                {
                  key: 'spares', label: `备件领用 (${profile.spare_usage.length})`,
                  children: profile.spare_usage.length === 0 ? <Empty description="无备件领用" /> : (
                    <List size="small" bordered dataSource={profile.spare_usage}
                      renderItem={(s) => (
                        <List.Item>
                          <Space wrap>
                            <Tag color="orange">出库 {s.qty}</Tag>
                            <Text strong>{s.spare_part_code}</Text>
                            <Text>{s.spare_part_name}</Text>
                            {s.defect_id && <Tag color="red">缺陷#{s.defect_id}</Tag>}
                            {s.work_ticket_id && <Tag color="blue">票#{s.work_ticket_id}</Tag>}
                            <Text type="secondary" style={{ fontSize: 12 }}>{s.operator} · {dayjs(s.created_at).format('MM-DD HH:mm')}</Text>
                          </Space>
                        </List.Item>
                      )} />
                  ),
                },
              ]}
            />
          </>
        )}
      </Drawer>

      <Modal title="登记新设备" open={createOpen} onOk={onCreate} onCancel={() => setCreateOpen(false)} width={600}>
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="设备名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="equipment_system" label="所属系统" rules={[{ required: true }]}>
            <Select options={Object.entries(SYSTEM_LABEL).map(([k, v]) => ({ label: v, value: k }))} />
          </Form.Item>
          <Form.Item name="criticality" label="重要性等级" initialValue="C">
            <Select options={Object.entries(CRITICALITY_LABEL).map(([k, v]) => ({ label: v, value: k }))} />
          </Form.Item>
          <Form.Item name="location" label="位置"><Input /></Form.Item>
          <Form.Item name="model" label="型号"><Input /></Form.Item>
          <Form.Item name="manufacturer" label="厂家"><Input /></Form.Item>
          <Form.Item name="notes" label="备注"><Input.TextArea rows={2} /></Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}
