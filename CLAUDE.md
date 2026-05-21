# Claude Code 项目规则

## 项目定位

发电厂设备点检与缺陷管理系统。v1.0 聚焦"设备台账 → 点检路线 → 点检任务 → 缺陷工单 → 检修闭环"。

与 plant-safety 互补（前者是设备+缺陷，后者是分区+隐患），共享同一座电厂的设备数据但流程独立。

## 技术栈约束

- 后端：FastAPI + SQLAlchemy + Pydantic v2，与 plant-safety / coal-yard-management 同款分层
- 前端：React 18 + TypeScript + Ant Design 5 + ECharts + Zustand + Vite
- 端口：后端 8003 / 前端 5175（避开 fuel-procurement 8000/5173 与 coal-yard 8001/5174）
- 数据库：SQLite（开发）/ PostgreSQL（生产）

## 业务规则

### 设备分级
- A 级：关键设备（停机即停机组），如锅炉本体、汽轮机、发电机、主变
- B 级：重要设备（停机降负荷），如给水泵、风机、循环泵
- C 级：一般设备，如水处理、灰渣、辅助系统

### 设备状态机
- `RUNNING` ⇄ `STANDBY`（备用）⇄ `MAINTENANCE`（检修）
- `RUNNING`/`STANDBY` → `DECOMMISSIONED`（退役，不可逆）
- `SEVERE` 点检结果 + 设备处 `RUNNING` → 自动转 `MAINTENANCE`
- 缺陷验收通过且无其他未结缺陷 → 自动恢复 `RUNNING`

### 点检异常 → 缺陷生成规则
| 设备等级 | 测点 ABNORMAL | 测点 SEVERE |
|---|---|---|
| A 级 | MAJOR | CRITICAL |
| B 级 | MINOR | MAJOR |
| C 级 | MINOR | MAJOR |

### 缺陷状态机
`NEW` → `ASSIGNED` → `IN_REPAIR` → `REPAIRED` → `VERIFIED`(=`CLOSED`)
- 任意态可 `CANCELLED`（CLOSED/VERIFIED 除外）
- 超 SLA 未关闭 → `OVERDUE`（系统打标，不阻塞流转，扫描接口触发）
- 验收驳回 → 回到 `IN_REPAIR`

### SLA 处理时限
- `MINOR` 72 小时
- `MAJOR` 24 小时
- `CRITICAL` 4 小时

### 健康度算法
- 初始 100
- 缺陷生成扣分：CRITICAL -15、MAJOR -8、MINOR -3
- 缺陷验收回弹：CRITICAL +10、MAJOR +6、MINOR +3
- 限制 [0, 100]

### 编号规则
- 设备：`EQ-{BL/TB/GN/AX/EL/CH/AS/DS}-NNNN`（按系统分别累加）
- 路线：`RT-NNN`
- 测点：`PT-NNNN`
- 任务：`TK-YYYYMMDD-NNNN`（每天重新累加）
- 缺陷：`DF-YYYYMMDD-NNNN`（每天重新累加）

## 角色权限

| 角色 | 主要权限 |
|---|---|
| ADMIN | 全部 |
| INSPECTOR | 点检任务执行、录入测点结果、上报缺陷 |
| REPAIRMAN | 接受派工、开始检修、提交修复 |
| SUPERVISOR | 派工、验收、设备状态切换 |
| VIEWER | 只读 |

后端通过 `deps.require_inspector / require_repairman / require_supervisor / require_write` 拦截；前端 `stores/auth.canInspect / canRepair / canSupervise / canWrite` 禁用按钮。

## 代码风格

- API 响应统一 `{code, message, data}`，使用 `utils.helpers.api_response`
- 分页用 `paginate_response`
- 中文 docstring 和字段注释
- 前端中文 locale + 中文 label

## 已知简化

- 没有移动端（v3 计划：PWA + 扫码登记）
- 没有 WebSocket（v3 加超期实时提醒）
- 没有照片附件实际存储（v1 仅记录 URL）

## v2.0 新增能力（2026-05-21）

### 内置定时调度器（APScheduler，`app/scheduler.py`）
- `sweep_overdue_defects` 每 10min：将超 SLA 的 NEW/ASSIGNED/IN_REPAIR 缺陷置 OVERDUE
- `sweep_missed_tasks` 每 30min：将超时未做的 PENDING/IN_PROGRESS 任务置 MISSED
- `auto_generate_tasks` 每 60min：按路线 `frequency`（SHIFT/DAILY/WEEKLY/MONTHLY）补生成下一次任务，幂等
- `retry_safety_sync` 每 5min：重试 PENDING/FAILED 的 plant-safety 联动
- 通过 `SCHEDULER_ENABLED=false` 关闭；`/api/scheduler/jobs` 查看，`/api/scheduler/run/{id}` 手动触发

### plant-safety 联动（`app/integration/safety_client.py`）
- **触发条件**：缺陷 severity = CRITICAL 且 `SAFETY_SYSTEM_URL` 已配置
- **接口约定**：`POST {SAFETY_SYSTEM_URL}/api/integration/hazards`，Header `X-Integration-Secret: {INTEGRATION_SECRET}`
- **状态字段**：Defect.safety_sync_status ∈ {PENDING, SYNCED, FAILED, SKIPPED}，失败计数 safety_sync_attempts
- **失败处理**：HTTP 错误/超时 → 标 FAILED 记 error，调度器 5 分钟后自动重试；前端可点"重推隐患"手动触发
- 非 CRITICAL 缺陷标 SKIPPED；未配置 `SAFETY_SYSTEM_URL` 也标 SKIPPED

### 报表与导出（`app/api/reports.py`）
- 所有 CSV 输出带 UTF-8 BOM，Excel 直接打开不乱码
- `/api/reports/monthly?months=6`：近 N 月缺陷新增/关闭/平均处理时长/SLA 达成率/分严重度
- `/api/reports/equipment-availability?days=30`：按系统汇总 RUNNING 比例 + 平均健康度
- 前端 `Reports.tsx` 含双轴柱+线图、表格、CSV 下载按钮、调度器状态面板

## v2.2 新增能力（2026-05-21）

### 两票管理（`app/models/ticket.py`, `app/api/work_tickets.py`, `app/api/operation_tickets.py`）
- **工作票** WT-YYYYMMDD-NNNN：FIRST/SECOND/EMERGENCY 三类
  - 状态机：DRAFT → SUBMITTED → ISSUED → IN_WORK → COMPLETED → CLOSED；可 CANCELLED
  - 角色：起草人(applicant) → 工作负责人(principal) → 签发人(issuer, supervisor) → 许可人(permitter)
  - 安全措施 `safety_measures` JSON 数组 `[{seq,measure,checked,checked_by,checked_at}]`，专门 `/check-safety` 接口逐条勾选
  - 关联 Defect 可选；许可开工自动转设备 MAINTENANCE，归档时无其他在工票自动恢复 RUNNING
- **操作票** OT-YYYYMMDD-NNNN：POWER_OFF/POWER_ON/SWITCHING/OTHER
  - 状态机：DRAFT → REVIEWED(supervisor) → APPROVED(supervisor) → EXECUTING(inspector) → COMPLETED
  - steps JSON `[{seq,action,expected,executed_at,executed_by,result(PASS/FAIL),notes}]`
  - `/execute-step` 逐步落 result，全部完成自动 COMPLETED

### 预测性维护（`app/api/predictive.py`）
- 综合风险分 = 缺陷数(30%)+CRITICAL(25%)+点检异常(15%)+健康度衰减(20%) + 等级加成(A+15/B+5)+状态加成(MAINTENANCE+10)
- failure_probability = sigmoid((risk_score-50)/12) → [0,1]
- risk_level：≥65 HIGH，≥40 MEDIUM，否则 LOW
- 自动给出 recommendation 字符串

### PWA + QR 扫码（`frontend/public/{manifest.webmanifest,sw.js,icon-*.svg}`, `pages/MobileScan.tsx`）
- 通过 manifest 可"添加到主屏幕"，独立窗口运行
- Service Worker 缓存 shell，API 走网络优先（不缓存）
- `/m/scan` 独立路由（不进 Layout）：登录 → 扫码（BarcodeDetector）/手动输入 → getByCode → 上报缺陷
- 后端 `GET /api/equipments/by-code/{code}` 支持 `EQ::xxx` 前缀去除

## v2.3 新增能力（2026-05-21）

### 备品备件（`app/models/spare_part.py`, `app/api/spare_parts.py`）
- SparePart：code（SP-NNNN）、name、spec、unit、category、stock_qty、min_qty、unit_price、location
- StockMovement：IN/OUT/ADJUST，可关联 defect_id / work_ticket_id
- 出库时自动校验库存充足；ADJUST 直接置目标值
- 低库存 = stock_qty < min_qty，列表/Dashboard 自动标红

### 设备 360 全景（`/api/equipments/{id}/profile`）
- 90 天窗口聚合：record_stats / recent_records / recent_defects / open_defect_count / recent_tickets / open_ticket_count / spare_usage
- 备件耗用通过 defect_id / work_ticket_id 反查 StockMovement(OUT)

### 工作票打印（`pages/WorkTicketPrint.tsx`, 路由 `/work-tickets/:id/print`）
- 独立路由（不进 Layout），A4 排版，@media print 隐藏工具栏
- 浏览器原生 print() 即可输出物理打印或 PDF

### plant-safety v1.1 接收接口
- `POST /api/integration/hazards`：X-Integration-Secret 头鉴权
- 幂等：external_source + external_no 联合唯一
- CRITICAL→MAJOR 隐患（14d 整改）；其他→GENERAL（30d）
- 设备编号前缀自动映射 HazardArea
- 返回 `{hazard_no, id, duplicated}`，equipment-inspection 写回 Defect.safety_hazard_no
