# Purchase State Consistency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan inline, then one fresh whole-branch review. Steps use checkbox syntax.

**Goal:** 消除采购取消/审批等旧状态覆盖收货或取消结果，状态与审计原子提交。
**Architecture:** 复用备件锁，统一锁后刷新采购单；推送服务只修改 ORM，由 API 提交状态与审计。
**Tech Stack:** FastAPI/SQLAlchemy、SQLite/PostgreSQL、pytest、HTTP 测试服务。
**Spec:** ../specs/2026-10-04-purchase-state-consistency.md

## Global Constraints

- 基线 04f898fb63f4b389f95eba264eff3b7138850870，现有隔离 worktree，新分支 maintenance/purchase-state-20261004。
- 权限/JSON/400状态规则不变；部分收到2件后可取消且原 UUID 可确认，最后5件已完成后取消400。
- 锁顺序备件先、采购后；没有业务修改后再刷新；不修改冻结迁移，HEAD=0003。
- 同步推送持锁/远端不可回滚范围明确，只使用本地 HTTP 模拟服务与隔离数据库。

## Review Focus

1. 跨入口锁顺序和 ORM 关系缓存不能带回旧状态/库存。
2. 成功部分收货后合法取消不能被全量收货的断言误禁止。
3. 服务内部 commit/flush、状态或审计读取不得过早释放锁或使失败部分提交。
4. 实际网络成功/失败后锁释放与本地快照一致；跨系统原子性不作虚假承诺。
5. 角色拒绝、缺失单据/备件与既有 UUID 重放必须保留。

### Task 1: 状态竞争锁与刷新

**Files:** backend/app/api/purchase_requests.py；新增 backend/tests/postgresql/test_purchase_states.py，复用 stock_context 和 concurrency 工具。
**Interfaces:** `_lock_pr(db:Session,pid:int)->PurchaseRequest`；返回 joined spare_part，使用 lock_spare_part；submit/approve/reject/send/receive/cancel 统一调用。

- [ ] 写真实 API 交错回归：暂停首次采购 SELECT，再让取消/收货提交；读取旧状态的操作须按新状态拒绝。最终5件与部分2件分别验证状态、stock、received、ledger及UUID。
- [ ] 先跑 `pytest tests/postgresql/test_purchase_states.py -q`，确认旧状态覆盖失败，反向取消先完成的收货检查作为已有行为控制。
- [ ] 在 API 实现私有共用锁/刷新入口，保持权限/响应/状态规则；收货使用刷新后的 spare_part。
- [ ] 运行上述文件及 test_receipt_replay.py/test_stock_transactions.py；期望全通过 SQLite/真实PG。

### Task 2: 状态与审计原子性、实际推送

**Files:** backend/app/api/purchase_requests.py、backend/app/integration/procurement_client.py；Task1新测试文件、本地HTTP工具。
**Interfaces:** `push_request(db,pr)->dict` 保留签名/结果，停止自行commit；API统一审计和提交。

- [ ] 写真实 audit_logs 约束失败：approve/send 返回500，订单仍SUBMITTED/APPROVED，元数据/审计无部分提交；解除约束再成功。先确认失败。
- [ ] 合并审批提交、去掉推送服务commit；审核/推送结果保持原消息及快照。
- [ ] 本地HTTP服务器验证实际推送负载、成功/失败、发送完成与最后收货交错，数据库/审计真实验证，不替换锁/查询结果。
- [ ] 跑整个采购状态/重放/库存相关套件，全通过。

### Task 3: 集成、审查与发布

**Files:** README.md、docs/PURCHASE-STATE-CONSISTENCY.md、现有库存/收货说明；作品集导览、计划、状态和发布证据。

- [ ] 完整后端（真实PG及backup工具）、API演示、Ruff/diff、前端Node/tsc/Vite；保持未改前端的已有浏览器验证由Compose CI复验。
- [ ] 一次 fresh whole-branch requesting-code-review，重要问题先复现再一次修复，并完成套件验收。
- [ ] 本地/上传tree严格一致，PR Quality/Compose通过后按授权合并；核对main新CI。
- [ ] 文档更新固定基线、持锁与外部失败限制、下一项过时盘点；停止自建测试容器/服务，保留干净工作树。
