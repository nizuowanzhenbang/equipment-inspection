# PP-030 采购与补货边界

用户授权自主扩量迭代；基线 8047049bb3158959172edc5a7148dd5f35be4217。已有库存/收货身份重放不重做。实际基线 306 passed/186 PostgreSQL skipped，正在准备真实 PostgreSQL 验证。

交付四个独立单元：

1. 新建数量使用既有 InventoryDecimal：有限、0 < qty <= 99999999.99、最多两位小数；urgency 仅 NORMAL/URGENT。字段错误 422，整请求无写入。数量乘单价使用 Decimal，以 ROUND_HALF_UP 保留两位金额，0 <= amount <= 9999999999.99；价格/金额无法表示时 409，无部分订单或审计。返回数值兼容现有 API。
2. 采购编号通过新 purchase_number_sequences 每 UTC 日原子分配，旧日内编号按最大有效后缀初始化，不依赖记录数量；删除订单后不复用已分配序号。同日不同物料并发创建均有唯一编号。分配与订单在同一事务，失败不消耗可见计数。
3. API 和调度器调用同一 generate_low_stock(db, applicant) 服务。先按 id 顺序锁定候选物料，刷新后再判库存/阈值/活动订单，避免并发生成或陈旧快照；先获取物料锁再分配编号，避免跨物料/编号的锁顺序倒置。建议数量仍为 max(2*min-stock,min)，保持 SUBMITTED 与现有来源。范围/金额错误的物料不截断，返回 skipped 原因；有效物料继续处理。API 与调度器重复执行不多建活动建议。
4. 首次收货累计不可超过原申请 qty，超量 409 且库存/流水/收货身份不变；合法多批到货及已提交身份的原结果重放保持。额外到货需另行登记/采购处理，不自动扩大原订单。页面显示剩余数量/补货跳过原因；有待确认身份时仍允许原身份重试，不按最新剩余量阻止恢复。

沿现有 SQLite/PostgreSQL、FastAPI、SQLAlchemy、Alembic 和 React；不引入框架。增加 0004_reliability_state 迁移与冻结双数据库结构契约，保持旧 0001/0002/0003 和无版本合法数据库可升级；结构漂移拒绝且原数据不改。为同批安全联动同时准备独立 safety_outbox 表，不修改旧 Defect 列。

验收：真实 JWT/API/数据库副作用、SQLite 与 PostgreSQL 竞争、API/调度器交错、编号删除/跨日、金额边界/精度、超收/重放、迁移重复/失败/漂移，既有完整后端/前端测试、构建、interview_demo 与全部 GitHub backend/postgresql/frontend 检查。
