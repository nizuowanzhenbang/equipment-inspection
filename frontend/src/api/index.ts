import axios from 'axios'
import type {
  ApiResponse, PaginatedResponse,
  Equipment, EquipmentSystem, Criticality, EquipmentStatus,
  InspectionRoute, InspectionPoint, RouteFrequency,
  InspectionTask, TaskStatus, PointStatus,
  Defect, DefectSeverity, DefectSource, DefectStatus,
  DashboardOverview, DefectTrendItem, SystemDistItem, TopFaultyItem, HealthRankItem,
  MonthlyReportItem, AvailabilityItem, SchedulerJob,
  WorkTicket, WorkTicketStatus, WorkTicketType,
  OperationTicket, OperationTicketStatus, OperationTicketType, OperationStep,
  PredictiveRiskItem,
  SparePart, StockMovement, StockMovementType,
  EquipmentProfile,
} from '../types'

const api = axios.create({ baseURL: '/api', timeout: 15000 })

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (res) => res.data,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/login'
    }
    return Promise.reject(err.response?.data || err)
  },
)

export const authApi = {
  login: (username: string, password: string) => {
    const form = new URLSearchParams()
    form.append('username', username)
    form.append('password', password)
    return api.post<unknown, { access_token: string; token_type: string }>('/auth/login', form, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    })
  },
  me: () => api.get<unknown, ApiResponse<{ id: number; username: string; role: string }>>('/auth/me'),
}

export const equipmentApi = {
  list: (params?: {
    page?: number; page_size?: number;
    equipment_system?: EquipmentSystem; criticality?: Criticality;
    status?: EquipmentStatus; keyword?: string
  }) => api.get<unknown, ApiResponse<PaginatedResponse<Equipment>>>('/equipments', { params }),
  create: (data: Partial<Equipment>) => api.post<unknown, ApiResponse<Equipment>>('/equipments', data),
  get: (id: number) => api.get<unknown, ApiResponse<Equipment>>(`/equipments/${id}`),
  getByCode: (code: string) => api.get<unknown, ApiResponse<Equipment>>(`/equipments/by-code/${encodeURIComponent(code)}`),
  profile: (id: number) => api.get<unknown, ApiResponse<EquipmentProfile>>(`/equipments/${id}/profile`),
  qrUrl: (id: number) => `/api/equipments/${id}/qr.svg`,
  update: (id: number, data: Partial<Equipment>) => api.put<unknown, ApiResponse<Equipment>>(`/equipments/${id}`, data),
  toMaintenance: (id: number) => api.post<unknown, ApiResponse<null>>(`/equipments/${id}/maintenance`),
  restore: (id: number) => api.post<unknown, ApiResponse<null>>(`/equipments/${id}/restore`),
}

export const routeApi = {
  list: (params?: { page?: number; page_size?: number; is_active?: boolean }) =>
    api.get<unknown, ApiResponse<PaginatedResponse<InspectionRoute>>>('/routes', { params }),
  create: (data: { name: string; equipment_system?: string; frequency: RouteFrequency; estimated_duration?: number; notes?: string; points: Array<{ equipment_id: number; sequence: number; check_items: any[]; standard?: string }> }) =>
    api.post<unknown, ApiResponse<InspectionRoute>>('/routes', data),
  get: (id: number) => api.get<unknown, ApiResponse<InspectionRoute>>(`/routes/${id}`),
  update: (id: number, data: Partial<InspectionRoute>) => api.put<unknown, ApiResponse<InspectionRoute>>(`/routes/${id}`, data),
  addPoint: (rid: number, data: { equipment_id: number; sequence: number; check_items: any[]; standard?: string }) =>
    api.post<unknown, ApiResponse<InspectionPoint>>(`/routes/${rid}/points`, data),
  deletePoint: (pid: number) => api.delete<unknown, ApiResponse<null>>(`/routes/points/${pid}`),
}

export const taskApi = {
  list: (params?: { page?: number; page_size?: number; status?: TaskStatus; route_id?: number }) =>
    api.get<unknown, ApiResponse<PaginatedResponse<InspectionTask>>>('/tasks', { params }),
  generate: (data: { route_id: number; scheduled_at: string; assigned_to?: string }) =>
    api.post<unknown, ApiResponse<InspectionTask>>('/tasks/generate', data),
  get: (id: number) => api.get<unknown, ApiResponse<InspectionTask & { records?: any[]; pending_points?: any[] }>>(`/tasks/${id}`),
  start: (id: number) => api.post<unknown, ApiResponse<null>>(`/tasks/${id}/start`),
  submitRecord: (id: number, data: { point_id: number; status: PointStatus; readings?: any; finding?: string; photo_url?: string }) =>
    api.post<unknown, ApiResponse<any>>(`/tasks/${id}/records`, data),
  sweepMissed: () => api.post<unknown, ApiResponse<{ missed: number }>>(`/tasks/sweep-missed`),
}

export const defectApi = {
  list: (params?: { page?: number; page_size?: number; status?: DefectStatus; severity?: DefectSeverity; source?: DefectSource; equipment_id?: number }) =>
    api.get<unknown, ApiResponse<PaginatedResponse<Defect>>>('/defects', { params }),
  create: (data: { equipment_id: number; title: string; description?: string; severity?: DefectSeverity; photo_url?: string }) =>
    api.post<unknown, ApiResponse<Defect>>('/defects', data),
  get: (id: number) => api.get<unknown, ApiResponse<Defect>>(`/defects/${id}`),
  assign: (id: number, assigned_to: string, notes?: string) =>
    api.post<unknown, ApiResponse<null>>(`/defects/${id}/assign`, { assigned_to, notes }),
  startRepair: (id: number) => api.post<unknown, ApiResponse<null>>(`/defects/${id}/start-repair`),
  repair: (id: number, repair_notes: string, repair_cost = 0) =>
    api.post<unknown, ApiResponse<null>>(`/defects/${id}/repair`, { repair_notes, repair_cost }),
  verify: (id: number, pass_: boolean, verify_notes?: string) =>
    api.post<unknown, ApiResponse<null>>(`/defects/${id}/verify`, { pass_, verify_notes }),
  cancel: (id: number) => api.post<unknown, ApiResponse<null>>(`/defects/${id}/cancel`),
  sweepOverdue: () => api.post<unknown, ApiResponse<{ overdue: number }>>(`/defects/sweep-overdue`),
  safetySync: (id: number) => api.post<unknown, ApiResponse<Defect>>(`/defects/${id}/safety-sync`),
}

export const reportApi = {
  monthly: (months = 6) =>
    api.get<unknown, ApiResponse<MonthlyReportItem[]>>('/reports/monthly', { params: { months } }),
  availability: (days = 30) =>
    api.get<unknown, ApiResponse<{ window_days: number; by_system: AvailabilityItem[] }>>('/reports/equipment-availability', { params: { days } }),
  exportEquipmentsUrl: () => '/api/reports/equipments/export',
  exportDefectsUrl: (start?: string, end?: string) => {
    const qs = new URLSearchParams()
    if (start) qs.append('start', start)
    if (end) qs.append('end', end)
    const tail = qs.toString()
    return `/api/reports/defects/export${tail ? '?' + tail : ''}`
  },
}

export const schedulerApi = {
  jobs: () => api.get<unknown, ApiResponse<SchedulerJob[]>>('/scheduler/jobs'),
  run: (jobId: string) => api.post<unknown, ApiResponse<any>>(`/scheduler/run/${jobId}`),
}

export const workTicketApi = {
  list: (params?: { page?: number; page_size?: number; status?: WorkTicketStatus; ticket_type?: WorkTicketType; equipment_id?: number; defect_id?: number }) =>
    api.get<unknown, ApiResponse<PaginatedResponse<WorkTicket>>>('/work-tickets', { params }),
  create: (data: any) => api.post<unknown, ApiResponse<WorkTicket>>('/work-tickets', data),
  get: (id: number) => api.get<unknown, ApiResponse<WorkTicket>>(`/work-tickets/${id}`),
  update: (id: number, data: any) => api.put<unknown, ApiResponse<WorkTicket>>(`/work-tickets/${id}`, data),
  submit: (id: number) => api.post<unknown, ApiResponse<null>>(`/work-tickets/${id}/submit`),
  issue: (id: number, approval_notes?: string) =>
    api.post<unknown, ApiResponse<null>>(`/work-tickets/${id}/issue`, { approval_notes }),
  permit: (id: number, permitter?: string, notes?: string) =>
    api.post<unknown, ApiResponse<null>>(`/work-tickets/${id}/permit`, { permitter, notes }),
  complete: (id: number, closing_notes?: string) =>
    api.post<unknown, ApiResponse<null>>(`/work-tickets/${id}/complete`, { closing_notes }),
  close: (id: number) => api.post<unknown, ApiResponse<null>>(`/work-tickets/${id}/close`),
  cancel: (id: number) => api.post<unknown, ApiResponse<null>>(`/work-tickets/${id}/cancel`),
  checkSafety: (id: number, step_seq: number) =>
    api.post<unknown, ApiResponse<null>>(`/work-tickets/${id}/check-safety`, null, { params: { step_seq } }),
}

export interface OperationTemplate {
  id: number
  name: string
  operation_type: OperationTicketType
  description?: string | null
  steps: Array<{ seq: number; action: string; expected?: string | null }>
  use_count: number
  created_by?: string | null
  created_at: string
  updated_at: string
}

export const opTicketApi = {
  list: (params?: { page?: number; page_size?: number; status?: OperationTicketStatus; operation_type?: OperationTicketType; work_ticket_id?: number }) =>
    api.get<unknown, ApiResponse<PaginatedResponse<OperationTicket>>>('/operation-tickets', { params }),
  create: (data: any) => api.post<unknown, ApiResponse<OperationTicket>>('/operation-tickets', data),
  get: (id: number) => api.get<unknown, ApiResponse<OperationTicket>>(`/operation-tickets/${id}`),
  update: (id: number, data: any) => api.put<unknown, ApiResponse<OperationTicket>>(`/operation-tickets/${id}`, data),
  review: (id: number) => api.post<unknown, ApiResponse<null>>(`/operation-tickets/${id}/review`),
  approve: (id: number) => api.post<unknown, ApiResponse<null>>(`/operation-tickets/${id}/approve`),
  start: (id: number) => api.post<unknown, ApiResponse<null>>(`/operation-tickets/${id}/start`),
  executeStep: (id: number, seq: number, result: 'PASS' | 'FAIL', notes?: string) =>
    api.post<unknown, ApiResponse<{ all_done: boolean }>>(`/operation-tickets/${id}/execute-step`, { seq, result, notes }),
  cancel: (id: number) => api.post<unknown, ApiResponse<null>>(`/operation-tickets/${id}/cancel`),
  listTemplates: () => api.get<unknown, ApiResponse<OperationTemplate[]>>('/operation-tickets/templates'),
  createTemplate: (data: { name: string; operation_type: OperationTicketType; description?: string; steps: Array<{ seq: number; action: string; expected?: string }> }) =>
    api.post<unknown, ApiResponse<OperationTemplate>>('/operation-tickets/templates', data),
  saveAsTemplate: (oid: number, name: string, description?: string) =>
    api.post<unknown, ApiResponse<OperationTemplate>>(`/operation-tickets/templates/from-ticket/${oid}`, null, { params: { name, description } }),
  deleteTemplate: (tid: number) =>
    api.delete<unknown, ApiResponse<null>>(`/operation-tickets/templates/${tid}`),
}

export const predictiveApi = {
  ranking: (limit = 20) =>
    api.get<unknown, ApiResponse<PredictiveRiskItem[]>>('/predictive/ranking', { params: { limit } }),
}

export interface AdminUser {
  id: number
  username: string
  full_name?: string | null
  role: 'ADMIN' | 'INSPECTOR' | 'REPAIRMAN' | 'SUPERVISOR' | 'VIEWER'
  is_active: boolean
  created_at: string
}

export interface AuditEntry {
  id: number
  actor?: string | null
  action: string
  target_type?: string | null
  target_id?: number | null
  target_no?: string | null
  summary?: string | null
  extra?: any
  created_at: string
}

export const auditApi = {
  list: (params?: { page?: number; page_size?: number; actor?: string; action?: string; target_type?: string; keyword?: string }) =>
    api.get<unknown, ApiResponse<PaginatedResponse<AuditEntry>>>('/audit', { params }),
}

export const userApi = {
  list: (params?: { page?: number; page_size?: number; role?: AdminUser['role']; keyword?: string }) =>
    api.get<unknown, ApiResponse<PaginatedResponse<AdminUser>>>('/users', { params }),
  create: (data: { username: string; password: string; full_name?: string; role?: AdminUser['role']; is_active?: boolean }) =>
    api.post<unknown, ApiResponse<AdminUser>>('/users', data),
  update: (id: number, data: { full_name?: string; role?: AdminUser['role']; is_active?: boolean }) =>
    api.put<unknown, ApiResponse<AdminUser>>(`/users/${id}`, data),
  resetPassword: (id: number, new_password: string) =>
    api.post<unknown, ApiResponse<null>>(`/users/${id}/reset-password`, { new_password }),
  toggleActive: (id: number) =>
    api.post<unknown, ApiResponse<{ is_active: boolean }>>(`/users/${id}/toggle-active`),
}

export const sparePartApi = {
  list: (params?: { page?: number; page_size?: number; keyword?: string; category?: string; low_only?: boolean }) =>
    api.get<unknown, ApiResponse<PaginatedResponse<SparePart>>>('/spare-parts', { params }),
  create: (data: Partial<SparePart>) => api.post<unknown, ApiResponse<SparePart>>('/spare-parts', data),
  get: (id: number) => api.get<unknown, ApiResponse<SparePart>>(`/spare-parts/${id}`),
  update: (id: number, data: Partial<SparePart>) => api.put<unknown, ApiResponse<SparePart>>(`/spare-parts/${id}`, data),
  categories: () => api.get<unknown, ApiResponse<Array<{ category: string; count: number }>>>(`/spare-parts/categories`),
  createMovement: (id: number, data: { movement_type: StockMovementType; qty: number; defect_id?: number; work_ticket_id?: number; notes?: string }) =>
    api.post<unknown, ApiResponse<{ movement: StockMovement; stock_qty: number; low_stock: boolean }>>(`/spare-parts/${id}/movements`, data),
  listMovements: (id: number, params?: { page?: number; page_size?: number }) =>
    api.get<unknown, ApiResponse<PaginatedResponse<StockMovement>>>(`/spare-parts/${id}/movements`, { params }),
  overview: () =>
    api.get<unknown, ApiResponse<{ total_items: number; low_stock_items: number; total_value: number }>>(`/spare-parts/stats/overview`),
}

export const uploadApi = {
  endpoint: '/api/uploads',
  // 给 antd Upload 组件用的 customRequest
  customRequest: async ({ file, onSuccess, onError }: any) => {
    try {
      const fd = new FormData()
      fd.append('file', file)
      const token = localStorage.getItem('token')
      const resp = await fetch('/api/uploads', {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: fd,
      })
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}))
        throw new Error(err.detail || err.message || `HTTP ${resp.status}`)
      }
      const json = await resp.json()
      onSuccess(json, file)
    } catch (e: any) {
      onError(e)
    }
  },
}

// 触发文件下载（带 Bearer 头）
export async function downloadCsv(url: string, filename?: string) {
  const token = localStorage.getItem('token')
  const resp = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
  if (!resp.ok) throw new Error(`下载失败 ${resp.status}`)
  const blob = await resp.blob()
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  if (filename) link.download = filename
  link.click()
  URL.revokeObjectURL(link.href)
}

export const dashboardApi = {
  overview: () => api.get<unknown, ApiResponse<DashboardOverview>>('/dashboard/overview'),
  defectTrend: (days = 30) =>
    api.get<unknown, ApiResponse<DefectTrendItem[]>>('/dashboard/defect-trend', { params: { days } }),
  systemDistribution: () =>
    api.get<unknown, ApiResponse<SystemDistItem[]>>('/dashboard/system-distribution'),
  topFaulty: (limit = 5) =>
    api.get<unknown, ApiResponse<TopFaultyItem[]>>('/dashboard/top-faulty-equipments', { params: { limit } }),
  healthRanking: (limit = 10) =>
    api.get<unknown, ApiResponse<HealthRankItem[]>>('/dashboard/equipment-health-ranking', { params: { limit } }),
}

export default api
