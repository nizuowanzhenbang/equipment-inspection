# 可重复部署与请求定位

## 本地合成演示

需要 Docker Engine 和 Compose v2（支持 `up --wait`）。在仓库根目录：

```sh
docker compose -p equipment-demo up --build --detach --wait
```

打开 http://127.0.0.1:8080，用 `admin / admin123` 登录；只读账户为 `viewer / viewer123`。这些是公开演示凭证，不能用于正式环境。默认只监听本机端口；数据库不暴露宿主端口，上传使用持久化本地 volume，调度器默认关闭。首次启动自动迁移并建立演示账户。

```sh
curl --fail http://127.0.0.1:8003/health
curl --fail http://127.0.0.1:8003/ready
docker compose -p equipment-demo logs backend
docker compose -p equipment-demo down
```

`down` 默认保留数据卷。不要给已有数据的项目加 `--volumes`；先按 [备份恢复](BACKUP-RESTORE.md) 验证备份。保持项目名不变才能复用同一数据卷；旧版默认项目名的用户应先查看 `docker compose ls`，不要误以为换项目名后旧数据丢失。

## 可选服务

调度器需要时设置 `SCHEDULER_ENABLED=true` 后重新创建容器。S3 或 MinIO 使用显式外部服务：设置 `STORAGE_BACKEND=s3`、`S3_ENDPOINT`、`S3_BUCKET`、`S3_ACCESS_KEY`、`S3_SECRET_KEY`。端点必须能从容器内访问，宿主机服务可使用适用平台的 `host.docker.internal` 地址。凭证放未跟踪的 `.env`，不要提交。

本轮无法从公共 registry 核实旧 `minio/minio` 镜像，不再自动启动内置 MinIO；保留应用的 S3 实现，不删除既有对象存储卷。此处仅验收默认本地存储，外部 S3 服务另行验收。

## 锁定与更新

- `requirements.txt` 是直接依赖范围；`requirements.lock` 是 Python 3.11 跨平台运行依赖及 SHA256，包含 PostgreSQL 驱动。
- `requirements-dev.lock` 包含相同运行版本及测试工具。CI 和镜像使用 `--require-hashes`，不再随安装时间解析最新版本。
- 前端使用 `package-lock.json` 和 `npm ci`。Python、Node、nginx、PostgreSQL 镜像使用 registry 返回的 digest；记录见 `dependency-audits/images-20260930.json`。
- 固定版本并不等于永久安全；更新必须重新运行数据库测试、构建及容器浏览器验收。

```sh
python -m pip install --require-hashes -r backend/requirements-dev.lock
# 有意升级时，用 uv 重新解析并审查 lock diff；不使用 --upgrade 则沿用现有锁定版本。
uv pip compile backend/requirements.txt backend/requirements-postgres.txt --generate-hashes --universal --python-version 3.11 --no-header --no-annotate -o backend/requirements.lock
uv pip compile backend/requirements.txt backend/requirements-postgres.txt backend/requirements-dev.txt -c backend/requirements.lock --generate-hashes --universal --python-version 3.11 --no-header --no-annotate -o backend/requirements-dev.lock
```

2026-09-30 扫描：兼容更新使 npm audit 从 9 个受影响包降至 5 个（4 moderate、1 high）；剩余 ECharts、React Router、Vite/esbuild 需要单独的大版本兼容验证。Python 扫描仅报告 `ecdsa 0.19.2` 的同一侧信道公告两次，没有上游修复版；当前 JWT 配置为 HS256，不能据此声称其他算法使用安全。原始扫描保存在 `dependency-audits/`。本轮未扫描基础镜像 OS 包，也未宣称漏洞清零。

## 就绪与日志

`/health` 仅表明进程存活；`/ready` 检查数据库连接和迁移 HEAD，失败返回通用 503，完整 schema 校验仍在启动时执行。探针沿用数据库驱动及连接配置，未独立设置连接或查询超时，没有承诺探针耗时上限；这不是负载/SLA 测试。

每个 HTTP 响应携带 `X-Request-ID`。日志记录 ID、方法、路由模板、状态、毫秒耗时，不记录请求体、查询字符串或原始异常；请求 ID 长度最多 64，非法输入生成 UUID。ID 是定位字段，不是可信身份。

手动启动也需 `uvicorn app.main:app --port 8003 --no-access-log`；否则服务器默认访问日志仍会包含查询字符串。应用对 Uvicorn WebSocket 握手日志另作过滤。演示 nginx 关闭默认 access/error 请求日志以避免 WebSocket 查询令牌泄露，诊断依赖后端脱敏日志、HTTP 状态和容器健康；代价是缺少 nginx 请求错误详情。日志策略不覆盖外部反向代理自定义日志或第三方服务。

## 浏览器验收与边界

GitHub `Compose browser acceptance` 使用唯一项目名和新数据卷，构建镜像、等待就绪，再使用 Chromium 真正登录并从设备页面读取通过 API 创建的合成设备；另用真实 HTTP 验证匿名 401 和只读用户写入 403。没有请求 mock。失败时保留 trace/截图，成功也保留设备页截图；产物保留 14 天。最后只删除该次 CI 项目的临时资源。

本地容器已启动时可运行：

```sh
cd frontend
npm ci
npx playwright install chromium
npm run test:e2e
```

只在可丢弃演示库执行：测试会新增合成设备。它是核心页面与权限冒烟，不是全部业务浏览器 E2E，也不是生产可用性、外部集成或性能验收。本轮开发机没有 Docker，容器结论以 GitHub CI 为准。

后续记录：2026-10-01前端主要依赖升级及扫描结果见 [前端升级](FRONTEND-UPGRADE.md)，上文2026-09-30扫描作为历史基线保留。
