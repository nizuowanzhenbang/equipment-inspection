import { useEffect, useState } from 'react'
import { Card, Row, Col, Table, Tag, Button, Space, DatePicker, Typography, Statistic, message } from 'antd'
import { DownloadOutlined, ReloadOutlined } from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import dayjs, { Dayjs } from 'dayjs'
import { reportApi, schedulerApi, downloadCsv } from '../api'
import type { MonthlyReportItem, AvailabilityItem, SchedulerJob } from '../types'
import { SYSTEM_LABEL, EquipmentSystem } from '../types'

const { Text } = Typography
const { RangePicker } = DatePicker

export default function Reports() {
  const [monthly, setMonthly] = useState<MonthlyReportItem[]>([])
  const [avail, setAvail] = useState<AvailabilityItem[]>([])
  const [jobs, setJobs] = useState<SchedulerJob[]>([])
  const [exporting, setExporting] = useState(false)
  const [range, setRange] = useState<[Dayjs, Dayjs] | null>([dayjs().subtract(30, 'day'), dayjs()])

  const load = async () => {
    const [m, a, j] = await Promise.all([
      reportApi.monthly(6),
      reportApi.availability(30),
      schedulerApi.jobs().catch(() => ({ data: [] })),
    ])
    setMonthly(m.data)
    setAvail(a.data.by_system)
    setJobs(j.data || [])
  }

  useEffect(() => { load() }, [])

  const monthlyOption = {
    tooltip: { trigger: 'axis' },
    legend: { data: ['新增', '关闭', '平均处理时长(h)', 'SLA达成率(%)'] },
    grid: { left: 50, right: 50, top: 40, bottom: 40 },
    xAxis: { type: 'category', data: monthly.map(m => m.month) },
    yAxis: [{ type: 'value', name: '数量' }, { type: 'value', name: '时长/%', position: 'right' }],
    series: [
      { name: '新增', type: 'bar', data: monthly.map(m => m.new_defects), itemStyle: { color: '#fa541c' } },
      { name: '关闭', type: 'bar', data: monthly.map(m => m.closed_defects), itemStyle: { color: '#52c41a' } },
      { name: '平均处理时长(h)', type: 'line', yAxisIndex: 1, smooth: true, data: monthly.map(m => m.avg_repair_hours), itemStyle: { color: '#1890ff' } },
      { name: 'SLA达成率(%)', type: 'line', yAxisIndex: 1, smooth: true, data: monthly.map(m => m.sla_pass_rate), itemStyle: { color: '#722ed1' } },
    ],
  }

  const availOption = {
    tooltip: { trigger: 'axis' },
    legend: { data: ['可用率(%)', '平均健康度'] },
    grid: { left: 50, right: 50, top: 40, bottom: 40 },
    xAxis: { type: 'category', data: avail.map(a => SYSTEM_LABEL[a.system as EquipmentSystem] || a.system) },
    yAxis: { type: 'value', min: 0, max: 100 },
    series: [
      { name: '可用率(%)', type: 'bar', data: avail.map(a => a.availability_rate), itemStyle: { color: '#13c2c2' } },
      { name: '平均健康度', type: 'line', smooth: true, data: avail.map(a => a.avg_health_score), itemStyle: { color: '#fa8c16' } },
    ],
  }

  const handleExportEquipments = async () => {
    setExporting(true)
    try {
      await downloadCsv(reportApi.exportEquipmentsUrl(), `equipments_${dayjs().format('YYYYMMDD')}.csv`)
      message.success('设备台账导出完成')
    } catch (e: any) {
      message.error(`导出失败：${e.message}`)
    } finally {
      setExporting(false)
    }
  }

  const handleExportDefects = async () => {
    setExporting(true)
    try {
      const start = range?.[0]?.format('YYYY-MM-DD')
      const end = range?.[1]?.format('YYYY-MM-DD')
      await downloadCsv(reportApi.exportDefectsUrl(start, end), `defects_${dayjs().format('YYYYMMDD')}.csv`)
      message.success('缺陷工单导出完成')
    } catch (e: any) {
      message.error(`导出失败：${e.message}`)
    } finally {
      setExporting(false)
    }
  }

  const handleRunJob = async (id: string) => {
    try {
      await schedulerApi.run(id)
      message.success(`已触发 ${id}`)
      load()
    } catch (e: any) {
      message.error(`触发失败：${e.message || e}`)
    }
  }

  const monthlyCols = [
    { title: '月份', dataIndex: 'month', key: 'month' },
    { title: '新增缺陷', dataIndex: 'new_defects', key: 'new' },
    { title: '关闭缺陷', dataIndex: 'closed_defects', key: 'closed' },
    { title: '平均处理时长(h)', dataIndex: 'avg_repair_hours', key: 'avg' },
    {
      title: 'SLA达成率', dataIndex: 'sla_pass_rate', key: 'sla',
      render: (v: number) => <Tag color={v >= 90 ? 'green' : v >= 70 ? 'orange' : 'red'}>{v}%</Tag>,
    },
    { title: '紧急', dataIndex: 'critical', key: 'critical', render: (v: number) => v > 0 ? <Tag color="red">{v}</Tag> : v },
    { title: '重要', dataIndex: 'major', key: 'major', render: (v: number) => v > 0 ? <Tag color="orange">{v}</Tag> : v },
    { title: '一般', dataIndex: 'minor', key: 'minor' },
  ]

  const availCols = [
    {
      title: '系统', dataIndex: 'system', key: 'system',
      render: (v: string) => SYSTEM_LABEL[v as EquipmentSystem] || v,
    },
    { title: '设备总数', dataIndex: 'equipment_count', key: 'total' },
    { title: '运行', dataIndex: 'running', key: 'running' },
    { title: '检修', dataIndex: 'maintenance', key: 'maintenance' },
    {
      title: '可用率', dataIndex: 'availability_rate', key: 'rate',
      render: (v: number) => <Tag color={v >= 95 ? 'green' : v >= 85 ? 'orange' : 'red'}>{v}%</Tag>,
    },
    {
      title: '平均健康度', dataIndex: 'avg_health_score', key: 'health',
      render: (v: number) => <Tag color={v >= 80 ? 'green' : v >= 60 ? 'orange' : 'red'}>{v}</Tag>,
    },
  ]

  const jobCols = [
    { title: 'Job ID', dataIndex: 'id', key: 'id' },
    {
      title: '下次执行', dataIndex: 'next_run', key: 'next',
      render: (v: string) => v ? dayjs(v).format('MM-DD HH:mm:ss') : '-',
    },
    {
      title: '上次执行', dataIndex: 'last_run_at', key: 'last',
      render: (v: string) => v ? dayjs(v).format('MM-DD HH:mm:ss') : '-',
    },
    {
      title: '上次结果', dataIndex: 'last_result', key: 'result',
      render: (v: any) => v ? <Text code style={{ fontSize: 12 }}>{typeof v === 'string' ? v : JSON.stringify(v)}</Text> : '-',
    },
    {
      title: '操作', key: 'op',
      render: (_: any, row: SchedulerJob) => (
        <Button size="small" onClick={() => handleRunJob(row.id)}>立即执行</Button>
      ),
    },
  ]

  const last = monthly[monthly.length - 1]

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card>
        <Row gutter={16}>
          <Col span={6}>
            <Statistic title="本月新增缺陷" value={last?.new_defects ?? 0} />
          </Col>
          <Col span={6}>
            <Statistic title="本月已关闭" value={last?.closed_defects ?? 0} />
          </Col>
          <Col span={6}>
            <Statistic title="本月平均处理时长 (h)" value={last?.avg_repair_hours ?? 0} precision={1} />
          </Col>
          <Col span={6}>
            <Statistic title="本月 SLA 达成率" value={last?.sla_pass_rate ?? 0} suffix="%" precision={1} />
          </Col>
        </Row>
      </Card>

      <Card
        title="近 6 个月缺陷处理趋势"
        extra={<Button icon={<ReloadOutlined />} size="small" onClick={load}>刷新</Button>}
      >
        <ReactECharts option={monthlyOption} style={{ height: 320 }} />
        <Table
          size="small"
          rowKey="month"
          dataSource={monthly}
          columns={monthlyCols}
          pagination={false}
          style={{ marginTop: 12 }}
        />
      </Card>

      <Card title="各系统设备可用率（快照）">
        <ReactECharts option={availOption} style={{ height: 280 }} />
        <Table
          size="small"
          rowKey="system"
          dataSource={avail}
          columns={availCols}
          pagination={false}
          style={{ marginTop: 12 }}
        />
      </Card>

      <Card title="数据导出">
        <Space direction="vertical" style={{ width: '100%' }}>
          <Space>
            <Button
              type="primary" icon={<DownloadOutlined />}
              loading={exporting} onClick={handleExportEquipments}
            >
              导出全部设备台账
            </Button>
          </Space>
          <Space>
            <Text>缺陷工单时间范围：</Text>
            <RangePicker
              value={range as any}
              onChange={(v) => setRange(v as any)}
            />
            <Button
              type="primary" icon={<DownloadOutlined />}
              loading={exporting} onClick={handleExportDefects}
            >
              导出缺陷工单
            </Button>
          </Space>
        </Space>
      </Card>

      <Card title="定时调度状态">
        <Table
          size="small"
          rowKey="id"
          dataSource={jobs}
          columns={jobCols}
          pagination={false}
        />
      </Card>
    </Space>
  )
}
