import { useEffect, useState } from 'react'
import { Row, Col, Card, Statistic, Table, Tag, Progress, Typography, Space } from 'antd'
import {
  ToolOutlined, FireOutlined, BugOutlined, HeartOutlined,
  CheckCircleOutlined, WarningOutlined,
  FileTextOutlined, OrderedListOutlined, AppstoreOutlined,
} from '@ant-design/icons'
import { Link } from 'react-router-dom'
import ReactECharts from 'echarts-for-react'
import { dashboardApi } from '../api'
import {
  DashboardOverview, DefectTrendItem, SystemDistItem,
  TopFaultyItem, HealthRankItem,
  SYSTEM_LABEL, CRITICALITY_LABEL, EQ_STATUS_LABEL,
} from '../types'

const { Title } = Typography

export default function Dashboard() {
  const [overview, setOverview] = useState<DashboardOverview | null>(null)
  const [trend, setTrend] = useState<DefectTrendItem[]>([])
  const [sysDist, setSysDist] = useState<SystemDistItem[]>([])
  const [topFaulty, setTopFaulty] = useState<TopFaultyItem[]>([])
  const [healthRank, setHealthRank] = useState<HealthRankItem[]>([])

  useEffect(() => {
    Promise.all([
      dashboardApi.overview(),
      dashboardApi.defectTrend(30),
      dashboardApi.systemDistribution(),
      dashboardApi.topFaulty(5),
      dashboardApi.healthRanking(10),
    ]).then(([o, t, s, f, r]) => {
      setOverview(o.data)
      setTrend(t.data)
      setSysDist(s.data)
      setTopFaulty(f.data)
      setHealthRank(r.data)
    })
  }, [])

  const trendOption = {
    tooltip: { trigger: 'axis' },
    legend: { data: ['新增缺陷', '关闭缺陷'] },
    grid: { left: 40, right: 20, top: 40, bottom: 40 },
    xAxis: { type: 'category', data: trend.map(t => t.date.slice(5)) },
    yAxis: { type: 'value' },
    series: [
      { name: '新增缺陷', type: 'line', smooth: true, data: trend.map(t => t.new), itemStyle: { color: '#fa541c' } },
      { name: '关闭缺陷', type: 'line', smooth: true, data: trend.map(t => t.closed), itemStyle: { color: '#52c41a' } },
    ],
  }

  const sysOption = {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { data: ['设备数', '未关缺陷'] },
    grid: { left: 40, right: 20, top: 40, bottom: 60 },
    xAxis: { type: 'category', data: sysDist.map(s => SYSTEM_LABEL[s.system as keyof typeof SYSTEM_LABEL] || s.system), axisLabel: { rotate: 30 } },
    yAxis: { type: 'value' },
    series: [
      { name: '设备数', type: 'bar', data: sysDist.map(s => s.equipment_count), itemStyle: { color: '#1677ff' } },
      { name: '未关缺陷', type: 'bar', data: sysDist.map(s => s.open_defects), itemStyle: { color: '#fa541c' } },
    ],
  }

  return (
    <div>
      <Title level={4}>发电厂设备运行总览</Title>
      <Row gutter={16}>
        <Col span={6}>
          <Card><Statistic title="设备总数" value={overview?.equipment.total ?? 0} prefix={<ToolOutlined />} suffix={`/ A级 ${overview?.equipment.criticality_a ?? 0}`} /></Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="今日点检完成率" value={overview?.today_tasks.completion_rate ?? 0} suffix="%" prefix={<CheckCircleOutlined />} valueStyle={{ color: (overview?.today_tasks.completion_rate ?? 0) >= 90 ? '#52c41a' : '#fa541c' }} />
            <span style={{ fontSize: 12, color: '#888' }}>完成 {overview?.today_tasks.completed ?? 0}/{overview?.today_tasks.total ?? 0}，漏检 {overview?.today_tasks.missed ?? 0}</span>
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="待处理缺陷" value={overview?.defects.open ?? 0} prefix={<BugOutlined />} valueStyle={{ color: '#fa541c' }} />
            <Space size={4} style={{ fontSize: 12, color: '#888' }}>
              <Tag color="red">紧急 {overview?.defects.critical_open ?? 0}</Tag>
              <Tag color="orange">超期 {overview?.defects.overdue ?? 0}</Tag>
            </Space>
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="平均设备健康度" value={overview?.avg_health_score ?? 100} suffix="/100" prefix={<HeartOutlined />} />
            <Progress percent={overview?.avg_health_score ?? 100} showInfo={false} strokeColor={(overview?.avg_health_score ?? 100) >= 85 ? '#52c41a' : '#fa541c'} />
          </Card>
        </Col>
      </Row>

      {(overview?.tickets || overview?.inventory) && (
        <Row gutter={16} style={{ marginTop: 16 }}>
          <Col span={8}>
            <Card>
              <Link to="/work-tickets">
                <Statistic title="在工/已签发工作票" value={overview?.tickets?.work_in_progress ?? 0} prefix={<FileTextOutlined />} valueStyle={{ color: '#1677ff' }} />
                <span style={{ fontSize: 12, color: '#888' }}>待签发：{overview?.tickets?.work_pending_approval ?? 0}</span>
              </Link>
            </Card>
          </Col>
          <Col span={8}>
            <Card>
              <Link to="/operation-tickets">
                <Statistic title="执行中操作票" value={overview?.tickets?.operation_executing ?? 0} prefix={<OrderedListOutlined />} valueStyle={{ color: '#722ed1' }} />
                <span style={{ fontSize: 12, color: '#888' }}>分步执行中</span>
              </Link>
            </Card>
          </Col>
          <Col span={8}>
            <Card>
              <Link to="/spare-parts">
                <Statistic title="备件低库存预警" value={overview?.inventory?.low_stock_items ?? 0} prefix={<AppstoreOutlined />} valueStyle={{ color: (overview?.inventory?.low_stock_items ?? 0) > 0 ? '#ff4d4f' : '#52c41a' }} />
                <span style={{ fontSize: 12, color: '#888' }}>低于安全库存的物料数</span>
              </Link>
            </Card>
          </Col>
        </Row>
      )}

      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col span={14}>
          <Card title={<Space><WarningOutlined />近 30 天缺陷新增/关闭趋势</Space>}>
            <ReactECharts option={trendOption} style={{ height: 320 }} />
          </Card>
        </Col>
        <Col span={10}>
          <Card title={<Space><FireOutlined />各系统设备与缺陷分布</Space>}>
            <ReactECharts option={sysOption} style={{ height: 320 }} />
          </Card>
        </Col>
      </Row>

      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col span={12}>
          <Card title="近 30 天高发故障设备 TOP 5" size="small">
            <Table
              dataSource={topFaulty}
              rowKey="equipment_id"
              size="small"
              pagination={false}
              columns={[
                { title: '编号', dataIndex: 'code', width: 120 },
                { title: '名称', dataIndex: 'name' },
                { title: '等级', dataIndex: 'criticality', width: 80,
                  render: (v) => <Tag color={v === 'A' ? 'red' : v === 'B' ? 'orange' : 'default'}>{CRITICALITY_LABEL[v as keyof typeof CRITICALITY_LABEL]}</Tag> },
                { title: '健康度', dataIndex: 'health_score', width: 100,
                  render: (v) => <Progress percent={v} size="small" /> },
                { title: '30 天缺陷', dataIndex: 'defect_count_30d', width: 100 },
              ]}
            />
          </Card>
        </Col>
        <Col span={12}>
          <Card title="设备健康度倒序榜（关键设备优先）" size="small">
            <Table
              dataSource={healthRank}
              rowKey="id"
              size="small"
              pagination={false}
              columns={[
                { title: '编号', dataIndex: 'code', width: 120 },
                { title: '名称', dataIndex: 'name' },
                { title: '等级', dataIndex: 'criticality', width: 80,
                  render: (v) => <Tag color={v === 'A' ? 'red' : v === 'B' ? 'orange' : 'default'}>{CRITICALITY_LABEL[v as keyof typeof CRITICALITY_LABEL]}</Tag> },
                { title: '状态', dataIndex: 'status', width: 80,
                  render: (v) => <Tag color={v === 'RUNNING' ? 'green' : v === 'MAINTENANCE' ? 'orange' : 'default'}>{EQ_STATUS_LABEL[v as keyof typeof EQ_STATUS_LABEL]}</Tag> },
                { title: '健康度', dataIndex: 'health_score', width: 110,
                  render: (v) => <Progress percent={v} size="small" strokeColor={v >= 85 ? '#52c41a' : v >= 60 ? '#faad14' : '#fa541c'} /> },
              ]}
            />
          </Card>
        </Col>
      </Row>
    </div>
  )
}
