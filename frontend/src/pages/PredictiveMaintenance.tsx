import { useEffect, useState } from 'react'
import { Card, Table, Tag, Space, Button, Statistic, Row, Col, Typography, Progress } from 'antd'
import { ThunderboltOutlined, ReloadOutlined } from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import { predictiveApi } from '../api'
import type { PredictiveRiskItem } from '../types'
import { SYSTEM_LABEL, CRITICALITY_LABEL, EquipmentSystem, Criticality } from '../types'

const { Text, Paragraph } = Typography

export default function PredictiveMaintenance() {
  const [items, setItems] = useState<PredictiveRiskItem[]>([])
  const [loading, setLoading] = useState(false)

  const load = () => {
    setLoading(true)
    predictiveApi.ranking(30)
      .then((r) => setItems(r.data))
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  const high = items.filter(i => i.risk_level === 'HIGH').length
  const medium = items.filter(i => i.risk_level === 'MEDIUM').length
  const low = items.filter(i => i.risk_level === 'LOW').length
  const avgProb = items.length ? Math.round(items.reduce((s, i) => s + i.failure_probability, 0) / items.length * 100) : 0

  const top10 = items.slice(0, 10)
  const scatterOption = {
    tooltip: {
      trigger: 'item',
      formatter: (p: any) => {
        const d = p.data._raw as PredictiveRiskItem
        return `${d.code} ${d.name}<br/>风险分=${d.risk_score}<br/>失效概率=${(d.failure_probability * 100).toFixed(1)}%<br/>近 90 天缺陷=${d.defects_90d}`
      },
    },
    grid: { left: 50, right: 30, top: 30, bottom: 50 },
    xAxis: { type: 'value', name: '健康度' },
    yAxis: { type: 'value', name: '风险分', min: 0, max: 100 },
    series: [{
      type: 'scatter',
      data: items.map(i => ({
        value: [i.health_score, i.risk_score],
        _raw: i,
        itemStyle: {
          color: i.risk_level === 'HIGH' ? '#ff4d4f' : i.risk_level === 'MEDIUM' ? '#faad14' : '#52c41a',
        },
        symbolSize: i.criticality === 'A' ? 18 : i.criticality === 'B' ? 12 : 8,
      })),
    }],
  }

  const levelTag = (l: string) => {
    if (l === 'HIGH') return <Tag color="red">高风险</Tag>
    if (l === 'MEDIUM') return <Tag color="orange">中风险</Tag>
    return <Tag color="green">低风险</Tag>
  }

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card>
        <Row gutter={16}>
          <Col span={6}><Statistic title="高风险设备" value={high} valueStyle={{ color: '#ff4d4f' }} /></Col>
          <Col span={6}><Statistic title="中风险设备" value={medium} valueStyle={{ color: '#faad14' }} /></Col>
          <Col span={6}><Statistic title="低风险设备" value={low} valueStyle={{ color: '#52c41a' }} /></Col>
          <Col span={6}><Statistic title="平均失效概率" value={avgProb} suffix="%" /></Col>
        </Row>
      </Card>

      <Card title={<Space><ThunderboltOutlined />风险分布（健康度 × 风险分）</Space>}
        extra={<Button icon={<ReloadOutlined />} size="small" onClick={load}>刷新</Button>}>
        <ReactECharts option={scatterOption} style={{ height: 320 }} />
        <Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0, fontSize: 12 }}>
          点大小代表设备等级（A 最大），颜色代表风险等级。理想区域：右下（健康度高、风险分低）。
        </Paragraph>
      </Card>

      <Card title="重点关注 Top 30">
        <Table
          rowKey="equipment_id"
          loading={loading}
          dataSource={items}
          pagination={{ pageSize: 15 }}
          columns={[
            { title: '编号', dataIndex: 'code', width: 140 },
            { title: '设备', dataIndex: 'name' },
            { title: '系统', dataIndex: 'equipment_system', width: 100,
              render: (v) => SYSTEM_LABEL[v as EquipmentSystem] || v },
            { title: '等级', dataIndex: 'criticality', width: 90,
              render: (v) => <Tag color={v === 'A' ? 'red' : v === 'B' ? 'orange' : 'default'}>{CRITICALITY_LABEL[v as Criticality]}</Tag> },
            { title: '健康度', dataIndex: 'health_score', width: 110,
              render: (v) => <Progress percent={v} size="small" status={v < 60 ? 'exception' : v < 80 ? 'active' : 'success'} /> },
            { title: '90天缺陷', dataIndex: 'defects_90d', width: 90 },
            { title: '紧急', dataIndex: 'critical_90d', width: 70,
              render: (v) => v > 0 ? <Tag color="red">{v}</Tag> : v },
            { title: '点检异常', dataIndex: 'abnormal_records_90d', width: 100 },
            { title: '失效概率', dataIndex: 'failure_probability', width: 100,
              render: (v) => <Text strong style={{ color: v >= 0.6 ? '#ff4d4f' : v >= 0.4 ? '#faad14' : '#52c41a' }}>{(v * 100).toFixed(1)}%</Text> },
            { title: '风险分', dataIndex: 'risk_score', width: 90,
              render: (v: number) => <Text strong>{v}</Text> },
            { title: '风险等级', dataIndex: 'risk_level', width: 100, render: (v) => levelTag(v) },
            { title: '建议', dataIndex: 'recommendation', ellipsis: true },
          ]}
          scroll={{ x: 1400 }}
        />
      </Card>
    </Space>
  )
}
