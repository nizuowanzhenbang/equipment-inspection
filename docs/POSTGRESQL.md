# PostgreSQL 点检事务回归

这一轮将设备点检主项目的数据库可靠性验证从 SQLite 扩展到真实 PostgreSQL。测试使用模拟数据和实际 SQL 事务；不模拟数据库锁或返回结果。

## 已修复的问题

1. 点检和手动上报使用“当天缺陷数 + 1”分配编号。并发请求可能取得相同编号，删除早期记录也可能导致重用现有编号，触发唯一约束并返回 500。
2. 不同任务同时读取同一设备的健康度后，旧的 Python 读改写可能相互覆盖。例如两条一般异常都读取 100，结果只有 97；现在按事务内原子 UPDATE 累计为 94。
3. 原表达式将 0 当成缺省值 100，使零分设备产生新异常后变成 97。现在只有 NULL 使用缺省 100，低分扣减下限为 0。

运行时新缺陷编号为 `DF-YYYYMMDD-<32 位 UUID>`，长度 44，仍由数据库唯一索引兜底。UUID 大幅降低碰撞风险，不承诺绝对不会碰撞或单号连续。已有编号不改写；种子数据显式序号仍兼容。外部系统应将编号视为不透明字符串，不解析最后四位或用它排序。前端、导出和工作票仍引用完整编号。

## 本地执行

准备一个专用 PostgreSQL 测试数据库，用户需具备该库创建 schema 的权限。不要使用生产连接；本测试不读取应用的 `DATABASE_URL` 作为目标。

在仓库根目录安装应用与测试依赖：

```sh
python -m pip install -r backend/requirements.txt -r backend/requirements-dev.txt -r backend/requirements-postgres.txt
```

以下连接为本地测试示例，按自己创建的隔离库配置：

```powershell
$env:TEST_POSTGRESQL_URL = 'postgresql+psycopg2://portfolio_test:test_password@127.0.0.1:5432/portfolio_test'
$env:SCHEDULER_ENABLED = 'false'
cd backend
python -m pytest tests/postgresql -q --junitxml=postgresql-results.xml
```

Linux / CI 对应环境变量：

```sh
export TEST_POSTGRESQL_URL='postgresql+psycopg2://portfolio_test:test_password@127.0.0.1:5432/portfolio_test'
export SCHEDULER_ENABLED=false
cd backend
python -m pytest tests/postgresql -q --junitxml=postgresql-results.xml
```

运行 `python -m pytest tests -q` 可同时执行原有测试。未提供 `TEST_POSTGRESQL_URL` 时 PostgreSQL 测试显示 skipped；提供非法类型、缺少驱动或数据库不可达时失败，不伪装成通过。

每个用例建立随机 `ei_test_<UUID>` schema，将其设为独立 search_path，在其中建立表、枚举和测试约束。结束后只删除这个 schema；连接池随之释放。不要并行运行同一进程中的测试，它们修改全局 FastAPI 依赖覆盖。进程被强制终止时可能留下测试 schema，需在专用测试库核对后清理。

## 覆盖的场景

- 同任务同测点并发提交相同内容：两个成功响应返回原记录，只有一份记录、一份缺陷和一次扣分。
- 并发提交不同内容：一个成功，一个 409，保留成功写入的原内容。
- 换账户重放返回 409；只读账户返回 403。使用真实用户查询和 JWT 鉴权依赖。
- 不同任务检查同一设备：缺陷编号不同，两次扣分累积，两个任务均正确完成。
- 两次手动上报，或手动上报与点检同时发生：两份缺陷都保存，不因计数分配撞号。
- 0、低分与 NULL：保留零分和下限，只对 NULL 采用缺省值。
- 缺陷插入阶段或最后任务提交阶段被数据库约束拒绝：记录、缺陷、健康度、任务状态整体回滚；解除故障后可重新提交。
- 旧库补唯一索引可以重复执行；数据库继续拒绝重复任务测点记录。
- 旧库已有重复记录时，初始化明确拒绝且不删除数据。

并发测试通过 mapper 事件屏障让两个真实事务先读取数据，再同时插入缺陷，从而稳定覆盖原有竞争窗口。没有替换 SQL 返回值或业务逻辑。

## CI 和边界

Quality checks 中新增 `postgresql` 作业，使用 PostgreSQL 16 服务、Python 3.11 和独立测试账户，输出 `postgresql-regression-results` artifact。原来的 SQLite、前端构建/离线测试和面试演示继续执行。

这些用例覆盖点检提交及新建缺陷路径，不等于所有接口支持任意并发。验收恢复健康度、其他业务编号、旧数据库全面版本迁移、多实例启动、故障切换和生产压测仍需单独设计和验证。原子扣分与记录、缺陷、任务在同一数据库事务内，不代表跨系统 exactly-once。
