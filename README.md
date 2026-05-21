# 发电厂设备点检与缺陷管理系统 v2.5

围绕「设备台账 → 点检路线 → 点检任务 → 缺陷工单 → 检修闭环」的发电厂设备运维管理系统。

## 项目定位

与 [plant-safety](../plant-safety) 互补：

| 维度 | plant-safety | equipment-inspection |
|---|---|---|
| 关注点 | 分区 + 风险类别 | 设备台账 + 点检测点 |
| 核心实体 | 隐患单（YH-xxx） | 设备 + 缺陷单（DF-xxx） |
| 闭环 | 排查 → 整改 → 复查 | 点检 → 派工 → 检修 → 验收 |

二者通过"设备名/编号"互查；v2.0 起 **CRITICAL 缺陷自动联动建一条 plant-safety 隐患单**（共享 `INTEGRATION_SECRET`，APScheduler 失败重试）。

## 技术栈

- **后端**：FastAPI + SQLAlchemy 2 + Pydantic v2，JWT 鉴权
- **前端**：React 18 + TypeScript + Ant Design 5 + ECharts + Zustand + Vite
- **数据库**：SQLite（开发）/ PostgreSQL（生产）
- **端口**：后端 8003，前端 5175（避开 fuel-procurement 8000/5173、coal-yard 8001/5174）

## 核心模型

7 张表 / 6 个核心实体：

1. **User**：5 角色 ADMIN / INSPECTOR / REPAIRMAN / SUPERVISOR / VIEWER
2. **Equipment**：设备台账，按 8 个系统分类，3 级关键度（A/B/C），QR 码 + 健康度
3. **InspectionRoute** + **InspectionPoint**：点检路线与测点，路线含频率（班/日/周/月）+ 多个测点 + 每个测点的检查项 JSON
4. **InspectionTask** + **InspectionRecord**：任务与每测点的检查结果
5. **Defect**：缺陷工单，状态机闭环 NEW → ASSIGNED → IN_REPAIR → REPAIRED → VERIFIED → CLOSED

## 关键业务规则

### 设备分级与编号
- 编号 `EQ-{SYS}-NNNN`，系统代码 BL/TB/GN/AX/EL/CH/AS/DS
- A 级 = 关键设备（停机即停机组），B 级 = 重要，C 级 = 一般
- 缺陷严重度自动决定：A 级 + SEVERE → CRITICAL，A 级 + ABNORMAL → MAJOR，其他 → MINOR

### 点检异常自动建单
- 点检员录入 `ABNORMAL` 或 `SEVERE` → 自动生成对应级别缺陷工单
- `SEVERE` + 设备 RUNNING → 设备自动转 `MAINTENANCE`
- 健康度衰减：CRITICAL -15、MAJOR -8、MINOR -3

### SLA 与超期
- MINOR 72 小时 / MAJOR 24 小时 / CRITICAL 4 小时
- `POST /api/defects/sweep-overdue` 扫描超期单（外挂 cron / 前端按钮触发）

### 缺陷闭环
- 派工（SUPERVISOR）→ 开始检修（REPAIRMAN）→ 提交修复 → 验收
- 验收通过 → 设备健康度回弹 + 若无其他未结缺陷 → 设备恢复 RUNNING

## 快速开始

### 后端

```bash
cd backend
pip install -r requirements.txt
python seed_data.py      # 生成 5 用户 + 18 设备 + 3 路线 + 一周任务 + 6 个典型缺陷
uvicorn app.main:app --port 8003 --reload
```

### 前端

```bash
cd frontend
npm install
npm run dev              # http://localhost:5175
```

### 默认账户

| 用户名 | 密码 | 角色 |
|---|---|---|
| admin | admin123 | 管理员（全部） |
| inspector | inspector123 | 点检员（任务/录入） |
| repairman | repairman123 | 维修工（检修） |
| supervisor | supervisor123 | 设备主管（派工/验收） |
| viewer | viewer123 | 只读 |

## API 全景

| 路由 | 说明 |
|---|---|
| `POST /api/auth/login` | 登录获取 JWT |
| `GET /api/equipments` + `POST/PUT` | 设备 CRUD + 转检修/恢复 |
| `GET /api/routes` + `POST` | 路线与测点管理 |
| `GET /api/tasks` + `POST /generate` + `POST /{id}/records` | 任务生成与录入 |
| `POST /api/tasks/sweep-missed` | 扫描漏检任务 |
| `GET /api/defects` + `POST /assign /repair /verify` | 缺陷工单闭环 |
| `POST /api/defects/sweep-overdue` | 扫描超期缺陷 |
| `POST /api/defects/{id}/safety-sync` | 手动重推 plant-safety 联动（v2） |
| `GET /api/dashboard/*` | 5 个看板接口 |
| `GET /api/reports/monthly` / `equipment-availability` | 月度/可用率报表（v2） |
| `GET /api/reports/equipments/export` / `defects/export` | CSV 导出（v2） |
| `GET /api/scheduler/jobs` / `POST /api/scheduler/run/{id}` | 调度器查看 + 手动触发（v2） |
| `POST /api/uploads` | 文件上传（≤5MB，图片/PDF），返回 `/uploads/...` URL（v2.1） |
| `WS /ws?token=...` | WebSocket 推送 CRITICAL/OVERDUE/MISSED/联动事件（v2.1） |
| `GET /api/equipments/by-code/{code}` | 按设备编号或 QR 内容查（v2.2） |
| `GET/POST /api/work-tickets` + 流转 `/submit /issue /permit /complete /close /cancel` | 工作票全闭环（v2.2） |
| `POST /api/work-tickets/{id}/check-safety?step_seq=N` | 安全措施逐条勾选（v2.2） |
| `GET/POST /api/operation-tickets` + 流转 `/review /approve /start /execute-step /cancel` | 操作票 + 逐步执行（v2.2） |
| `GET /api/predictive/ranking` | 预测性维护风险榜 Top N（v2.2） |
| `GET /api/spare-parts` + 流水 + `/stats/overview` | 备品备件 + 出入库 + 低库存预警（v2.3） |
| `GET /api/equipments/{id}/profile` | 设备 360 全景（v2.3） |
| `GET/POST /api/users` + 流转 `/{id}/reset-password /toggle-active` | 用户管理（ADMIN-only，v2.4） |
| `GET/POST /api/operation-tickets/templates` + `/from-ticket/{oid}` + `DELETE /{tid}` | 操作票模板（v2.4） |
| `GET /api/equipments/{id}/qr.svg` | 设备 QR 码 SVG（v2.5） |
| `GET /api/audit` | 审计日志（ADMIN-only，v2.5） |

## Dashboard 看点

1. **4 KPI**：设备总数 / 今日点检完成率 / 待处理缺陷 / 平均健康度
2. **缺陷趋势**：近 30 天新增 vs 关闭
3. **系统分布**：8 个系统的设备数 + 未关缺陷柱状对比
4. **高发故障设备 TOP 5**：30 天缺陷数倒序
5. **健康度倒序榜**：A 级优先 + 健康度倒序

## v2.0 新增

- **内置 APScheduler 调度器**：4 个 job（缺陷超期扫描 10min / 漏检扫描 30min / 自动生成任务 60min / 联动重试 5min），lifespan 启停，无需外挂 cron
- **plant-safety 联动**：CRITICAL 缺陷落库即推送，失败自动重试，缺陷列表显示联动状态 + 隐患单号
- **CSV 导出**：设备台账全量 / 缺陷工单按时间范围（UTF-8 BOM，Excel 直开）
- **报表页面**：6 个月新增/关闭/SLA 达成率/平均处理时长趋势 + 各系统设备可用率 + 调度器状态面板
- **缺陷列表"重推隐患"按钮**：失败的联动可手工补推

## v2.1 新增

- **照片真上传**：`POST /api/uploads` 本地 disk 存储，缺陷上报 + 测点录入均换成 antd Upload 组件
- **WebSocket 实时推送**：CRITICAL 缺陷新建、缺陷超期、任务漏检、联动成功/失败全推到前端 notification
- **WS 连接管理**：自动重连（指数退避，鉴权失败不重试），ConnectionManager 跨线程 emit
- **seed_data v2**：示例缺陷加 SYNCED/FAILED/PENDING/SKIPPED 联动状态，报表/列表演示更直观

## v2.2 新增

- **两票管理**：工作票（第一种/第二种/紧急抢修）+ 操作票（停电/送电/倒闸），全状态机闭环，与缺陷工单挂钩
- **工作票联动设备**：许可开工自动转设备 MAINTENANCE；收票归档时若无其它在工票自动恢复 RUNNING
- **操作票分步执行**：每步可单独记录 PASS/FAIL 结果，全部完成自动标 COMPLETED
- **预测性维护**：基于近 90 天缺陷/紧急/点检异常/健康度/等级的综合风险算法，给每台设备打 0–100 风险分 + 失效概率 + 处置建议
- **PWA + QR 扫码点检**：manifest + service worker + 安装到主屏幕；`/m/scan` 移动端扫码页（用浏览器原生 BarcodeDetector + 手动输入降级），扫到 QR → 拉设备 → 上报缺陷一气呵成
- **风险散点图**：健康度 × 风险分散点（颜色=等级，大小=A/B/C）+ Top 30 重点关注表

## v2.3 新增

- **备品备件管理**：SparePart + StockMovement，出入库/盘点流水，与缺陷/工作票关联领用，安全库存预警
- **设备 360 全景**：`/api/equipments/{id}/profile` 聚合 90 天点检 + 缺陷 + 工作票 + 备件耗用 + 风险评分
- **Dashboard 整合 v2.2+ 数据**：在工工作票 / 执行中操作票 / 低库存预警 3 张联动卡片
- **缺陷一键开工作票**：缺陷列表"工作票"按钮带 defect_id 自动跳转并预填起草表单
- **工作票打印视图**：`/work-tickets/{id}/print` A4 友好排版，浏览器原生 print() 即可输出 PDF
- **plant-safety v1.1 接收接口**：CRITICAL 缺陷自动落隐患单，X-Integration-Secret 鉴权 + 幂等去重，本系列首个跨系统真闭环 ✅

## v2.4 新增

- **用户管理**：ADMIN 可 CRUD 用户 + 重置密码 + 启用/禁用；不可禁用自己或内置 admin
- **操作票模板库**：常用倒闸序列保存为模板，新建操作票时下拉一键复用；详情可"另存为模板"，模板有使用次数计数（自然冷热分层）

## v2.5 新增

- **设备 QR 码**：后端用 segno 生成 SVG，前端 `/equipment-qr-print` 批量打印页（A4 4 列网格，浏览器原生 print()）
- **MobileScan 闭环**：上面打印的 QR 内容是 `EQ::CODE`，可直接用 `/m/scan` 移动页扫
- **审计日志**：AuditLog 表 + `app/utils/audit.log()` 一行打点工具
- 已接入关键写操作：上报缺陷、派工、验收通过/驳回、工作票签发/许可/归档、创建用户、重置密码
- ADMIN 可在"审计日志"菜单看到全部记录，支持单号/摘要关键词检索

## 与 plant-safety 联动 quick-start

1. 启动 plant-safety v1.1+：`cd plant-safety/backend && uvicorn app.main:app --port 8000`
2. 启动 equipment-inspection 时配 `SAFETY_SYSTEM_URL=http://localhost:8000`（可写入 `backend/.env`）
3. 两侧 `INTEGRATION_SECRET` 必须一致（默认 `coal-integration-shared-secret`）
4. 测试：在 equipment-inspection 上报一条 CRITICAL 缺陷 → plant-safety 会自动生成一条 MAJOR 隐患单，且 Defect.safety_hazard_no 被写回
5. 失败时调度器 `retry_safety_sync` 每 5 分钟自动重试

## 已知简化（v3+ 规划）

- 上传仅本地 disk（v3 加 S3/OSS）
- 设备可用率为快照口径（基于当前 RUNNING 比例），非时间加权
- 健康度算法为线性估算
- WebSocket 单进程内存，多实例需 Redis pubsub
- BarcodeDetector 仅 Chromium 系移动端支持，iOS Safari 暂走手动输入
