// 公共类型
export interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export type EquipmentSystem =
  | 'BOILER' | 'TURBINE' | 'GENERATOR' | 'AUXILIARY'
  | 'ELECTRICAL' | 'CHEMICAL' | 'ASH' | 'DESULFUR'

export type Criticality = 'A' | 'B' | 'C'
export type EquipmentStatus = 'RUNNING' | 'STANDBY' | 'MAINTENANCE' | 'DECOMMISSIONED'

export interface Equipment {
  id: number
  code: string
  name: string
  equipment_system: EquipmentSystem
  criticality: Criticality
  location?: string
  model?: string
  manufacturer?: string
  install_date?: string
  status: EquipmentStatus
  qr_code?: string
  health_score: number
  notes?: string
  created_at: string
  updated_at: string
}

export type RouteFrequency = 'SHIFT' | 'DAILY' | 'WEEKLY' | 'MONTHLY'

export interface InspectionPoint {
  id: number
  point_no: string
  route_id: number
  equipment_id: number
  equipment_name?: string
  equipment_code?: string
  sequence: number
  check_items: Array<{ name: string; type: string; unit?: string; min?: number; max?: number; options?: string[] }>
  standard?: string
  notes?: string
  created_at: string
}

export interface InspectionRoute {
  id: number
  route_no: string
  name: string
  equipment_system?: string
  frequency: RouteFrequency
  estimated_duration: number
  is_active: boolean
  notes?: string
  point_count: number
  points?: InspectionPoint[]
  created_at: string
}

export type TaskStatus = 'PENDING' | 'IN_PROGRESS' | 'COMPLETED' | 'MISSED' | 'CANCELLED'
export type PointStatus = 'NORMAL' | 'ABNORMAL' | 'SEVERE'

export interface InspectionTask {
  id: number
  task_no: string
  route_id: number
  route_name?: string
  scheduled_at: string
  started_at?: string
  completed_at?: string
  assigned_to?: string
  executed_by?: string
  status: TaskStatus
  abnormal_count: number
  notes?: string
  created_at: string
  record_count: number
  total_points: number
}

export type DefectSource = 'INSPECTION' | 'MANUAL' | 'ALARM'
export type DefectSeverity = 'MINOR' | 'MAJOR' | 'CRITICAL'
export type DefectStatus = 'NEW' | 'ASSIGNED' | 'IN_REPAIR' | 'REPAIRED' | 'VERIFIED' | 'CLOSED' | 'OVERDUE' | 'CANCELLED'

export interface Defect {
  id: number
  defect_no: string
  equipment_id: number
  equipment_name?: string
  equipment_code?: string
  source: DefectSource
  severity: DefectSeverity
  status: DefectStatus
  title: string
  description?: string
  photo_url?: string
  reported_by?: string
  reported_at: string
  assigned_to?: string
  assigned_at?: string
  repair_started_at?: string
  repair_completed_at?: string
  repair_notes?: string
  repair_cost: number
  verified_by?: string
  verified_at?: string
  verify_notes?: string
  sla_deadline?: string
  closed_at?: string
  safety_sync_status?: 'PENDING' | 'SYNCED' | 'FAILED' | 'SKIPPED' | null
  safety_hazard_no?: string | null
  safety_sync_at?: string | null
  safety_sync_attempts?: number
  created_at: string
  updated_at: string
}

export interface MonthlyReportItem {
  month: string
  new_defects: number
  closed_defects: number
  avg_repair_hours: number
  sla_pass_rate: number
  minor: number
  major: number
  critical: number
}

export interface AvailabilityItem {
  system: string
  equipment_count: number
  running: number
  maintenance: number
  availability_rate: number
  avg_health_score: number
}

export interface SchedulerJob {
  id: string
  next_run: string | null
  trigger: string
  last_run_at: string | null
  last_result: any
}

// ---- v2.2 两票 ----
export type WorkTicketType = 'FIRST' | 'SECOND' | 'EMERGENCY'
export type WorkTicketStatus =
  | 'DRAFT' | 'SUBMITTED' | 'ISSUED' | 'IN_WORK' | 'COMPLETED' | 'CLOSED' | 'CANCELLED'

export interface SafetyMeasure {
  seq: number
  measure: string
  checked?: boolean
  checked_by?: string
  checked_at?: string
}

export interface WorkTicket {
  id: number
  ticket_no: string
  ticket_type: WorkTicketType
  defect_id?: number | null
  defect_no?: string | null
  equipment_id: number
  equipment_name?: string
  equipment_code?: string
  work_content: string
  safety_measures?: SafetyMeasure[]
  risk_notes?: string | null
  planned_start?: string | null
  planned_end?: string | null
  actual_start?: string | null
  actual_end?: string | null
  applicant?: string | null
  principal?: string | null
  issuer?: string | null
  permitter?: string | null
  team_members?: string[] | null
  status: WorkTicketStatus
  submitted_at?: string | null
  issued_at?: string | null
  permitted_at?: string | null
  completed_at?: string | null
  closed_at?: string | null
  approval_notes?: string | null
  closing_notes?: string | null
  created_at: string
  updated_at: string
}

export type OperationTicketType = 'POWER_OFF' | 'POWER_ON' | 'SWITCHING' | 'OTHER'
export type OperationTicketStatus =
  | 'DRAFT' | 'REVIEWED' | 'APPROVED' | 'EXECUTING' | 'COMPLETED' | 'CANCELLED'

export interface OperationStep {
  seq: number
  action: string
  expected?: string | null
  executed_at?: string | null
  executed_by?: string | null
  result?: 'PASS' | 'FAIL' | null
  notes?: string | null
}

export interface OperationTicket {
  id: number
  ticket_no: string
  title: string
  operation_type: OperationTicketType
  work_ticket_id?: number | null
  equipment_id?: number | null
  equipment_name?: string
  operator?: string | null
  supervisor?: string | null
  approver?: string | null
  steps: OperationStep[]
  status: OperationTicketStatus
  reviewed_at?: string | null
  approved_at?: string | null
  started_at?: string | null
  completed_at?: string | null
  notes?: string | null
  created_at: string
  updated_at: string
}

export const WT_TYPE_LABEL: Record<WorkTicketType, string> = {
  FIRST: '第一种工作票', SECOND: '第二种工作票', EMERGENCY: '紧急抢修',
}

export const WT_STATUS_LABEL: Record<WorkTicketStatus, string> = {
  DRAFT: '起草中', SUBMITTED: '已提交', ISSUED: '已签发',
  IN_WORK: '作业中', COMPLETED: '工作终结', CLOSED: '已归档', CANCELLED: '已取消',
}

export const OT_TYPE_LABEL: Record<OperationTicketType, string> = {
  POWER_OFF: '停电操作', POWER_ON: '送电操作', SWITCHING: '倒闸操作', OTHER: '其他',
}

export const OT_STATUS_LABEL: Record<OperationTicketStatus, string> = {
  DRAFT: '起草中', REVIEWED: '已审核', APPROVED: '已批准',
  EXECUTING: '执行中', COMPLETED: '已完成', CANCELLED: '已取消',
}

// ---- v2.3 备品备件 ----
export type StockMovementType = 'IN' | 'OUT' | 'ADJUST'

export interface SparePart {
  id: number
  code: string
  name: string
  spec?: string | null
  unit: string
  category?: string | null
  stock_qty: number
  min_qty: number
  unit_price: number
  location?: string | null
  supplier?: string | null
  notes?: string | null
  low_stock: boolean
  created_at: string
  updated_at: string
}

export interface StockMovement {
  id: number
  spare_part_id: number
  spare_part_code?: string
  spare_part_name?: string
  movement_type: StockMovementType
  qty: number
  defect_id?: number | null
  work_ticket_id?: number | null
  operator?: string | null
  notes?: string | null
  created_at: string
}

export const MV_TYPE_LABEL: Record<StockMovementType, string> = {
  IN: '入库', OUT: '出库', ADJUST: '盘点调整',
}

// ---- v2.3 设备 360 ----
export interface EquipmentProfile {
  equipment: Equipment
  record_stats: { total: number; normal: number; abnormal: number; severe: number }
  recent_records: Array<{
    id: number; point_id: number; status: string; finding?: string | null;
    recorded_by?: string; recorded_at: string; defect_id?: number | null
  }>
  open_defect_count: number
  recent_defects: Array<{
    id: number; defect_no: string; title: string; severity: string; status: string;
    reported_at: string; closed_at?: string | null
  }>
  open_ticket_count: number
  recent_tickets: Array<{
    id: number; ticket_no: string; work_content: string; ticket_type: string;
    status: string; principal?: string | null; created_at: string
  }>
  spare_usage: Array<{
    id: number; spare_part_code?: string; spare_part_name?: string; qty: number;
    operator?: string; defect_id?: number | null; work_ticket_id?: number | null;
    created_at: string; notes?: string | null
  }>
}

// ---- v2.2 预测性维护 ----
export interface PredictiveRiskItem {
  equipment_id: number
  code: string
  name: string
  equipment_system: string
  criticality: 'A' | 'B' | 'C'
  health_score: number
  defects_90d: number
  critical_90d: number
  abnormal_records_90d: number
  failure_probability: number   // 0-1
  risk_score: number            // 综合分数
  risk_level: 'HIGH' | 'MEDIUM' | 'LOW'
  recommendation: string
}

export interface DashboardOverview {
  equipment: { total: number; criticality_a: number; running: number; maintenance: number }
  today_tasks: { total: number; completed: number; missed: number; completion_rate: number }
  defects: { open: number; critical_open: number; overdue: number }
  tickets?: { work_in_progress: number; work_pending_approval: number; operation_executing: number }
  inventory?: { low_stock_items: number }
  avg_health_score: number
}

export interface DefectTrendItem { date: string; new: number; closed: number }
export interface SystemDistItem { system: string; equipment_count: number; open_defects: number }
export interface TopFaultyItem {
  equipment_id: number; code: string; name: string; criticality: Criticality;
  health_score: number; defect_count_30d: number
}
export interface HealthRankItem {
  id: number; code: string; name: string; criticality: Criticality;
  status: EquipmentStatus; health_score: number
}

export const SYSTEM_LABEL: Record<EquipmentSystem, string> = {
  BOILER: '锅炉系统', TURBINE: '汽轮机', GENERATOR: '发电机',
  AUXILIARY: '辅机', ELECTRICAL: '电气', CHEMICAL: '化学水',
  ASH: '除灰除渣', DESULFUR: '脱硫脱硝',
}

export const CRITICALITY_LABEL: Record<Criticality, string> = {
  A: 'A级（关键）', B: 'B级（重要）', C: 'C级（一般）',
}

export const EQ_STATUS_LABEL: Record<EquipmentStatus, string> = {
  RUNNING: '运行', STANDBY: '备用', MAINTENANCE: '检修', DECOMMISSIONED: '退役',
}

export const TASK_STATUS_LABEL: Record<TaskStatus, string> = {
  PENDING: '待执行', IN_PROGRESS: '进行中', COMPLETED: '已完成',
  MISSED: '漏检', CANCELLED: '已取消',
}

export const SEVERITY_LABEL: Record<DefectSeverity, string> = {
  MINOR: '一般', MAJOR: '重要', CRITICAL: '紧急',
}

export const DEFECT_STATUS_LABEL: Record<DefectStatus, string> = {
  NEW: '新建', ASSIGNED: '已派工', IN_REPAIR: '检修中',
  REPAIRED: '已修复', VERIFIED: '已验收', CLOSED: '已关闭',
  OVERDUE: '已超期', CANCELLED: '已取消',
}
