# 采购状态与收货竞争

2026-10-04，基于 PR #12 的 main `04f898fb63f4b389f95eba264eff3b7138850870`。没有新增迁移，数据库 HEAD 保持 `0003_purchase_receipts`。

## 问题与行为

收货已把一张采购单的最后 5 件入库，但另一请求仍使用之前读到的 APPROVED 状态取消，旧实现会把 RECEIVED 覆盖为 CANCELLED。提交、批准、驳回和推送同样可能在取消已经成功后，使用旧状态重新修改单据。

这些既有状态 API 现在与收货共用备件写锁，顺序为查询单据取得备件 ID → 取得备件锁 → 刷新采购单及备件关系 → 按当前状态判断 → 业务写入与提交。鉴权在入口执行；JSON、角色和状态规则保持原约定。缺失单据/备件为 404，无效状态为 400。

取消先提交后，等待中的首次收货/批准/提交/驳回/推送按最新 CANCELLED 状态拒绝。最终到货先提交时，取消被拒绝，库存、流水与 RECEIVED 一致。同时批准和驳回只有一个能从 SUBMITTED 成功；重复状态操作等待后必须重新判断。

部分到货 2 件后取消仍合法，保留 stock=12、received=2 和原入库流水；取消不执行退库。已经成功的 UUID 仍可确认原结果，保持首次快照，不重新累计。不能用“只有一项请求成功”作为所有竞争的断言：先提交再取消、先推送再取消、部分收货再取消可以都是合法的先后操作。

## 状态、审计与推送

审批状态/操作人/时间及 `pr.approve` 审计在同一事务；推送的 SENT、时间、外部单号及 `pr.send` 审计也一起提交。真实数据库审计约束失败时，状态与元数据全部回滚，解除故障后可以重试。推送服务仅修改 ORM，由 API 负责提交，不再在内部提前释放事务锁。

实际同步推送在外部 HTTP 调用期间持有备件锁，沿用 `PROCUREMENT_TIMEOUT_SEC`（默认 5 秒），会使同备件的其他订单及库存写入等待。HTTP 失败或格式错误保留 APPROVED，事务结束释放锁；本地测试服务器验证了真实请求和失败恢复，以及外部推送等待时最后收货读到旧状态、等锁后仍完成为 RECEIVED。

远端 HTTP 已成功而本地审计/提交失败时，数据库回滚无法撤销远端订单。本轮有明确失败演练；遇到这种不确定结果须先核对外部采购系统，不直接把发送失败当作“远端没收到”。持久化投递、远端去重、取消通知及失败定位属于后续跨系统迭代。沿用既有外部响应判定，没有新增自动重试或耗时上限承诺。

## 回归与复跑

测试使用真实 SQLite 和 PostgreSQL。通过 ORM 已实际读出的对象设置暂停/屏障，让另一事务先提交，不替换数据库结果或锁；避免 SQLite 未取完游标本身阻塞写入。断言最终状态、库存、累计到货、流水、成功快照、审批字段及审计，而非只看响应码。

```sh
cd backend
TEST_POSTGRESQL_URL=postgresql+psycopg2://user:password@127.0.0.1:5432/isolated_test \
  SCHEDULER_ENABLED=false python -m pytest \
  tests/postgresql/test_purchase_states.py tests/postgresql/test_purchase_push.py \
  tests/postgresql/test_receipt_replay.py tests/postgresql/test_stock_transactions.py -q
```

只使用隔离测试库。完整后端还需 PG_DUMP/PG_RESTORE 匹配数据库版本的客户端，详见迁移/恢复文档。GitHub Quality 运行后端、PG、前端检查，Compose 复验 nginx/PG 和已有浏览器场景。

过时绝对盘点、采购新建/自动补货精度金额及编号竞争、超量收货政策继续留待后续。这些指定模拟交错、HTTP 测试和 CI 不是生产容量或现场投运证明。代码回退不能恢复业务数据；遵循既有备份与独立恢复流程。
