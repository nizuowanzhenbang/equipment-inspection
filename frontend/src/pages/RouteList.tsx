import { useEffect, useState } from 'react'
import { Card, Table, Tag, Button, Space, Drawer, List, Typography } from 'antd'
import { NodeIndexOutlined, ReloadOutlined } from '@ant-design/icons'
import { routeApi } from '../api'
import { InspectionRoute, InspectionPoint, SYSTEM_LABEL } from '../types'

const { Text, Paragraph } = Typography

const FREQ_LABEL: Record<string, string> = {
  SHIFT: '班次', DAILY: '每日', WEEKLY: '每周', MONTHLY: '每月',
}

export default function RouteList() {
  const [rows, setRows] = useState<InspectionRoute[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [detail, setDetail] = useState<InspectionRoute | null>(null)

  const load = () => {
    setLoading(true)
    routeApi.list({ page, page_size: 15 })
      .then((r) => { setRows(r.data.items); setTotal(r.data.total) })
      .finally(() => setLoading(false))
  }
  useEffect(load, [page])

  const openDetail = async (id: number) => {
    const res = await routeApi.get(id)
    setDetail(res.data)
    setDrawerOpen(true)
  }

  return (
    <Card title={<Space><NodeIndexOutlined />点检路线</Space>}
      extra={<Button icon={<ReloadOutlined />} onClick={load} />}>
      <Table
        rowKey="id"
        loading={loading}
        dataSource={rows}
        pagination={{ current: page, pageSize: 15, total, onChange: setPage }}
        columns={[
          { title: '编号', dataIndex: 'route_no', width: 100 },
          { title: '名称', dataIndex: 'name' },
          { title: '主要系统', dataIndex: 'equipment_system', width: 110,
            render: (v) => v ? (SYSTEM_LABEL[v as keyof typeof SYSTEM_LABEL] || v) : '-' },
          { title: '频率', dataIndex: 'frequency', width: 90,
            render: (v) => <Tag color="blue">{FREQ_LABEL[v] || v}</Tag> },
          { title: '测点数', dataIndex: 'point_count', width: 90 },
          { title: '预计耗时', dataIndex: 'estimated_duration', width: 110, render: (v) => `${v} 分钟` },
          { title: '启用', dataIndex: 'is_active', width: 70,
            render: (v) => v ? <Tag color="green">是</Tag> : <Tag>否</Tag> },
          { title: '操作', width: 100, fixed: 'right' as const,
            render: (_: any, r: InspectionRoute) => (
              <Button size="small" onClick={() => openDetail(r.id)}>查看测点</Button>
            ) },
        ]}
      />

      <Drawer
        title={detail ? `${detail.route_no} · ${detail.name}` : '路线详情'}
        open={drawerOpen} onClose={() => setDrawerOpen(false)} width={620}
      >
        {detail && (
          <>
            <Paragraph type="secondary">
              {detail.equipment_system && <>{SYSTEM_LABEL[detail.equipment_system as keyof typeof SYSTEM_LABEL] || detail.equipment_system} · </>}
              {FREQ_LABEL[detail.frequency]} · 预计 {detail.estimated_duration} 分钟
            </Paragraph>
            <List
              dataSource={detail.points || []}
              renderItem={(p: InspectionPoint) => (
                <List.Item>
                  <List.Item.Meta
                    title={<Space><Tag>{p.point_no}</Tag><Text strong>#{p.sequence} {p.equipment_name}</Text><Text type="secondary">{p.equipment_code}</Text></Space>}
                    description={
                      <>
                        <div>检查项：{(p.check_items || []).map(c => `${c.name}${c.unit ? `(${c.unit})` : ''}`).join('、')}</div>
                        {p.standard && <div style={{ color: '#888' }}>标准：{p.standard}</div>}
                      </>
                    }
                  />
                </List.Item>
              )}
            />
          </>
        )}
      </Drawer>
    </Card>
  )
}
