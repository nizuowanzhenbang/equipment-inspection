# 设备采购与安全交付 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement task-by-task. Steps use checkbox syntax.

**Goal:** 完成 PP-030 四个采购边界单元及 PP-040 可恢复安全发送。
**Architecture:** 共用 Decimal/数据库锁/原子编号服务；不可变 outbox 与缺陷同事务，发送端严格核对 ACK；接收端独立配套计划。
**Tech Stack:** 既有 FastAPI/Pydantic/SQLAlchemy/Alembic、SQLite/PostgreSQL、React/TypeScript；无新框架。
**Spec:** ../specs/2026-10-12-procurement-boundaries.md、../specs/2026-10-12-safety-delivery.md。

## Global Constraints

- 数量 0 < qty <= 99999999.99，两位小数；金额 0 <= amount <= 9999999999.99，ROUND_HALF_UP 两位。
- SQLite/PostgreSQL，0004_reliability_state 增量升级、冻结结构契约，不自动修复漂移或改历史流水。
- API/调度都先锁全部候选物料再取编号；缺陷发送消息不可变，ACK 身份匹配才能成功。
- 基线 8047049，工作分支 upgrade/equipment-procurement-20261012；执行台账见本文。中央阶段与实际 SHA 分开保存。

## Review Focus

浮点解析非有限错误本身仍须可返回 422；旧编号删除/跨日不重复；跨物料锁序无死锁；并发收货与身份重放不超量；网络成功/本地失败与变更设备后重试不误报或变消息。全部在对应任务加入真实失败路径，不依赖 mock 返回值作为成功证据。

### Task 1 · Decimal 新建与原子序号/迁移

Files: app/api/purchase_requests.py、app/services/purchases.py、models/purchase_request.py、models/safety_outbox.py、main.py、migrate.py、schema_contract.py、migrations/versions/0004_reliability_state.py、schema_contracts/*-reliability.json；tests/postgresql/test_procurement_boundaries.py、tests/test_migrations.py。
Interfaces: allocate_purchase_number(db)->str；estimated_amount(qty,price)->Decimal。
- [ ] 新 API 数量/金额/删除后编号/并发及旧 0003 升级测试，确认真实 RED。
- [ ] 实现 DTO/Decimal/原子计数和迁移契约，完整套件及两数据库迁移通过，保存提交。

### Task 2 · 共用自动补货与超量收货

Files: services/purchases.py、api/purchase_requests.py、scheduler.py、frontend/src/pages/PurchaseRequestList.tsx；同一新增测试文件/前端测试。
Interfaces: generate_low_stock(db,applicant)->{created,skipped}，调用方一次提交。
- [ ] API/调度并发与重复、陈旧库存、建议/金额溢出跳过、合法继续、超收/合法重放 RED。
- [ ] 共用服务/锁序/拒绝副作用/页面可见原因，实现后全套 backend、PostgreSQL、frontend tests/build/interview_demo，推送 PP-030 阶段。

### Task 3 · 不可变安全 outbox 与严格回执

Files: models/safety_outbox.py、integration/safety_client.py、api/tasks.py/defects.py（按实际必要）、tests/test_safety_delivery.py、tests/postgresql/test_safety_delivery.py。
Interfaces: mark_pending(db,d) 同缺陷事务；push_one(db,d)->bool；retry_pending(db,limit)->dict。
- [ ] 真实 HTTP 故障/畸形 ACK、已接受后断线、Session 重启/内容变更、并发投递与本地失败 RED。
- [ ] 保存/刷新/提交顺序、回执验证与受控错误，完整套件/前端构建/迁移验收后推送候选。

### Task 4 · 整批审查与发布

- [ ] 接收端 PP-041 按独立计划完成；一次 fresh-context 整批两分支审查与冷恢复，Important 单次 RED→GREEN 修复，无重复审查。
- [ ] 接收端先发布，发送/采购再发布；固定候选及 main CI 通过；每项真实合并检查点/release/索引和最终摘要回写。

## 执行台账

当前只读核查/基线。插件 supporting-script resource 读取不可用，沿已版本化本计划与中央日志记录 brief/BASE/命令/结果；不读取或删除其他计划工作区。完整基线设备 306 passed/186 PostgreSQL skipped，安全 68 passed；第一条安全测试从根目录执行缺少 app 导入路径，改在 backend 按 CI 命令运行后通过，不计业务 RED。

Pre-flight: Task 1 提供编号/表/金额；Task 2 调用相同服务与锁序；Task 3 使用 Task 1 已创建 outbox，schema contract 必须包含两张新增表；接收 ACK 身份契约由 PP-041 提供，按接收端先部署。

## 采购实现阶段（2026-10-13 接续）

首次 48 个双数据库 API 回归 40 failed/8 passed，迁移旧头升级 1 failed；实现后目标采购/SQLite 迁移 66 passed。完整后端连真实 PostgreSQL 与同版本客户端 542 passed，原 PostgreSQL 客户端缺失失败均已排除。随后新增畸形 Unicode 编号后缀：先 2 failed、修复后 2 passed；最终整批完整套件将覆盖该新增用例。

前端既有 16 passed，TypeScript/Vite 构建通过；首次构建发现 autoGenerate 响应类型未同步 skipped，已按真实服务字段补齐。金额/编号/补货/超量收货已实现并保持身份重放；根目录与 backend 测试/import 路径错误仅作工具错误记录，不计业务 RED。无现场或跨库 exactly-once 声明。

Task 1/2: 实现及指定目标验证通过，生产阶段待提交；同批 outbox/接收端仍待实现，未合并。本计划最终闭合以全分支完整验证和中央签收为准。
