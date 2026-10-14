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
- [x] 新 API 数量/金额/删除后编号/并发及旧 0003 升级测试，确认真实 RED。
- [x] 实现 DTO/Decimal/原子计数和迁移契约，完整套件及两数据库迁移通过，保存提交。

### Task 2 · 共用自动补货与超量收货

Files: services/purchases.py、api/purchase_requests.py、scheduler.py、frontend/src/pages/PurchaseRequestList.tsx；同一新增测试文件/前端测试。
Interfaces: generate_low_stock(db,applicant)->{created,skipped}，调用方一次提交。
- [x] API/调度并发与重复、陈旧库存、建议/金额溢出跳过、合法继续、超收/合法重放 RED。
- [x] 共用服务/锁序/拒绝副作用/页面可见原因，实现后全套 backend、PostgreSQL、frontend tests/build/interview_demo，推送 PP-030 阶段。

### Task 3 · 不可变安全 outbox 与严格回执

Files: models/safety_outbox.py、integration/safety_client.py、api/tasks.py/defects.py（按实际必要）、tests/test_safety_delivery.py、tests/postgresql/test_safety_delivery.py。
Interfaces: mark_pending(db,d) 同缺陷事务；push_one(db,d)->bool；retry_pending(db,limit)->dict。
- [x] 真实 HTTP 故障/畸形 ACK、已接受后断线、Session 重启/内容变更、并发投递与本地失败 RED。
- [x] 保存/刷新/提交顺序、回执验证与受控错误，完整套件/前端构建/迁移验收后推送候选。

### Task 4 · 整批审查与发布

- [x] 接收端 PP-041 按独立计划完成；一次 fresh-context 整批两分支审查与冷恢复，Important 单次 RED→GREEN 修复，无重复审查。
- [ ] 接收端先发布，发送/采购再发布；固定候选及 main CI 通过；每项真实合并检查点/release/索引和最终摘要回写。

## 执行台账

当前只读核查/基线。插件 supporting-script resource 读取不可用，沿已版本化本计划与中央日志记录 brief/BASE/命令/结果；不读取或删除其他计划工作区。完整基线设备 306 passed/186 PostgreSQL skipped，安全 68 passed；第一条安全测试从根目录执行缺少 app 导入路径，改在 backend 按 CI 命令运行后通过，不计业务 RED。

Pre-flight: Task 1 提供编号/表/金额；Task 2 调用相同服务与锁序；Task 3 使用 Task 1 已创建 outbox，schema contract 必须包含两张新增表；接收 ACK 身份契约由 PP-041 提供，按接收端先部署。

## 采购实现阶段（2026-10-13 接续）

首次 48 个双数据库 API 回归 40 failed/8 passed，迁移旧头升级 1 failed；实现后目标采购/SQLite 迁移 66 passed。完整后端连真实 PostgreSQL 与同版本客户端 542 passed，原 PostgreSQL 客户端缺失失败均已排除。随后新增畸形 Unicode 编号后缀：先 2 failed、修复后 2 passed；最终整批完整套件将覆盖该新增用例。

前端既有 16 passed，TypeScript/Vite 构建通过；首次构建发现 autoGenerate 响应类型未同步 skipped，已按真实服务字段补齐。金额/编号/补货/超量收货已实现并保持身份重放；根目录与 backend 测试/import 路径错误仅作工具错误记录，不计业务 RED。无现场或跨库 exactly-once 声明。

Task 1/2: 实现及指定目标验证通过，生产阶段待提交；同批 outbox/接收端仍待实现，未合并。本计划最终闭合以全分支完整验证和中央签收为准。

## PP-040 发送阶段

真实 localhost HTTP/两个数据库首轮 30 failed/4 passed；本地 ACK 保存失败、未配置端点仍需冻存事件的附加回归 4 failed。初始失败提交 754e9b8c79c0df6c027f3f46f34a23861fa83692 已推送。实现后完整发送目标 38 passed，包含源头 API 提交前消息保存、空/畸形/身份错误/非200、响应丢失后新Session、内容变更、两个旧Session并发、数据库确认故障。网络对端仍为临时 HTTP 契约，真正两个应用协议验收待 PP-041 实现。

Ruling: 已存 SYNCED 但无有效隐患引用不能当成功，允许重核 — 原实现会把空回执永久跳过 — 历史没有原消息时只能冻结当前可核对内容，接收端冲突需人工处理；正常已确认历史不重推。ACK 保存失败返回非成功且旧持久消息保留，计数只代表已提交尝试，不保证等于全部网络次数。

## 真正两应用与完整设备验收

发送实现后完整设备后端582 passed（SQLite与真实PostgreSQL，无环境跳过），前端16 passed与构建通过。真正配对测试最初仅缺 ORM 注册，修正harness后旧接收端e5e62e7实跑2 failed：正常回执缺身份、丢回执后缺原子收据。新接收端56f494a527dd71820400fc57cad7f6fdf35013f9实跑2 passed，两个独立应用/数据库/进程及真实HTTP代理；对端提交后只丢第一ACK，发送进程退出、源内容/设备改名后重启，仍发原事件且只有一张隐患/收据。

新增 safety_contract CI 固定配对接收代码；普通无配置测试可跳过配对，本地最终全套和独立CI显式提供根目录，不能将跳过写成对接通过。接收端候选完整113 passed/1 intentional skip，最后整批审查与发布仍待。


## 整批审查与单次 Important 修正轮 · 2026-10-14

一次 fresh-context 整批审查固定设备8047049..57816f8、安全e5e62e7..56f494a；Critical 0 / Important 3 / Minor 3。设备审查者目标88 passed；接收45 passed/1刻意跳过；另有父代理完整584/113通过。不是再次审查。R1安全编号由接收、人工、检查三个入口统一事务内分配；R2采购全请求递归处理非有限非法输入；R3扫描/页面/重推采用同一引用有效性。设备新增回归首轮18 failed/6 passed，其中17项为真实业务失败，1项为测试试图写入PG varchar(50)的51字非法历史引用；该状态在PG不可能，已改为两库均验证超长ACK拒绝，未将夹具失败当业务RED；安全回归2 failed/2 passed（PG的人工、检查入口确实500）。失败提交设备e17b69d、安全9752f18已推送。

Ruling R1（接受 Important）：新增独立日序号表，三个隐患入口共享分配，旧编号按最大合法后缀接续，不依赖ID/条数；代价是额外小表和同日编号事务串行，新老写入进程应在维护窗口切换，不允许旧进程继续用count编号。
Ruling R2（接受 Important）：整个创建DTO递归替换非有限坏值为可序列化非法值，错误仍422且无写入；代价为按请求结构递归遍历，合法数值语义保持。
Ruling R3（接受 Important）：按主键分段读取历史状态、以同一Python有效性函数筛选待投递，正常历史不占limit也不发送；页面匹配同一空白/控制字符/Unicode码点上限。代价是恢复扫描需要读历史成功行，且优先顺序采用ID升序；容量/性能未验收。

Minor全部延期并明确保留：M1接收升级备份/维护窗口操作文档未补；M2采购页面无独立剩余数量展示（上限已正确）；M3安全SKIPPED/失败原因未进入正常DefectResponse/读取界面（库中有原因，手动重试会展示）。依执行计划只修复Important的一轮要求，不将其漏记或称全部规范完成。

Declined-to-judge：现场有效性、容量/性能、真实第三方运行、任意数据库篡改完整恢复、跨库exactly-once均超范围，接受此边界；成本是本次通过只证明版本化原型与明确故障契约。历史无原消息只能核对已存投影，以及ACK保存失败计数只代表已提交尝试，原Ruling继续有效。


## 最终候选验证

Important单轮修正后完整设备后端608 passed（SQLite、真实PostgreSQL16、同版本备份客户端、真正两应用2项均执行，无环境跳过）；前端18 passed及TypeScript/Vite构建，ruff/pip check/interview_demo通过。完整命令从backend执行：SCHEDULER_ENABLED=false TEST_POSTGRESQL_URL=<隔离测试库> PG_DUMP=<同版客户端> PG_RESTORE=<同版客户端> SAFETY_PEER_ROOT=<固定接收代码> python -m pytest tests -q。PG超长历史引用夹具已改为真实可发生的超长ACK拒绝，不再把数据库本已阻止的非法状态作为恢复前提。

接收端PR #4已先合并为6f12503f00fdd485a55e737f17d08e8ff8b833f0，候选与main三项CI成功，合并树与本地受测6ff90ca完全一致；设备配对CI固定该实际发布SHA。唯一审查已闭合Important，无复审；三项Minor仍延期。设备候选CI与合并/main CI待执行。


CI范围核对：发送双数据库用例位于根tests/test_safety_delivery.py；原PG作业只选tests/postgresql会遗漏它的PG参数。PG作业已显式加入该文件，避免未来只测SQLite。完整本地608已包含该范围，代码未另改，不需要重复完整本地测试；新固定候选需重新通过全部CI。
