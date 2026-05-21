/**
 * 工作票打印视图：A4 友好的纸面布局，浏览器原生 print() 即可输出 PDF/打印
 * 路由 /work-tickets/:id/print（在 App.tsx 中注册）
 */
import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Button, Spin, Empty } from 'antd'
import { PrinterOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { workTicketApi } from '../api'
import type { WorkTicket } from '../types'
import { WT_TYPE_LABEL, WT_STATUS_LABEL } from '../types'

export default function WorkTicketPrint() {
  const { id } = useParams<{ id: string }>()
  const [ticket, setTicket] = useState<WorkTicket | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!id) return
    workTicketApi.get(Number(id))
      .then((r) => setTicket(r.data))
      .finally(() => setLoading(false))
  }, [id])

  if (loading) {
    return <div style={{ textAlign: 'center', padding: 80 }}><Spin /></div>
  }
  if (!ticket) {
    return <Empty description="工作票不存在" style={{ marginTop: 80 }} />
  }

  const styles: Record<string, React.CSSProperties> = {
    page: {
      width: '210mm',
      minHeight: '297mm',
      margin: '20px auto',
      padding: '18mm 15mm',
      background: '#fff',
      fontFamily: '"Microsoft YaHei","PingFang SC",sans-serif',
      color: '#000',
      fontSize: 13,
      lineHeight: 1.7,
      boxShadow: '0 0 12px rgba(0,0,0,0.08)',
    },
    title: { textAlign: 'center', fontSize: 22, fontWeight: 700, marginBottom: 4 },
    sub: { textAlign: 'center', fontSize: 14, color: '#666', marginBottom: 16 },
    meta: { display: 'flex', justifyContent: 'space-between', marginBottom: 12, fontSize: 12, color: '#444' },
    table: { width: '100%', borderCollapse: 'collapse', marginBottom: 12 } as React.CSSProperties,
    cellHead: { border: '1px solid #000', padding: 8, background: '#f0f0f0', width: '20%', fontWeight: 600 } as React.CSSProperties,
    cell: { border: '1px solid #000', padding: 8 } as React.CSSProperties,
    sectionH: { fontWeight: 700, margin: '12px 0 6px', borderLeft: '4px solid #000', paddingLeft: 8 },
    sigRow: { display: 'flex', justifyContent: 'space-between', marginTop: 30, gap: 24 },
    sigBox: { flex: 1, borderTop: '1px solid #000', paddingTop: 6, textAlign: 'center', fontSize: 12 } as React.CSSProperties,
    bar: {
      position: 'fixed', top: 12, right: 16, zIndex: 99,
      display: 'flex', gap: 8,
    },
  }

  return (
    <>
      <style>{`
        @media print {
          @page { size: A4; margin: 0; }
          body { margin: 0; background: #fff; }
          .no-print { display: none !important; }
          .print-page { box-shadow: none !important; margin: 0 !important; padding: 18mm 15mm !important; }
        }
        body { background: #ececec; margin: 0; }
      `}</style>
      <div className="no-print" style={styles.bar}>
        <Button type="primary" icon={<PrinterOutlined />} onClick={() => window.print()}>打印 / 另存为 PDF</Button>
        <Button onClick={() => window.close()}>关闭</Button>
      </div>

      <div className="print-page" style={styles.page}>
        <div style={styles.title}>{WT_TYPE_LABEL[ticket.ticket_type]}</div>
        <div style={styles.sub}>发电厂设备点检与缺陷管理系统</div>
        <div style={styles.meta}>
          <span>票号：<b>{ticket.ticket_no}</b></span>
          <span>状态：{WT_STATUS_LABEL[ticket.status]}</span>
          <span>打印时间：{dayjs().format('YYYY-MM-DD HH:mm')}</span>
        </div>

        <table style={styles.table}>
          <tbody>
            <tr>
              <td style={styles.cellHead}>检修设备</td>
              <td style={styles.cell} colSpan={3}>{ticket.equipment_name} ({ticket.equipment_code})</td>
            </tr>
            <tr>
              <td style={styles.cellHead}>关联缺陷</td>
              <td style={styles.cell}>{ticket.defect_no || '—'}</td>
              <td style={styles.cellHead}>工作票类型</td>
              <td style={styles.cell}>{WT_TYPE_LABEL[ticket.ticket_type]}</td>
            </tr>
            <tr>
              <td style={styles.cellHead}>工作内容</td>
              <td style={styles.cell} colSpan={3} >{ticket.work_content}</td>
            </tr>
            <tr>
              <td style={styles.cellHead}>危险点分析</td>
              <td style={styles.cell} colSpan={3}>{ticket.risk_notes || '—'}</td>
            </tr>
            <tr>
              <td style={styles.cellHead}>计划开始</td>
              <td style={styles.cell}>{ticket.planned_start ? dayjs(ticket.planned_start).format('YYYY-MM-DD HH:mm') : '—'}</td>
              <td style={styles.cellHead}>计划结束</td>
              <td style={styles.cell}>{ticket.planned_end ? dayjs(ticket.planned_end).format('YYYY-MM-DD HH:mm') : '—'}</td>
            </tr>
            <tr>
              <td style={styles.cellHead}>实际开始</td>
              <td style={styles.cell}>{ticket.actual_start ? dayjs(ticket.actual_start).format('YYYY-MM-DD HH:mm') : '—'}</td>
              <td style={styles.cellHead}>实际结束</td>
              <td style={styles.cell}>{ticket.actual_end ? dayjs(ticket.actual_end).format('YYYY-MM-DD HH:mm') : '—'}</td>
            </tr>
            <tr>
              <td style={styles.cellHead}>申请人</td>
              <td style={styles.cell}>{ticket.applicant || '—'}</td>
              <td style={styles.cellHead}>工作负责人</td>
              <td style={styles.cell}>{ticket.principal || '—'}</td>
            </tr>
            <tr>
              <td style={styles.cellHead}>签发人</td>
              <td style={styles.cell}>{ticket.issuer || '—'}</td>
              <td style={styles.cellHead}>许可人</td>
              <td style={styles.cell}>{ticket.permitter || '—'}</td>
            </tr>
            <tr>
              <td style={styles.cellHead}>工作班成员</td>
              <td style={styles.cell} colSpan={3}>{(ticket.team_members || []).join('、') || '—'}</td>
            </tr>
          </tbody>
        </table>

        <div style={styles.sectionH}>安全措施</div>
        <table style={styles.table}>
          <thead>
            <tr>
              <td style={{ ...styles.cellHead, width: '8%' }}>序号</td>
              <td style={styles.cellHead}>措施内容</td>
              <td style={{ ...styles.cellHead, width: '10%' }}>已确认</td>
              <td style={{ ...styles.cellHead, width: '15%' }}>确认人</td>
              <td style={{ ...styles.cellHead, width: '18%' }}>确认时间</td>
            </tr>
          </thead>
          <tbody>
            {(ticket.safety_measures || []).length === 0 ? (
              <tr><td style={styles.cell} colSpan={5}>（无安全措施记录）</td></tr>
            ) : (
              ticket.safety_measures!.map((m) => (
                <tr key={m.seq}>
                  <td style={styles.cell}>{m.seq}</td>
                  <td style={styles.cell}>{m.measure}</td>
                  <td style={styles.cell}>{m.checked ? '☑' : '☐'}</td>
                  <td style={styles.cell}>{m.checked_by || ''}</td>
                  <td style={styles.cell}>{m.checked_at ? dayjs(m.checked_at).format('YYYY-MM-DD HH:mm') : ''}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>

        {(ticket.approval_notes || ticket.closing_notes) && (
          <>
            <div style={styles.sectionH}>审批 / 收票备注</div>
            <table style={styles.table}>
              <tbody>
                <tr>
                  <td style={styles.cellHead}>签发备注</td>
                  <td style={styles.cell}>{ticket.approval_notes || '—'}</td>
                </tr>
                <tr>
                  <td style={styles.cellHead}>收票备注</td>
                  <td style={styles.cell}>{ticket.closing_notes || '—'}</td>
                </tr>
              </tbody>
            </table>
          </>
        )}

        <div style={styles.sigRow}>
          <div style={styles.sigBox}>工作负责人签字 ({ticket.principal})</div>
          <div style={styles.sigBox}>签发人签字 ({ticket.issuer || ''})</div>
          <div style={styles.sigBox}>许可人签字 ({ticket.permitter || ''})</div>
        </div>
      </div>
    </>
  )
}
