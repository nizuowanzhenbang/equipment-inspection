import { Layout as AntLayout, Menu, Button, Typography, Space } from 'antd'
import {
  DashboardOutlined, ToolOutlined, NodeIndexOutlined,
  AuditOutlined, BugOutlined, LogoutOutlined, SafetyCertificateOutlined,
  BarChartOutlined, FileTextOutlined, OrderedListOutlined, ThunderboltOutlined,
  AppstoreOutlined, UserOutlined, CloudUploadOutlined, ShoppingCartOutlined,
} from '@ant-design/icons'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { useAuthStore, ROLE_LABEL } from '../stores/auth'
import { useRealtime } from '../hooks/useRealtime'

const { Sider, Header, Content } = AntLayout
const { Title, Text } = Typography

export default function Layout() {
  const navigate = useNavigate()
  const location = useLocation()
  const { username, role, logout, token } = useAuthStore()
  useRealtime(!!token)

  const menuItems = [
    { key: '/dashboard', icon: <DashboardOutlined />, label: '仪表盘' },
    { key: '/equipments', icon: <ToolOutlined />, label: '设备台账' },
    { key: '/routes', icon: <NodeIndexOutlined />, label: '点检路线' },
    { key: '/tasks', icon: <AuditOutlined />, label: '点检任务' },
    { key: '/defects', icon: <BugOutlined />, label: '缺陷工单' },
    { key: '/work-tickets', icon: <FileTextOutlined />, label: '工作票' },
    { key: '/operation-tickets', icon: <OrderedListOutlined />, label: '操作票' },
    { key: '/predictive', icon: <ThunderboltOutlined />, label: '预测维护' },
    { key: '/spare-parts', icon: <AppstoreOutlined />, label: '备品备件' },
    { key: '/purchase-requests', icon: <ShoppingCartOutlined />, label: '采购申请' },
    { key: '/offline', icon: <CloudUploadOutlined />, label: '离线队列' },
    { key: '/reports', icon: <BarChartOutlined />, label: '报表导出' },
    ...(role === 'ADMIN' ? [
      { key: '/users', icon: <UserOutlined />, label: '用户管理' },
      { key: '/audit', icon: <AuditOutlined />, label: '审计日志' },
    ] : []),
  ]

  return (
    <AntLayout style={{ minHeight: '100vh' }}>
      <Sider width={220} theme="light" style={{ borderRight: '1px solid #f0f0f0' }}>
        <div style={{ padding: '20px 16px', borderBottom: '1px solid #f0f0f0' }}>
          <Space>
            <SafetyCertificateOutlined style={{ fontSize: 22, color: '#fa541c' }} />
            <Title level={5} style={{ margin: 0 }}>设备点检</Title>
          </Space>
        </div>
        <Menu
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
          style={{ borderRight: 0 }}
        />
      </Sider>
      <AntLayout>
        <Header style={{
          background: '#fff', padding: '0 24px',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          borderBottom: '1px solid #f0f0f0',
        }}>
          <Text strong style={{ fontSize: 16 }}>发电厂设备点检与缺陷管理系统</Text>
          <Space>
            <Text type="secondary">{username} · {role ? ROLE_LABEL[role] || role : ''}</Text>
            <Button type="text" icon={<LogoutOutlined />} onClick={() => { logout(); navigate('/login') }}>
              退出
            </Button>
          </Space>
        </Header>
        <Content style={{ padding: 20, background: '#f5f5f5' }}>
          <Outlet />
        </Content>
      </AntLayout>
    </AntLayout>
  )
}
