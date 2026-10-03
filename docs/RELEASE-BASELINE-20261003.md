# 设备点检集成基线与验证

2026-10-03。本轮审查主分支 `8b4551808524b76c7b50c3425396bd5a265ba080` 到历史候选 `f6efc764fc166a003190925cc633b32600a51256` 的差异，并在该候选上补齐库存数量及恢复目标隔离修复。最终发布提交与远端检查见对应集成 PR；本文不使用尚未产生的提交号自引用。

## 纳入的能力

- PR #4–#5：真实 PostgreSQL 点检/验收并发、UUID 缺陷编号、健康度及事务回滚。
- PR #6：演示/正式配置分离、管理员初始化及五角色权限回归。
- PR #7：冻结的迁移基线、旧库预检、SQLite/PG 备份及独立恢复。
- PR #8–#9：按哈希锁安装、固定容器镜像、Compose 冷启动/浏览器验收、前端依赖与图表兼容。
- PR #10：库存出入库与采购收货共用备件锁、等锁后刷新及原子回滚。
- 本轮：有限非负两位小数、原始 Decimal 长尾精度检查、累计数量上限、前后端盘点归零；拒绝 libpq 会重解释的数据库名。

核心历史与迁移/交付/前端分别进行了独立只读审查。发现的恢复目标重定向与长尾小数绕过问题均先复现、补测试，再修复并独立复核。历史分支的内容统一纳入集成 PR，不需要重复逐条实现。

## 本地证据

| 检查 | 实际结果 |
|---|---|
| 首批库存边界回归 | 修复前 70 failed / 40 passed；修复后 110 passed |
| 长尾小数补充回归 | 修复前 18 failed；最终包含在完整后端验证中 |
| 恢复路由补充回归 | 修复前 7 failed；备份专项修复后 19 passed |
| 完整后端 `python -m pytest -q` | 362 passed、0 skipped，含真实 PostgreSQL 121 项 |
| API 面试演示 | status=passed，35 checks |
| 前端 `npm test` | 7 passed |
| TypeScript / Vite 生产构建 | 通过 |
| Chromium `npm run test:e2e` | 5 passed，新增归零页面/API/流水检查 |
| Ruff E9/F63/F7/F82 / git diff --check | 通过 |
| 最终独立复核 | 库存与恢复修复无剩余重要问题 |

本地 Python 3.12.14、Node 24.19.0、隔离 PostgreSQL 16。数据库测试使用随机 schema 和独立恢复库；浏览器测试使用隔离 SQLite 演示库与 Vite 代理。已有浏览器用例的标题提及 nginx/PostgreSQL，本地运行并不证明该部署组合；远端 Compose CI 使用实际 nginx/PostgreSQL 冷启动，应单独核对其提交与成功结果。远端 CI 使用 Python 3.11、Node 22。

复跑：按哈希锁安装开发依赖，在 backend 目录设置独立 TEST_POSTGRESQL_URL 及与服务器匹配的 PG_DUMP/PG_RESTORE 后运行 `python -m pytest -q`；运行 `python interview_demo.py --output <新的报告文件名>`。前端执行 `npm ci --no-audit --no-fund`、`npm test`、`npm run build`。Compose 浏览器流程见 [部署说明](REPRODUCIBLE-DEPLOYMENT.md)，测试数据必须独立于正式业务。

## 升级与边界

默认模式为 production，需要有效密钥、显式迁移后才能启动；固定演示账户只在 APP_MODE=demo 创建。正式初始化管理员须先迁移，非管理员用户目录调用会返回 403。新缺陷号为不透明 UUID 字符串，旧号保留。具体升级要求见 [运行配置](RUNTIME-SECURITY.md) 和 [迁移矩阵](DATABASE-MIGRATIONS.md)。

库存新增严格输入校验，负值、超范围、有效小数超两位或显式空数量返回 422；零 IN/OUT/收货及累计溢出返回 400，零盘点成功。恢复工具不支持含 `=` 或以 `postgres://`、`postgresql://` 开头的库名。无需本轮新增 schema 或历史数据改写。

部分收货重放幂等、取消/审批竞争、过时绝对盘点、采购创建/自动补货精度与金额边界、物料编号分配、外部可靠联动仍需后续迭代。既有 Python 弃用、前端大包警告和依赖审计边界保留；不把本轮结果称为无漏洞、生产容量或现场投运证明。数据库备份不含附件、密钥及全局角色，检查失败的恢复库不接业务流量。

代码回退不恢复业务数据，也不纠正历史库存/流水差异；迁移不提供破坏性自动降级。保留备份、附件与数据卷，按独立恢复验证后再切换连接。
