# Database Recovery Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development for the independent backup component; coordinator implements migration and integration. Read the spec first.

**Goal:** 可验证的数据库升级、隔离恢复及恢复后业务验收。

**Architecture:** Alembic 冻结基线与预检；独立备份工具和恢复校验；生产启动只验证版本。

**Tech Stack:** Python 3.11, SQLAlchemy 2, Alembic, SQLite, PostgreSQL 16.

**Spec:** `docs/superpowers/specs/2026-09-30-database-recovery.md`

## Global constraints

不覆盖旧数据库/备份；连接密码不进命令行或报告；所有测试写入仅限测试临时文件/独立库。旧迁移不依赖可变 ORM。

## Review focus

1. 结构不匹配但版本标记正确：check 仍拒绝。
2. SQLite DDL 与 PG 枚举：升级失败不得假标成功。
3. 备份时并发写入：清单和备份必须属于同一快照。
4. 恢复参数指向旧目标：在任何写操作前拒绝。
5. 启动、seed、bootstrap 和 interview_demo：新入口须兼容既有主流程。

## Task 1 — migration (coordinator)

Files: `app/migrate.py`, `app/schema_contract.py`, `migrations/`, `alembic.ini`, tests.

- [x] Write/run red tests for supported schemas, duplicate records and drift.
- [x] Freeze baseline DDL and SQLite/PG contracts; implement `upgrade_database(engine)` and `check_database(engine)`.
- [x] Implement production check, demo/seed upgrade and bootstrap precondition; update tests.
- [x] Verify SQLite/PG upgrades and old test compatibility.

## Task 2 — backup (independent implementer)

Files owned: `app/backup.py`, `tests/test_backup.py`, `tests/postgresql/test_backup_restore.py`, `docs/BACKUP-RESTORE.md`.

Interfaces: `backup_database(url: str, output: Path) -> dict`, `restore_database(archive: Path, target_url: str) -> dict`; CLI documented by implementer. No import dependency on Task 1.

- [x] Write/run red tests for roundtrip, occupied target, overwritten output and corrupted archive.
- [x] Implement SQLite backup API and PG snapshot pg_dump/transactional pg_restore; verify counts and referential integrity.
- [x] Test on genuinely separate PG databases when an explicit test URL is provided; preserve no caller data.
- [x] Document limitations and commands. Coordinator adds restored API flow and final CI configuration.

## Task 3 — integration and delivery (coordinator)

- [x] Restore application fixture, validate data and execute subsequent API business workflow.
- [ ] Run full suite and CI with PG client tools available; independent review, address important findings.
- [ ] Commit, push PR based on #6, record actual CI and recovery evidence in outputs.

## Ledger

Ruling: 继承用户自主决策授权，使用独立功能分支；本轮不触碰用户现有业务库，迁移/恢复在测试库验证后交付工具。

Ruling: 首管理员命令要求先显式迁移，避免两个独立建表入口；上一轮 bootstrap-only 库仍有升级测试。

Review: 已修复 SQLite 表达式/排序索引遗漏、PG serial 错误引用、缺失 SQLite 源与输出重合、PG 环境默认导致预检/恢复目标不一致四项 Important，独立复核无阻塞。

Next: 用户追加要求“完成后进入下一轮”，本轮推送与 CI 通过后继续可重复部署及依赖维护。
