import { useEffect, useState } from 'react'
import {
  Card, Table, Tag, Button, Space, Input, Form, Modal, message, Switch, Select,
  Typography, Popconfirm,
} from 'antd'
import { UserOutlined, PlusOutlined, ReloadOutlined, KeyOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { userApi, AdminUser } from '../api'
import { useAuthStore, ROLE_LABEL } from '../stores/auth'

const { Text } = Typography

export default function UserManagement() {
  const role = useAuthStore((s) => s.role)
  const myUsername = useAuthStore((s) => s.username)
  const isAdmin = role === 'ADMIN'

  const [rows, setRows] = useState<AdminUser[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [filters, setFilters] = useState<{ role?: AdminUser['role']; keyword?: string }>({})

  const [createOpen, setCreateOpen] = useState(false)
  const [createForm] = Form.useForm()
  const [editOpen, setEditOpen] = useState(false)
  const [editForm] = Form.useForm()
  const [pwOpen, setPwOpen] = useState(false)
  const [pwForm] = Form.useForm()
  const [current, setCurrent] = useState<AdminUser | null>(null)

  const load = () => {
    setLoading(true)
    userApi.list({ page, page_size: 20, ...filters })
      .then((r) => { setRows(r.data.items); setTotal(r.data.total) })
      .finally(() => setLoading(false))
  }
  useEffect(load, [page, filters])

  const onCreate = async () => {
    const v = await createForm.validateFields()
    try {
      await userApi.create(v)
      message.success('用户已创建')
      setCreateOpen(false); createForm.resetFields(); load()
    } catch (e: any) { message.error(e?.detail || '失败') }
  }

  const onEdit = async () => {
    const v = await editForm.validateFields()
    try {
      await userApi.update(current!.id, v)
      message.success('已更新')
      setEditOpen(false); editForm.resetFields(); load()
    } catch (e: any) { message.error(e?.detail || '失败') }
  }

  const onResetPw = async () => {
    const v = await pwForm.validateFields()
    try {
      await userApi.resetPassword(current!.id, v.new_password)
      message.success('密码已重置')
      setPwOpen(false); pwForm.resetFields()
    } catch (e: any) { message.error(e?.detail || '失败') }
  }

  const onToggle = async (u: AdminUser) => {
    try {
      const r = await userApi.toggleActive(u.id)
      message.success(r.data.is_active ? '已启用' : '已禁用')
      load()
    } catch (e: any) { message.error(e?.detail || '失败') }
  }

  if (!isAdmin) {
    return (
      <Card>
        <Text type="warning">仅管理员可访问用户管理。</Text>
      </Card>
    )
  }

  return (
    <Card
      title={<Space><UserOutlined />用户管理</Space>}
      extra={
        <Space>
          <Select<AdminUser['role'] | undefined>
            placeholder="角色" allowClear style={{ width: 140 }} value={filters.role}
            onChange={(v) => { setPage(1); setFilters({ ...filters, role: v }) }}
            options={Object.entries(ROLE_LABEL).map(([k, v]) => ({ label: v, value: k }))}
          />
          <Input.Search placeholder="用户名/姓名" allowClear style={{ width: 200 }}
            onSearch={(v) => { setPage(1); setFilters({ ...filters, keyword: v || undefined }) }} />
          <Button icon={<ReloadOutlined />} onClick={load} />
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>新增用户</Button>
        </Space>
      }
    >
      <Table
        rowKey="id"
        loading={loading}
        dataSource={rows}
        pagination={{ current: page, pageSize: 20, total, onChange: setPage }}
        columns={[
          { title: 'ID', dataIndex: 'id', width: 60 },
          { title: '用户名', dataIndex: 'username', width: 140,
            render: (v) => <Text strong>{v}</Text> },
          { title: '姓名', dataIndex: 'full_name', render: (v) => v || '-' },
          { title: '角色', dataIndex: 'role', width: 130,
            render: (v) => {
              const colorMap: Record<string, string> = {
                ADMIN: 'red', SUPERVISOR: 'orange', REPAIRMAN: 'blue',
                INSPECTOR: 'cyan', VIEWER: 'default',
              }
              return <Tag color={colorMap[v] || 'default'}>{ROLE_LABEL[v] || v}</Tag>
            } },
          { title: '状态', dataIndex: 'is_active', width: 100,
            render: (v) => v ? <Tag color="green">启用</Tag> : <Tag>禁用</Tag> },
          { title: '创建时间', dataIndex: 'created_at', width: 160,
            render: (v) => dayjs(v).format('YYYY-MM-DD HH:mm') },
          {
            title: '操作', width: 280, fixed: 'right' as const,
            render: (_: any, r: AdminUser) => (
              <Space size="small">
                <Button size="small" onClick={() => {
                  setCurrent(r); editForm.setFieldsValue(r); setEditOpen(true)
                }}>编辑</Button>
                <Button size="small" icon={<KeyOutlined />}
                  onClick={() => { setCurrent(r); setPwOpen(true) }}>重置密码</Button>
                <Popconfirm
                  title={`确定${r.is_active ? '禁用' : '启用'} ${r.username} 吗？`}
                  onConfirm={() => onToggle(r)}
                  disabled={r.username === myUsername || r.username === 'admin'}
                >
                  <Button size="small" danger={r.is_active}
                    disabled={r.username === myUsername || r.username === 'admin'}>
                    {r.is_active ? '禁用' : '启用'}
                  </Button>
                </Popconfirm>
              </Space>
            ),
          },
        ]}
        scroll={{ x: 1100 }}
      />

      <Modal title="新增用户" open={createOpen} onOk={onCreate} onCancel={() => setCreateOpen(false)} width={520}>
        <Form form={createForm} layout="vertical" initialValues={{ role: 'INSPECTOR', is_active: true }}>
          <Form.Item name="username" label="用户名" rules={[{ required: true, min: 3, max: 50 }]}><Input /></Form.Item>
          <Form.Item name="password" label="初始密码" rules={[{ required: true, min: 6 }]}>
            <Input.Password />
          </Form.Item>
          <Form.Item name="full_name" label="姓名"><Input /></Form.Item>
          <Form.Item name="role" label="角色" rules={[{ required: true }]}>
            <Select options={Object.entries(ROLE_LABEL).map(([k, v]) => ({ label: v, value: k }))} />
          </Form.Item>
          <Form.Item name="is_active" label="启用" valuePropName="checked"><Switch /></Form.Item>
        </Form>
      </Modal>

      <Modal title={current ? `编辑用户 · ${current.username}` : '编辑'}
        open={editOpen} onOk={onEdit} onCancel={() => setEditOpen(false)} width={520}>
        <Form form={editForm} layout="vertical">
          <Form.Item name="full_name" label="姓名"><Input /></Form.Item>
          <Form.Item name="role" label="角色">
            <Select options={Object.entries(ROLE_LABEL).map(([k, v]) => ({ label: v, value: k }))} />
          </Form.Item>
          <Form.Item name="is_active" label="启用" valuePropName="checked"><Switch /></Form.Item>
        </Form>
      </Modal>

      <Modal title={current ? `重置 ${current.username} 的密码` : '重置密码'}
        open={pwOpen} onOk={onResetPw} onCancel={() => setPwOpen(false)} width={480}>
        <Form form={pwForm} layout="vertical">
          <Form.Item name="new_password" label="新密码" rules={[{ required: true, min: 6 }]}>
            <Input.Password />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}
