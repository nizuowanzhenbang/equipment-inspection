# 采购收货重放幂等 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** 部分收货响应丢失后使用稳定请求标识重试，只记账一次。
**Architecture:** 可选 UUID 和采购单作用域成功结果表，复用备件写锁；前端按账户/采购单保存未确认请求。冻结迁移及方言增量合同显式升级旧库。
**Tech Stack:** FastAPI/Pydantic、SQLAlchemy/Alembic、SQLite/PostgreSQL、React/TypeScript、Node test/Playwright。
**Spec:** ../specs/2026-10-03-purchase-receipt-idempotency.md

## Global Constraints

- 基线 b2bd35cea7ad40a0a0ab9b836707b6af6539738b；使用现有隔离 worktree。
- request_id 可选 UUID，旧客户端语义与响应格式不变；数量继续 Numeric(10,2) 边界。
- 同键不同数量/操作人 409；成功快照重放在首次状态检查之前，鉴权之后。
- 仅合成测试库，显式迁移；0001/0002 和十四表合同不改，禁止破坏性 downgrade。
- 原标识仅在确认成功或明确人工放弃后清除，首次发送前存储失败则不发请求。

## Review Focus

长尾/尾零数值等价与 UUID 标准化；HTTP 失败后身份/内容不得漂移；当前及旧版本的结构漂移不可借升级掩盖；成功后新状态仍可确认首次结果；另一标签页确认不得误删更新后的待确认记录。

### Task 1: 后端收货与显式迁移

**Files:** backend/app/api/purchase_requests.py、models/purchase_request.py、main.py、migrate.py、schema_contract.py；新增 migrations/versions/0003_purchase_receipts.py、contracts/{sqlite,postgresql}-receipts.json；tests/postgresql/test_receipt_replay.py 与 tests/test_migrations.py（共用 PG 继承）。
**Interfaces:** PRReceive.request_id: UUID|None；PurchaseReceipt 成功记录字段见 spec；validate_structure(..., require_receipts=True)；HEAD=0003_purchase_receipts。

- [x] 写真实接口回归：POST 两次相同键/数量 2，响应一致、stock=12、received=2、ledger=1；冲突 409；并发同键只一条；完整到货后重放仍 200；旧无键两次仍累计。先运行并确认预期失败。
- [x] 写迁移回归：使用冻结 0002 DDL 构建旧库并保留 sentinel，升级创建新表/版本；当前缺表及旧版本漂移拒绝；新表 DDL 注入失败后版本/数据保持，解除失败再升级。
- [x] 最小实现模型、冻结迁移、增量合同与严格版本预检；锁后查成功记录并匹配 actor_id/qty；库存/流水和快照一起提交。
- [x] 补真实约束失败、去重记录写入失败回滚、权限/跨账户/跨采购单与标准化回归；跑相关 tests/postgresql 与迁移文件。
- [x] 保持候选在 worktree，完成后与前端一同推送可复核提交。

### Task 2: 可恢复的前端收货请求

**Files:** frontend/src/utils/receiptAttempt.ts、tests/receipt-attempt.test.mjs、api/index.ts、pages/PurchaseRequestList.tsx、e2e/receipt.spec.ts。
**Interfaces:** loadReceiptAttempt(storage,username,pid):ReceiptAttempt|null；getReceiptAttempt(storage,username,pid,quantity):ReceiptAttempt；clearReceiptAttempt(storage,username,pid,requestId):void；ReceiptAttempt={requestId:string,quantity:number}。

- [x] 写存储/真实流程回归：相同账户/采购单复用 UUID，刷新复用；不同用户/单据隔离；数量漂移拒绝；不可写/损坏停止发送；仅清除匹配标识。先确认失败。
- [x] API receive(id,received_qty,request_id) 发送稳定标识；首次提交前保存，在途禁止重复；失败保留弹窗与数量，已完成订单仍能确认待确认请求。人工放弃提示先核对流水，不自动清理。
- [x] Chromium 实际创建/提交/批准采购单，route.fetch 成功后 route.abort 丢失响应；页面刷新后用同键重试，断言 stock=12、received=2、ledger=1；新真实到货使用新键正常累计。
- [x] 运行 Node 全套、TypeScript/Vite build、Chromium；修复后端/UI 均完成才进入全量 gate。

### Task 3: 集成验收与接续

**Files:** docs/PURCHASE-RECEIPT-REPLAY.md、DATABASE-MIGRATIONS.md、STOCK-CONSISTENCY.md、README.md；作品集最新状态及发布证据。

- [ ] 在真实 PG 及 SQLite 跑完整 python -m pytest -q，API 面试演示，Ruff 和 diff 检查；只在新失败/修复后重复必要检查。
- [ ] 使用 requesting-code-review 独立复核本分支，解决重要问题；验证 staged tree 与上传/合并 tree 相同。
- [ ] 推送 PR，等待 Quality/Compose，通过后按持续授权合并；核对 main 新 CI 和迁移兼容证据。
- [ ] 更新作品集、固定演示基线、限制与下一轮动作；停止自己创建的测试服务和容器，保留可接续工作树。
