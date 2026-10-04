# Stocktake Snapshot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans inline, then one fresh whole-branch review. Steps use checkbox syntax.

**Goal:** 拒绝过时绝对盘点，避免覆盖读取后新增的出入库。
**Architecture:** 使用同备件最后流水ID作为只读stock_revision；库存/版本单SELECT，锁后校验expected_stock_revision。前端固定显示快照，冲突后重新读取并显式输入。
**Tech Stack:** SQLAlchemy/FastAPI、SQLite/PostgreSQL、React/AntD、pytest/Chromium。
**Spec:** ../specs/2026-10-04-stocktake-snapshot-design.md

## Global Constraints

- 基线170b8393e622d31e23a5a546419748183f07ce20，既有隔离worktree，maintenance/stocktake-snapshot-20261004。
- 不新增DDL/迁移或依赖；HEAD=0003；stock_revision为同备件最后已提交StockMovement.id，无流水0。
- expected_stock_revision JSON整数0..2147483647，ADJUST缺失/null409，过时409，IN/OUT可省略；零盘点有效。
- 旧盘点客户端需升级；原采购UUID重放/部分取消/权限规则保留。
- ADJUST缺字段文案：“盘点信息不完整，请更新客户端并刷新库存后重新盘点”。过时文案：“库存已有变动，请关闭并刷新库存，核对后重新盘点”。

## Review Focus

1. SQL表达式、关联加载、ORM缓存或提交后的读取不能组合旧库存和新版本。
2. 流水回滚/UUID重放/另一备件/仅更新元数据时，版本变化必须与真实库存写入对应。
3. 数量先变后恢复、同版本盘点与等待锁的请求不得绕过校验；零盘点仍有效。
4. 前端冲突、取消、刷新和重新打开不得静默换版本并保留旧数量提交。
5. 旧客户端、无效版本、角色拒绝及不存在备件/关联对象保持清晰错误，冻结迁移合同不变。

### Task 1: 真实数据库版本与盘点校验

**Files:** backend/app/models/spare_part.py、backend/app/schemas/spare_part.py、backend/app/api/spare_parts.py；新增backend/tests/postgresql/test_stocktake_snapshots.py；更新test_stock_quantities.py的合法归零请求。
**Interfaces:** SparePart.stock_revision只读int；SparePartResponse.stock_revision:int；MovementCreate.expected_stock_revision:int|None；create_movement成功响应stock_revision:int。

- [ ] 写真实API失败回归：原10库存IN2后ADJUST10/expected0须409且保留12和一条流水；OUT、收货与ABA分别验证。同版本两个盘点只有200/409；GET/列表在另一事务提交后保留成对旧库存/旧版本；提交后被暂停的成功响应保留本次库存与流水ID。
- [ ] 跑新测试，确认红灯来源是缺少版本/旧盘点被接受/响应被后来事务污染；角色/不存在目标作为既有行为控制。
- [ ] 用相关scalar SELECT的column_property提供同SQL快照版本；锁后校验，真实flush失败保留原版本；流水flush后提交前生成固定成功响应。
- [ ] 验证strict版本、另一备件不干扰、同数量盘点推进版本、元数据更新不推进、真实约束回滚及UUID重放不推进；合法归零请求携带0。运行新文件及库存/重放/采购状态套件，期望SQLite/PG全通过。

### Task 2: 固定显示快照与显式重新确认

**Files:** frontend/src/types/index.ts、frontend/src/api/index.ts、frontend/src/pages/SparePartList.tsx、frontend/e2e/stock.spec.ts。
**Interfaces:** SparePart.stock_revision:number；createMovement可接收expected_stock_revision:number并返回stock_revision:number；只在ADJUST附加打开时current.stock_revision。

- [ ] 写真实Chromium冲突回归：对话框读取10后API入库2，提交0返回409且仍保持原输入/基准；重复确认仍409；关闭刷新后显示12、ADJUST数量为空，用户输入11成功且流水只有IN与一次ADJUST。
- [ ] 在后端新校验已生效、前端未改时跑stock.spec，确认归零/重新确认链路失败，作为前端RED。
- [ ] 实际HTTP响应提交后暂停送达，确认旧UI仍能取消；修复期间禁用编辑/关闭并防止重复发起，解除暂停后成功关闭原表单。
- [ ] 在对话框显示基准、ADJUST选择清空数量；打开/取消重置表单，显式关闭刷新按钮；旧输入或列表后台刷新不改当前基准。保持原角色/数量控件。
- [ ] 真实Chromium验收归零、过时盘点/重新确认、ABA以及取消重开；npm test与tsc/Vite通过。

### Task 3: 审查、集成与结果

**Files:** README.md、docs/STOCKTAKE-SNAPSHOT.md、原库存/采购技术说明；作品集README/DEMO/ROADMAP/长期规划/状态与新发布证据。

- [ ] 完整后端（实际PG与备份包装）、Node/build、API、Ruff/diff；一次fresh whole-branch review，重要发现先复现再一次修复，重新完成相应验收。
- [ ] 本地/上传tree一致，PR Quality和Compose通过后按授权合并；核对新main tree及Quality。
- [ ] 固定提交、旧盘点客户端409兼容边界和简短测试结果写入证据；作品集同步合并；停止自建容器/服务并归档本计划ledger，下一项采购创建/自动补货边界。
