/**
 * 设备 QR 码批量打印页：选择系统/等级筛选 → 8 列 × 多行卡片 → 浏览器打印
 * 路由 /equipment-qr-print（不进 Layout）
 */
import { useEffect, useState } from 'react'
import { Button, Space, Select, Checkbox, Typography, Spin, message } from 'antd'
import { PrinterOutlined, ReloadOutlined } from '@ant-design/icons'
import { equipmentApi } from '../api'
import type { Equipment, EquipmentSystem, Criticality } from '../types'
import { SYSTEM_LABEL, CRITICALITY_LABEL } from '../types'

const { Text } = Typography

interface QrItem {
  equipment: Equipment
  svgText: string | null
}

function Card({ item }: { item: QrItem }) {
  return (
    <div style={{
      width: '23%',
      margin: '1%',
      padding: '8px 6px',
      border: '1px dashed #aaa',
      borderRadius: 6,
      textAlign: 'center',
      pageBreakInside: 'avoid',
      boxSizing: 'border-box',
    }}>
      <div style={{ width: 130, height: 130, margin: '0 auto', overflow: 'hidden' }}
        dangerouslySetInnerHTML={{ __html: item.svgText || '' }}
      />
      <div style={{ fontSize: 13, fontWeight: 700, marginTop: 6 }}>{item.equipment.code}</div>
      <div style={{ fontSize: 12, color: '#444', marginTop: 2 }}>{item.equipment.name}</div>
      <div style={{ fontSize: 11, color: '#888', marginTop: 2 }}>{item.equipment.location || ''}</div>
    </div>
  )
}

export default function QRPrint() {
  const [equipments, setEquipments] = useState<Equipment[]>([])
  const [systemFilter, setSystemFilter] = useState<EquipmentSystem | undefined>()
  const [critFilter, setCritFilter] = useState<Criticality | undefined>()
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [items, setItems] = useState<QrItem[]>([])
  const [loading, setLoading] = useState(false)

  const loadList = () => {
    setLoading(true)
    equipmentApi.list({ page_size: 200, equipment_system: systemFilter, criticality: critFilter })
      .then((r) => setEquipments(r.data.items))
      .finally(() => setLoading(false))
  }
  useEffect(loadList, [systemFilter, critFilter])

  const fetchAllQr = async () => {
    if (selected.size === 0) {
      message.warning('请先勾选要打印的设备')
      return
    }
    setLoading(true)
    const targets = equipments.filter(e => selected.has(e.id))
    const token = localStorage.getItem('token')
    const out: QrItem[] = []
    for (const eq of targets) {
      try {
        const resp = await fetch(equipmentApi.qrUrl(eq.id), {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        })
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
        const svg = await resp.text()
        out.push({ equipment: eq, svgText: svg })
      } catch (e: any) {
        out.push({ equipment: eq, svgText: `<div style='color:red;font-size:10px'>QR 失败 ${e.message}</div>` })
      }
    }
    setItems(out)
    setLoading(false)
  }

  const selectAll = () => setSelected(new Set(equipments.map(e => e.id)))
  const selectNone = () => setSelected(new Set())
  const toggle = (id: number) => {
    const s = new Set(selected)
    if (s.has(id)) s.delete(id); else s.add(id)
    setSelected(s)
  }

  return (
    <div style={{ padding: 16, background: '#ececec', minHeight: '100vh' }}>
      <style>{`
        @media print {
          @page { size: A4; margin: 8mm; }
          .no-print { display: none !important; }
          .print-area { background: #fff !important; padding: 0 !important; }
        }
      `}</style>

      <div className="no-print" style={{ marginBottom: 12 }}>
        <Space wrap>
          <Select<EquipmentSystem | undefined>
            placeholder="系统" allowClear style={{ width: 130 }}
            value={systemFilter} onChange={setSystemFilter}
            options={Object.entries(SYSTEM_LABEL).map(([k, v]) => ({ label: v, value: k }))}
          />
          <Select<Criticality | undefined>
            placeholder="等级" allowClear style={{ width: 130 }}
            value={critFilter} onChange={setCritFilter}
            options={Object.entries(CRITICALITY_LABEL).map(([k, v]) => ({ label: v, value: k }))}
          />
          <Button icon={<ReloadOutlined />} onClick={loadList}>刷新设备列表</Button>
          <Button onClick={selectAll}>全选 ({equipments.length})</Button>
          <Button onClick={selectNone}>清空</Button>
          <Button type="primary" onClick={fetchAllQr} loading={loading}>
            预览 ({selected.size})
          </Button>
          <Button icon={<PrinterOutlined />} disabled={items.length === 0}
            onClick={() => window.print()}>打印 / PDF</Button>
        </Space>
        <div style={{ marginTop: 10, padding: 10, background: '#fff', borderRadius: 6, maxHeight: 220, overflowY: 'auto' }}>
          {equipments.map(e => (
            <Checkbox
              key={e.id}
              checked={selected.has(e.id)}
              onChange={() => toggle(e.id)}
              style={{ width: 250, marginBottom: 4 }}
            >
              <Text style={{ fontSize: 12 }}>
                {e.code} · {e.name}
              </Text>
            </Checkbox>
          ))}
        </div>
      </div>

      <div className="print-area" style={{ background: '#fff', padding: 12 }}>
        {loading ? <Spin style={{ width: '100%', textAlign: 'center', padding: 60 }} /> : (
          items.length === 0 ? (
            <Text type="secondary" style={{ display: 'block', textAlign: 'center', padding: 60 }}>
              ↑ 勾选设备后点"预览"，QR 卡片会在此显示
            </Text>
          ) : (
            <div style={{ display: 'flex', flexWrap: 'wrap' }}>
              {items.map(i => <Card key={i.equipment.id} item={i} />)}
            </div>
          )
        )}
      </div>
    </div>
  )
}
