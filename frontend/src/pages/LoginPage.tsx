import { useState } from 'react'
import { Card, Form, Input, Button, Typography, message } from 'antd'
import { UserOutlined, LockOutlined, SafetyCertificateOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { authApi } from '../api'
import { useAuthStore } from '../stores/auth'

const { Title, Text } = Typography

export default function LoginPage() {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)
  const setAuth = useAuthStore((s) => s.setAuth)

  const onFinish = async (values: { username: string; password: string }) => {
    setLoading(true)
    try {
      const res = await authApi.login(values.username, values.password)
      const me = await fetch('/api/auth/me', {
        headers: { Authorization: `Bearer ${res.access_token}` },
      }).then((r) => r.json())
      setAuth(res.access_token, me.data.username, me.data.role)
      message.success('登录成功')
      navigate('/dashboard')
    } catch (e: unknown) {
      message.error((e as { detail?: string })?.detail || '登录失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      style={{
        minHeight: '100vh', display: 'flex',
        justifyContent: 'center', alignItems: 'center',
        background: 'linear-gradient(135deg, #fa541c 0%, #871f00 100%)',
      }}
    >
      <Card style={{ width: 420, padding: 8 }}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <SafetyCertificateOutlined style={{ fontSize: 48, color: '#fa541c' }} />
          <Title level={3} style={{ marginTop: 12, marginBottom: 4 }}>
            设备点检与缺陷管理
          </Title>
          <Text type="secondary">设备 · 路线 · 点检 · 缺陷 · 检修闭环</Text>
        </div>
        <Form onFinish={onFinish} layout="vertical">
          <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input prefix={<UserOutlined />} placeholder="用户名" size="large" />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password prefix={<LockOutlined />} placeholder="密码" size="large" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} block size="large">
              登录
            </Button>
          </Form.Item>
          <Text type="secondary" style={{ fontSize: 12, display: 'block', lineHeight: 1.8 }}>
            请使用管理员分配的账户登录。演示环境账户见项目运行说明。
          </Text>
        </Form>
      </Card>
    </div>
  )
}
