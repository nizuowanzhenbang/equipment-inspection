/**
 * 移动端扫码 + 快速上报缺陷页
 * - 用浏览器原生 BarcodeDetector（Chrome/Edge 移动端支持）扫 QR
 * - 不支持时给手动输入 code 的入口；扫到 `EQ::CODE` 或纯 CODE -> 拉设备信息 -> 选缺陷等级 -> 上传照片 -> 提交
 */
import { useEffect, useRef, useState } from 'react'
import {
  Card, Button, Space, Input, Select, message, Typography, Tag, Form, Upload, Spin, Divider,
} from 'antd'
import { ScanOutlined, UploadOutlined, ReloadOutlined } from '@ant-design/icons'
import { equipmentApi, defectApi, uploadApi, authApi } from '../api'
import type { Equipment } from '../types'
import { SEVERITY_LABEL, SYSTEM_LABEL, EquipmentSystem } from '../types'

const { Title, Text, Paragraph } = Typography

declare global {
  interface Window {
    BarcodeDetector?: any
  }
}

interface BarcodeDetectorLike {
  detect: (image: ImageBitmapSource) => Promise<Array<{ rawValue: string }>>
}

export default function MobileScan() {
  const [authed, setAuthed] = useState(!!localStorage.getItem('token'))
  const [loginForm] = Form.useForm()
  const [loggingIn, setLoggingIn] = useState(false)

  const [scanning, setScanning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [supported, setSupported] = useState<boolean | null>(null)
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const detectorRef = useRef<BarcodeDetectorLike | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const rafRef = useRef<number | null>(null)

  const [manualCode, setManualCode] = useState('')
  const [equipment, setEquipment] = useState<Equipment | null>(null)
  const [loading, setLoading] = useState(false)

  const [defectForm] = Form.useForm()
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    setSupported(typeof window.BarcodeDetector === 'function')
    return () => stopScan()
  }, [])

  const doLogin = async () => {
    const v = await loginForm.validateFields()
    setLoggingIn(true)
    try {
      const res = await authApi.login(v.username, v.password)
      localStorage.setItem('token', res.access_token)
      // 也拉一次 me 以保存角色（可选）
      try {
        const me: any = await authApi.me()
        if (me?.data) {
          localStorage.setItem('username', me.data.username)
          localStorage.setItem('role', me.data.role)
        }
      } catch {}
      setAuthed(true)
      message.success('登录成功')
    } catch (e: any) {
      message.error('登录失败')
    } finally {
      setLoggingIn(false)
    }
  }

  const startScan = async () => {
    setError(null)
    if (!window.BarcodeDetector) {
      setError('当前浏览器不支持原生 QR 扫描，请使用手动输入')
      return
    }
    try {
      detectorRef.current = new window.BarcodeDetector({ formats: ['qr_code'] })
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: 'environment' } },
        audio: false,
      })
      streamRef.current = stream
      if (videoRef.current) {
        videoRef.current.srcObject = stream
        await videoRef.current.play()
      }
      setScanning(true)
      tick()
    } catch (e: any) {
      setError(`无法访问摄像头：${e?.message || e}`)
    }
  }

  const stopScan = () => {
    setScanning(false)
    if (rafRef.current) cancelAnimationFrame(rafRef.current)
    rafRef.current = null
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop())
      streamRef.current = null
    }
    if (videoRef.current) videoRef.current.srcObject = null
  }

  const tick = async () => {
    if (!detectorRef.current || !videoRef.current) return
    try {
      const codes = await detectorRef.current.detect(videoRef.current)
      if (codes && codes.length) {
        const raw = codes[0].rawValue
        stopScan()
        handleCode(raw)
        return
      }
    } catch {}
    rafRef.current = requestAnimationFrame(tick)
  }

  const handleCode = async (raw: string) => {
    setLoading(true)
    try {
      const r = await equipmentApi.getByCode(raw)
      setEquipment(r.data)
      message.success(`已识别：${r.data.code}`)
    } catch (e: any) {
      message.error(e?.detail || `未识别 ${raw}`)
    } finally {
      setLoading(false)
    }
  }

  const submitDefect = async () => {
    if (!equipment) return
    const v = await defectForm.validateFields()
    setSubmitting(true)
    try {
      await defectApi.create({
        equipment_id: equipment.id,
        title: v.title,
        description: v.description,
        severity: v.severity,
        photo_url: v.photo_url,
      })
      message.success('缺陷已上报！')
      defectForm.resetFields()
      setEquipment(null)
    } catch (e: any) {
      message.error(e?.detail || '上报失败')
    } finally {
      setSubmitting(false)
    }
  }

  // ---- UI ----
  const containerStyle: React.CSSProperties = {
    minHeight: '100vh', background: '#f5f5f5', padding: 12,
    fontFamily: '-apple-system,BlinkMacSystemFont,"Helvetica Neue",Roboto,"Microsoft YaHei",sans-serif',
  }

  if (!authed) {
    return (
      <div style={containerStyle}>
        <Card>
          <Title level={4} style={{ marginTop: 0 }}>📱 移动端登录</Title>
          <Form form={loginForm} layout="vertical">
            <Form.Item name="username" label="用户名" rules={[{ required: true }]}>
              <Input placeholder="inspector" autoComplete="username" />
            </Form.Item>
            <Form.Item name="password" label="密码" rules={[{ required: true }]}>
              <Input.Password placeholder="inspector123" autoComplete="current-password" />
            </Form.Item>
            <Button type="primary" block loading={loggingIn} onClick={doLogin} size="large">登录</Button>
          </Form>
          <Paragraph type="secondary" style={{ marginTop: 12, fontSize: 12 }}>
            提示：点检员请用 inspector / inspector123 登录。建议加到主屏幕（Safari -&gt; 分享 -&gt; 添加到主屏幕；Chrome -&gt; 三点菜单 -&gt; 安装应用）。
          </Paragraph>
        </Card>
      </div>
    )
  }

  return (
    <div style={containerStyle}>
      <Card>
        <Space direction="vertical" size={8} style={{ width: '100%' }}>
          <Title level={4} style={{ margin: 0 }}>📷 扫码点检</Title>
          <Text type="secondary">扫设备 QR 码（EQ::XXX 格式），或手动输入设备编号</Text>
        </Space>

        {!scanning && !equipment && (
          <Space direction="vertical" size={12} style={{ width: '100%', marginTop: 12 }}>
            <Button type="primary" icon={<ScanOutlined />} size="large" block onClick={startScan}>
              开始扫码
            </Button>
            {supported === false && (
              <Text type="warning" style={{ fontSize: 12 }}>
                ⚠️ 当前浏览器不支持原生 QR 扫描，请使用手动输入。建议使用 Chrome / Edge 安卓版。
              </Text>
            )}
            <Divider style={{ margin: '8px 0' }}>或</Divider>
            <Space.Compact style={{ width: '100%' }}>
              <Input
                placeholder="输入设备编号 EQ-BL-0001"
                value={manualCode}
                onChange={(e) => setManualCode(e.target.value)}
                size="large"
              />
              <Button type="primary" size="large" onClick={() => manualCode && handleCode(manualCode)}>查询</Button>
            </Space.Compact>
          </Space>
        )}

        {scanning && (
          <Space direction="vertical" size={12} style={{ width: '100%', marginTop: 12 }}>
            <video
              ref={videoRef}
              playsInline
              style={{ width: '100%', borderRadius: 8, background: '#000', aspectRatio: '4 / 3' }}
            />
            <Text type="secondary" style={{ textAlign: 'center', display: 'block' }}>把 QR 对准摄像头中央</Text>
            <Button block onClick={stopScan}>取消</Button>
          </Space>
        )}

        {error && <Text type="danger" style={{ display: 'block', marginTop: 8 }}>{error}</Text>}

        {loading && <Spin style={{ display: 'block', marginTop: 16, textAlign: 'center' }} />}

        {equipment && (
          <Space direction="vertical" size={12} style={{ width: '100%', marginTop: 16 }}>
            <Card type="inner" title={equipment.name}>
              <Space direction="vertical" size={6}>
                <Space wrap>
                  <Tag color="blue">{equipment.code}</Tag>
                  <Tag color={equipment.criticality === 'A' ? 'red' : equipment.criticality === 'B' ? 'orange' : 'default'}>
                    {equipment.criticality} 级
                  </Tag>
                  <Tag>{SYSTEM_LABEL[equipment.equipment_system as EquipmentSystem] || equipment.equipment_system}</Tag>
                  <Tag color={equipment.status === 'RUNNING' ? 'green' : 'orange'}>{equipment.status}</Tag>
                </Space>
                <Text type="secondary">位置：{equipment.location || '-'}</Text>
                <Text type="secondary">健康度：{equipment.health_score}/100</Text>
              </Space>
            </Card>

            <Card type="inner" title="📝 快速上报缺陷">
              <Form form={defectForm} layout="vertical" initialValues={{ severity: 'MINOR' }}>
                <Form.Item name="title" label="问题简述" rules={[{ required: true }]}>
                  <Input placeholder="例如：轴承温度过高" />
                </Form.Item>
                <Form.Item name="description" label="详细描述">
                  <Input.TextArea rows={2} />
                </Form.Item>
                <Form.Item name="severity" label="严重程度" rules={[{ required: true }]}>
                  <Select size="large" options={Object.entries(SEVERITY_LABEL).map(([k, v]) => ({
                    label: `${v}${k === 'CRITICAL' ? '（1 小时 SLA）' : k === 'MAJOR' ? '（4 小时 SLA）' : '（72 小时 SLA）'}`,
                    value: k,
                  }))} />
                </Form.Item>
                <Form.Item name="photo_url" label="现场照片">
                  <Upload
                    customRequest={uploadApi.customRequest}
                    maxCount={1}
                    accept="image/*"
                    listType="picture"
                    onChange={(info) => {
                      if (info.file.status === 'done') {
                        const url = (info.file.response as any)?.data?.url
                        if (url) {
                          defectForm.setFieldValue('photo_url', url)
                          message.success('照片已上传')
                        }
                      } else if (info.file.status === 'error') {
                        message.error('上传失败')
                      }
                    }}
                  >
                    <Button icon={<UploadOutlined />} size="large" block>拍照 / 选图</Button>
                  </Upload>
                </Form.Item>
                <Space style={{ width: '100%' }}>
                  <Button type="primary" size="large" block loading={submitting} onClick={submitDefect}>提交</Button>
                  <Button size="large" onClick={() => setEquipment(null)} icon={<ReloadOutlined />}>重扫</Button>
                </Space>
              </Form>
            </Card>
          </Space>
        )}
      </Card>

      <Paragraph type="secondary" style={{ marginTop: 12, textAlign: 'center', fontSize: 12 }}>
        当前用户：{localStorage.getItem('username')} · <a onClick={() => { localStorage.clear(); setAuthed(false) }}>退出</a>
      </Paragraph>
    </div>
  )
}
