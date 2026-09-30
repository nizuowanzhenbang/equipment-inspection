# 数据库备份与独立恢复

在 `backend` 目录执行。工具不读取应用默认配置，必须显式提供含连接 URL 的环境变量名称。凭证不进入工具参数或清单；子进程通过环境变量连接 PostgreSQL。请使用受控终端或密钥管理服务设置环境变量，避免把密码写进终端历史。

```powershell
# 事先设置 SOURCE_DATABASE_URL 和 RESTORE_DATABASE_URL。
python -m app.backup backup C:\backups\inspection-20260930.dump --url-env SOURCE_DATABASE_URL
python -m app.backup restore C:\backups\inspection-20260930.dump --url-env RESTORE_DATABASE_URL
```

Linux 同样使用 `python -m app.backup backup /backups/inspection.dump --url-env SOURCE_DATABASE_URL`。SQLite URL 示例 `sqlite:///C:/restore/new.db`；PostgreSQL 示例 `postgresql+psycopg2://user:password@localhost:5432/new_restore_db`，后者仅展示格式，实际凭证放在环境变量中。

每次备份生成指定文件及同目录 `<文件名>.manifest.json`。两者均拒绝覆盖。清单包含格式版本、数据库类型、UTC 时间、源库标识、SHA256 和表行数；源库标识不含密码，但包含库名/地址或 SQLite 路径。备份含业务数据，应限制目录访问并按数据保留策略管理。SHA256 能发现损坏，但不能证明来源可信；恢复仅使用可信备份和清单。

SQLite 通过只读连接和官方 backup API 获取一致快照，再从生成的备份计算行数、执行 integrity_check 和 foreign_key_check。源文件不存在时拒绝创建。恢复目标文件必须不存在；先校验散列、数据完整性和行数，再独占创建目标文件。失败时清理本次创建的目标。

PostgreSQL 需要与服务器兼容的 `pg_dump`/`pg_restore`（测试使用 PostgreSQL 16）。默认从 PATH 查找，也可用环境变量 `PG_DUMP` / `PG_RESTORE` 指定完整可执行文件路径。来源连接在 REPEATABLE READ 只读事务中导出快照；表行数和 `pg_dump --snapshot` 使用同一个快照。归档为 custom 格式。

PostgreSQL URL 必须显式填写 host、port、user、database。除 `PG_DUMP` / `PG_RESTORE` 工具路径外，连接进程不得继承其他 `PG*` 环境设置；工具会提前拒绝，避免 Python 的预检连接和命令行恢复连接使用不同的环境默认值。SSL 配置只通过 URL 中受支持的 sslmode/sslcert/sslkey/sslrootcert 提供。

PostgreSQL 恢复必须显式指向事先新建的独立空库，建议 `CREATE DATABASE <唯一恢复库名> TEMPLATE template0`。工具拒绝源库、已有表/序列/视图、用户类型、函数、非默认 schema 或扩展的目标；只允许默认 public schema 与 plpgsql。请在维护窗口独占该目标库，禁止应用或其他管理员同时写入/执行 DDL。恢复采用 `--single-transaction --exit-on-error --no-owner --no-privileges`，归档内 SQL 失败时整个恢复事务回滚。完成后重新核对表行数和已验证外键。若恢复提交后清单行数不符，工具失败退出但保留独立目标供检查；不会自动删除数据库或回滚已提交的恢复。切勿让应用连接一个检查失败的目标。

工具成功退出仅代表数据库检查通过。将应用配置指向恢复库前，在隔离环境执行 `python -m app.migrate check`，必要时按迁移文档先升级，然后验证登录、点检记录、缺陷派工、修复、验收以及数据数量。记录备份清单、验收结果和切换时间后再安排业务切换。回滚代码不能替代恢复旧版数据库备份。

范围：不备份 PostgreSQL 全局角色、所有权/授权、对象存储附件、部署密钥或其他外部系统。PostgreSQL 表计数针对普通用户表（含分区表），不作为视图、外部表或外部附件的业务校验。包含自定义扩展/外部服务的库需额外制定恢复流程。不要把生成的备份或含凭证环境文件提交到 Git。

测试：`pytest tests/test_backup.py` 验证 SQLite；显式设置 `TEST_POSTGRESQL_URL` 后运行 `pytest tests/postgresql/test_backup_restore.py`，测试帐号需 CREATEDB 权限，只创建和清理 `ei_backup_<随机值>` 独立测试库。未设置时 PostgreSQL 测试跳过，不能据此宣称 PostgreSQL 验收通过。
