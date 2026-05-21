# 任务跟踪

## v1.0（已完成，2026-05-21）

### 后端
- [x] 5 角色用户体系（ADMIN/INSPECTOR/REPAIRMAN/SUPERVISOR/VIEWER）+ JWT
- [x] 7 张表：User / Equipment / InspectionRoute / InspectionPoint / InspectionTask / InspectionRecord / Defect
- [x] 设备台账：8 系统 + 3 级关键度 + 状态机 + QR 码 + 健康度
- [x] 点检路线 + 测点：检查项 JSON、频率（班/日/周/月）
- [x] 任务生成 + 测点录入 + 自动完成判定 + 漏检扫描
- [x] 点检异常 → 自动生成缺陷（severity 由 设备等级 × 异常程度 推导）+ SEVERE 自动转设备 MAINTENANCE
- [x] 缺陷状态机：NEW → ASSIGNED → IN_REPAIR → REPAIRED → VERIFIED(=CLOSED)，含 OVERDUE 标记
- [x] SLA：MINOR 72h / MAJOR 24h / CRITICAL 4h
- [x] 健康度联动：缺陷扣分、验收回弹、自动恢复 RUNNING
- [x] Dashboard：4 KPI + 缺陷趋势 + 系统分布 + 高发故障设备 + 健康度榜
- [x] seed_data：5 用户 + 18 设备（覆盖 8 系统）+ 3 路线 + 一周任务 + 6 缺陷样例
- [x] 角色权限拦截：require_inspector / require_repairman / require_supervisor / require_write

### 前端
- [x] 登录页（橙色主题）+ Layout + 5 个菜单
- [x] Dashboard：4 KPI + 2 ECharts 图 + 2 排行榜
- [x] EquipmentList：分页 + 系统/等级/状态/关键词筛选 + 登记 Modal + 转检修/恢复
- [x] RouteList：分页 + 测点查看 Drawer（含检查项明细）
- [x] TaskList：分页 + 状态筛选 + 任务详情 Drawer + 测点录入 Modal + 扫描漏检
- [x] DefectList：分页 + 多筛选 + 上报 + 派工 / 开始检修 / 提交修复 / 验收 全流程按钮 + 扫描超期
- [x] 全前端 stores/auth + canInspect / canRepair / canSupervise / canWrite

### 文档
- [x] README.md
- [x] CLAUDE.md
- [x] TASK.md

## v2.0（已完成，2026-05-21）

### 后端
- [x] APScheduler 内置定时调度器：sweep_overdue / sweep_missed / auto_generate_tasks / retry_safety_sync 四个 job，应用 lifespan 启停
- [x] `app/integration/safety_client.py`：CRITICAL 缺陷推送 plant-safety，幂等重试 + 失败回退 PENDING/FAILED
- [x] Defect 模型新增 safety_sync_status / safety_hazard_no / safety_sync_at / safety_sync_attempts / safety_sync_error 字段
- [x] tasks 自动生成缺陷 & defects 手动上报均触发联动
- [x] `/api/scheduler/jobs` + `/api/scheduler/run/{job_id}`：查看下次执行 / 上次结果 / 手动触发
- [x] `/api/reports/equipments/export`、`/api/reports/defects/export`（带 BOM 的 CSV）
- [x] `/api/reports/monthly`：近 N 个月新增/关闭/平均处理时长/SLA 达成率/分严重度
- [x] `/api/reports/equipment-availability`：按系统的设备可用率 + 平均健康度
- [x] `/api/defects/{id}/safety-sync`：手动重推单个缺陷
- [x] APP_VERSION 升至 2.0.0；INTEGRATION/SCHEDULER 相关配置项加齐

### 前端
- [x] 新增 `pages/Reports.tsx`：月度趋势 ECharts + 报表表格 + 系统可用率 + CSV 导出 + 调度器状态
- [x] 菜单加"报表导出"入口（BarChartOutlined）
- [x] DefectList 加"隐患联动"列（彩色标签）+ CRITICAL 缺陷"重推隐患"按钮
- [x] `api/index.ts` 新增 reportApi / schedulerApi / downloadCsv
- [x] types 增加 MonthlyReportItem / AvailabilityItem / SchedulerJob，Defect 增加 safety_* 字段

## v2.1（已完成，2026-05-21 续）

### 后端
- [x] 文件上传：`POST /api/uploads`，本地 disk 存储到 `UPLOAD_DIR/YYYYMMDD/<uuid>_<safe>`，5MB 限制，扩展名白名单
- [x] FastAPI StaticFiles 挂载 `/uploads`，URL 形如 `/uploads/20260521/xxx.jpg`
- [x] WebSocket：`/ws?token=...` JWT 鉴权，ConnectionManager + 跨线程 emit_sync + 异步 drain_loop
- [x] 5 个推送事件：defect.critical_created / defect.overdue_swept / task.missed_swept / defect.safety_synced / defect.safety_sync_failed
- [x] defects/tasks/scheduler 三处生产事件，已与 plant-safety 联动结果对齐
- [x] seed_data 加 v2 safety_sync_status 字段示例（SYNCED/FAILED/PENDING/SKIPPED 各覆盖）

### 前端
- [x] uploadApi.customRequest 通用 antd Upload 适配
- [x] DefectList 上报 Modal 改用 Upload 组件（≤5MB，图片格式）
- [x] TaskList 测点录入 Modal 同步改造
- [x] `hooks/useRealtime.ts`：自动重连（指数退避 + 鉴权失败不重试），全局 notification 弹窗
- [x] Layout 启用 WS hook（依赖 token，登录后自动连）
- [x] vite.config.ts 加 `/uploads` 和 `/ws` 代理（含 ws: true）

## v2.2（已完成，2026-05-21 续）

### 后端
- [x] WorkTicket / OperationTicket 双模型 + 状态机
- [x] 工作票流程：DRAFT → SUBMITTED → ISSUED → IN_WORK → COMPLETED → CLOSED
  - 安全措施 JSON + 逐条勾选 API
  - 关联缺陷 / 设备，许可开工自动转 MAINTENANCE，归档无在工票自动恢复 RUNNING
- [x] 操作票流程：DRAFT → REVIEWED → APPROVED → EXECUTING → COMPLETED
  - steps JSON 支持分步执行 PASS/FAIL，全部完成自动 COMPLETED
- [x] `GET /api/equipments/by-code/{code}`：扫码查设备（支持 `EQ::` 前缀去除）
- [x] `GET /api/predictive/ranking`：综合风险分算法（缺陷数 30% + CRITICAL 25% + 异常 15% + 健康度 20% + 等级/状态加成），sigmoid 平滑成失效概率 + 等级 + 建议
- [x] seed_data 加 2 张工作票 + 1 张操作票样例

### 前端
- [x] WorkTicketList：列表 + 起草 Modal + 详情 Drawer + 安全措施清单（含逐条勾选按钮）+ 流转按钮
- [x] OperationTicketList：列表 + 起草 + 详情 + Steps 组件可视化进度 + 逐步执行 Modal
- [x] PredictiveMaintenance：4 KPI + 健康度×风险分散点图 + Top 30 表格（含失效概率/等级/建议）
- [x] PWA：`manifest.webmanifest` + `/sw.js` + 2 个 SVG 图标 + index.html meta + main.tsx 注册 SW
- [x] MobileScan `/m/scan`：独立移动端登录页 + BarcodeDetector 摄像头扫码 + 手动输入降级 + 拍照上报缺陷
- [x] Layout 菜单 +3 项（工作票 / 操作票 / 预测维护）

## v2.3（已完成，2026-05-21 续）

### 后端
- [x] SparePart + StockMovement 模型 + CRUD + 出入库 API
- [x] `/api/spare-parts/stats/overview` 库存总览
- [x] `/api/equipments/{id}/profile` 设备 360 聚合（点检 + 缺陷 + 工作票 + 备件耗用，90 天窗口）
- [x] Dashboard overview 加 tickets / inventory 段
- [x] seed_data 加 12 条物料 + 出入库流水样例
- [x] plant-safety 端新增 `/api/integration/hazards` 接收接口（X-Integration-Secret 头校验 + 幂等），equipment-inspection v2.0 联动从此 E2E 跑通

### 前端
- [x] SparePartList 页：4 KPI + 表格 + 出入库 Modal + 流水 Drawer + 低库存过滤
- [x] EquipmentList 加详情入口 + Tabs Drawer（点检/缺陷/工作票/备件 4 个 tab）
- [x] Dashboard 加 3 张 v2.2/2.3 卡片（路由可点击跳转）
- [x] DefectList 加"工作票"按钮，预填 defect_id 跳转
- [x] WorkTicketList 详情 Drawer 加打印按钮 + 接收 `?defect_id=` 自动开 Modal
- [x] WorkTicketPrint 独立路由 A4 打印页（@media print 优化）

## v2.4（已完成，2026-05-21 续）

### 后端
- [x] 用户管理 API：`/api/users` CRUD + `/{id}/reset-password` + `/{id}/toggle-active`，ADMIN-only
- [x] `require_admin` 依赖（仅 ADMIN）
- [x] 用户保护：admin / 当前用户 不可禁用，admin 不可降级
- [x] OperationTemplate 模型 + `/api/operation-tickets/templates` 系列接口
- [x] OperationTicketCreate 支持 `template_id` 复用 steps，模板 use_count 自增
- [x] `/templates/from-ticket/{oid}` 把操作票另存为模板

### 前端
- [x] UserManagement 页：仅 ADMIN 菜单显示；表格 + 新增/编辑/重置密码/启停 Modal
- [x] OperationTicketList 顶部下拉"模板"，选中即复用并打开起草 Modal
- [x] 详情 Drawer 加"另存为模板"按钮 + Modal

## v2.5（已完成，2026-05-21 续）

### 后端
- [x] `GET /api/equipments/{id}/qr.svg`：segno 生成 SVG QR（内容 `EQ::CODE`）
- [x] AuditLog 模型 + `app/utils/audit.log()` 工具函数（失败不阻塞业务）
- [x] `GET /api/audit`：ADMIN-only 审计列表，支持 actor/action/target_type/keyword 过滤
- [x] 关键写操作接入审计：defect.create / defect.assign / defect.verify_pass / defect.verify_reject / wt.issue / wt.permit / wt.close / user.create / user.reset_password
- [x] requirements.txt 加 segno

### 前端
- [x] `/equipment-qr-print` 批量 QR 打印页（独立路由，4 列 A4 网格，@media print）
- [x] EquipmentList 顶栏加"批量 QR 打印"按钮
- [x] `/audit` AuditLog 页：彩色 action 标签 + 关键词搜索 + 分页
- [x] Layout 菜单：ADMIN 看到"用户管理"+"审计日志"两项

## v3.0（规划）

- [ ] 文件存储扩展：S3 / OSS 适配（当前仅本地 disk）
- [ ] 两票电子签名（CA 集成）
- [ ] 移动端 PWA 离线模式（IndexedDB 暂存点检记录）
- [ ] 备件采购申请单（低库存自动转采购提醒，与 fuel-procurement 系统对齐流程）
- [ ] Docker Compose 一键启动 equipment-inspection + plant-safety

## v4.0（远期规划）

- [ ] 预测性维护：基于近 90 天点检数据预测设备失效概率
- [ ] 与 DCS 报警系统对接：报警自动转缺陷工单
- [ ] 备品备件库存联动（与未来的 plant-materials 系统）
- [ ] 移动端语音录入（点检员现场免提）
