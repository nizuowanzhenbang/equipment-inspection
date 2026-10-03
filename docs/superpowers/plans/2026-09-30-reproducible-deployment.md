# Reproducible Deployment Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development for bounded observability work; coordinator owns dependency locks, containers, E2E and final integration.

**Goal:** 从已验证依赖冷启动应用，并提供就绪和请求定位证据。

**Architecture:** 哈希锁定依赖、digest 固定镜像、独立 Compose CI 与 Chromium；简单中间件和轻量就绪探针。

**Tech Stack:** Python 3.11, FastAPI, PostgreSQL 16, React/TypeScript, Node 22, Playwright, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-09-30-reproducible-deployment.md`

## Global constraints

不修改真实部署或生产卷；不记录凭证；当前本地没有 Docker，容器验收以远程 CI 为准。

## Tasks

- [x] Observability: app/observability.py + main.py + tests/test_observability.py；先红后绿。/ready 数据库与版本故障 503，无异常细节；X-Request-ID 输入限长/限字符，无效生成 UUID；日志不含查询参数或body。
- [x] Coordinator: 解析并冻结当前可兼容依赖，生成 hashes locks，Docker使用锁；frontend npm ci；扫描与记录漏洞。
- [x] Coordinator: 固定镜像digest、完善compose就绪/可选存储与启动文档；CI独立Compose项目从空volume启动。
- [x] Coordinator: Chromium登录和页面设备验证，401/403权限场景通过真实HTTP核对；保存失败trace与截图。
- [ ] Final: 全量测试、独立审查、提交PR，等待含Compose冷启动的最终CI结果。

## Ledger

Ruling: 将 MinIO 从默认演示依赖改为显式外部服务，默认本地存储；保留原有 S3 实现，通过文档显式启用。

Ruling: Docker Hub 的 minio/minio 元数据返回 404、manifest 返回 401，无法核实可拉取 digest；本轮不保留未经验证的内置镜像，原有 S3 实现和配置接口保留。已有 MinIO volume 不删除，需自行连接已验证外部服务；代价是对象存储不再一条命令随演示启动。

## Execution evidence

- Observability: 18 focused regressions passed after RED, including real Uvicorn accepted/rejected WebSocket handshakes for two protocol implementations. Review identified the server WebSocket log leak; fixed with logger/handler filtering and no raw nginx request logs.
- Dependency locks: installed into a new .venv-locked with hash checking; runtime/dev locks share identical runtime versions. Frontend npm ci, build, 5 offline tests and 2 Playwright test collection passed.
- Review: dependency/container/browser changes have no Important findings; known audit findings explicitly retained for a separate compatibility upgrade.
- Ruling: suppress nginx request/error logs and protocol DEBUG details to prevent query credentials reaching stored logs; backend safe request logs remain. Cost: reduced proxy-specific diagnostics.
- Initial full local run had 47 PostgreSQL setup errors because the isolated service was stopped; restarted the same isolated instance, then reran with readiness precheck. Final run and remote Compose evidence pending.

Final local evidence: 209 passed, 0 skipped (47 real PostgreSQL), 136.56s; independent final review clear. Remote Compose acceptance pending PR CI.
