# 面试演示：一次命令验证点检到验收

## 运行

需要 Python 3.11，使用独立虚拟环境。在仓库目录执行：

```sh
cd backend
python -m pip install -r requirements.txt -r requirements-dev.txt
python interview_demo.py --output interview-evidence.json
```

成功时打印 `PASS`、检查数量与报告路径，退出码为 0。省略 `--output` 会直接打印 JSON。已有报告不会被覆盖，复跑时换一个文件名。JSON 中文以 UTF-8 保存，可用编辑器打开。

脚本启动一次性 FastAPI TestClient，执行真实的启动建表、默认演示账户密码校验、JWT 登录和业务 API；没有 mock 鉴权或直接插入业务记录。每次只创建一台模拟 B 级给水泵、一条路线、一个测点和一项任务。

脚本在导入配置前强制使用临时 SQLite，关闭调度器、外部安全/采购系统联动，使用临时上传目录和随机 JWT 密钥。调用方的 DATABASE_URL、UPLOAD_DIR 等配置不会用于演示。结束后销毁临时数据库；它不会往正在运行的服务添加演示记录，也不启动浏览器页面。报告只保存验证结果，不包含密码或登录令牌。

## 五分钟讲解路线

| 时间 | 展示内容 | 技术解释 |
| --- | --- | --- |
| 0–1 分钟 | 运行命令并打开报告，确认 `status: passed` | 所有结果来自这次实际 API 调用；CI 也运行同一命令 |
| 1–2 分钟 | B 级设备 SEVERE 记录自动生成 MAJOR 缺陷，健康度 100 → 92，设备进入 MAINTENANCE | 业务规则如何驱动跨表状态变化 |
| 2–3 分钟 | 同内容重传得到相同记录和缺陷 ID；修改内容返回 409；健康度仍是 92 | 业务幂等、冲突语义和服务端事务；网络传输故障本身由其他测试覆盖 |
| 3–4 分钟 | supervisor 派工、repairman 维修、验收驳回后重修、最终关闭 | 真实角色权限、状态机、拒绝路径；VIEWER 录入和 INSPECTOR 派工均返回 403 |
| 4–5 分钟 | 设备恢复 RUNNING，健康度 98；重复验收返回 400；审计有派工、驳回、通过记录 | 关闭幂等边界、避免重复回弹、可以追溯的业务证据 |

## 结果读法

- `checks`：每个检查的名称、实际值、预期值和是否通过。失败立即退出非零，不输出新的成功报告。
- `result.health_scores`：初始、首次异常、重传后、最终验收后的四个值；预期 `[100, 92, 92, 98]`。
- `result.record_count` / `defect_count`：重传及冲突后的记录和缺陷数，各为 1。
- `result.audit_actions`：实际读取到的缺陷审计动作。
- `generated_at`：本次执行时间；属于模拟演示证据，不是现场运行记录。

## 相关验证与限制

```sh
python -m pytest tests/test_interview_demo.py -v
python -m pytest tests/test_record_replay.py -v
```

第一组用独立子进程连续执行两次演示，并验证已有数据库不被触碰、已有报告不被覆盖。第二组验证重传、并发和唯一性约束。前端离线队列另在 `frontend` 执行 `npm test`。

本命令验证 API 业务闭环，未验证浏览器点击、Service Worker、Docker、PostgreSQL 或外部系统交付；不能把它描述为完整浏览器 E2E 或生产性能测试。需要 UI 展示时按 README 单独启动演示环境，使用 [离线点检演示说明](INTERVIEW.md)。

## 简历补充

> 为设备点检项目建立可重复运行的 API 场景演示，使用真实 JWT 和分角色调用验证异常建单、重传幂等、维修验收及审计链路；以隔离数据库避免污染既有数据，并把演示纳入 CI 作为可复核的交付证据。
