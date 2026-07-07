import { useState } from 'react'
import { Modal, Form, Input, Alert } from 'antd'

interface Props {
  open: boolean
  title: string
  stage: string
  extraForm?: React.ReactNode  // 额外字段（比如签发备注/收尾说明）
  onCancel: () => void
  onConfirm: (password: string, extra: Record<string, any>) => Promise<void> | void
}

/**
 * 两票电子签名 Modal：用户在关键流转节点必须再次输入登录密码作为签名。
 * 后端会校验密码 + HMAC-SHA256 计算 sig_hash 写入 signatures 链。
 */
export default function SignatureModal({ open, title, stage, extraForm, onCancel, onConfirm }: Props) {
  const [form] = Form.useForm()
  const [submitting, setSubmitting] = useState(false)

  const handleOk = async () => {
    const values = await form.validateFields()
    const { signature_password, ...extra } = values
    setSubmitting(true)
    try {
      await onConfirm(signature_password, extra)
      form.resetFields()
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      open={open}
      title={title}
      okText="签名确认"
      cancelText="取消"
      confirmLoading={submitting}
      onOk={handleOk}
      onCancel={() => { form.resetFields(); onCancel() }}
      maskClosable={false}
      destroyOnClose
    >
      <Alert
        type="warning"
        showIcon
        message={`阶段：${stage}`}
        description="请输入登录密码作为电子签名。提交后将生成 HMAC 摘要写入签名链，不可篡改。"
        style={{ marginBottom: 16 }}
      />
      <Form form={form} layout="vertical">
        {extraForm}
        <Form.Item
          name="signature_password"
          label="签名密码"
          rules={[{ required: true, message: '必须再次输入密码' }]}
        >
          <Input.Password autoComplete="current-password" placeholder="登录密码" />
        </Form.Item>
      </Form>
    </Modal>
  )
}
