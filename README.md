# 电厂设备的数字工长 · 设备点检与缺陷管理系统

## 求职展示更新：可靠离线点检

同一账户、同一任务测点、同一内容重传可返回原记录；内容冲突返回 409 并保留原数据。数据库唯一索引与事务锁防止重复入账；离线队列绑定录入账户，并将冲突标记为待核对。

[设计取舍、五分钟演示与面试追问](docs/INTERVIEW.md) · [自动化回归用例](backend/tests/test_record_replay.py)

**面试前一条命令自检：** 安装后端应用和开发依赖后，在 `backend` 执行 `python interview_demo.py --output interview-evidence.json`。脚本在临时数据库中使用真实登录与 API，验证点检异常、重传去重、冲突拒绝、派工、检修、驳回重修、验收关闭和审计日志。[运行方式与讲解路线](docs/DEMO.md)

> ⚙️ 电厂里上千台设备从锅炉到冷却塔，关键设备一停 = 整个机组停。但巡检全靠纸本子、口头交代——谁该巡哪台、几点巡、漏巡了没人盯；发现的小问题（轴温偏高、阀门内漏）没传到检修工那里就忘了；等小问题熬成大故障，已经晚了。

**这套系统把电厂上千台设备从"巡 → 修 → 验"串成一条数字闭环**：手机扫设备上的 QR 码就开点检，录入异常自动按设备等级（A/B/C）开缺陷工单；派工、检修、验收走完整状态机，每一步都有人、有时间、有签名；备件领用同步扣库存；`CRITICAL` 缺陷自动推到[安全管理系统](https://github.com/nizuowanzhenbang/plant-safety)立项整改。点检员在矿区/汽机房没信号？离线照样干，回到办公区自动同步。

> ⚠️ **免责声明**：本系统是 **厂内运维管理工具**，不能替代两票（工作票/操作票）的纸质归档（即便系统支持电子签名也建议保留纸质副本作为合规依据）。

---

## ⚡ 30 秒看明白你能用它做什么

| 你是谁 | 它帮你做什么 |
|---|---|
| 🧰 设备主管 | 派工、验收、看健康度倒序榜、决定哪台设备进检修 |
| 👷 点检员 | 手机扫 QR → 录测点 → 上传照片，异常当场建缺陷；离线也能点 |
| 🔧 维修工 | 接派工 → 开始检修 → 提交修复，自动联动备件领用 |
| 📦 仓管 | 看低库存预警、做出入库流水、低于安全库存自动建采购申请 |
| 🏢 设备部主任 | 大屏一眼看完今天的点检完成率、未结缺陷、SLA 达成率 |

---

## ✨ 核心场景

### 📱 手机扫码点检：3 秒进入录入页
设备上贴一张 QR 码，点检员手机打开 PWA → 扫码 → 自动拉出该设备的点检项 → 录数 → 拍照 → 提交。不用记编号、不用翻菜单。

> 💡 **离线也能干**：地下汽机房没信号？记录暂存浏览器 IndexedDB，回到办公区自动同步上传。

### 🔁 缺陷工单闭环：从异常到关闭，谁干的、几点干的、签了字
```
点检异常 → NEW（自动建单）→ ASSIGNED（派工）→ IN_REPAIR（开修）→ REPAIRED（提交）→ VERIFIED（验收关闭）
                                                                          ↓ 不通过
                                                                       回到 IN_REPAIR
```

- **设备等级 × 测点异常** = 自动决定缺陷严重度
  | 设备等级 | ABNORMAL | SEVERE |
  |---|---|---|
  | A（关键） | MAJOR | CRITICAL |
  | B（重要） | MINOR | MAJOR |
  | C（一般） | MINOR | MAJOR |

- **SLA 自动盯**：CRITICAL 4 小时 / MAJOR 24 小时 / MINOR 72 小时，超期飘红 `OVERDUE`
- **健康度算法**：缺陷扣分（CRITICAL -15、MAJOR -8、MINOR -3），验收回弹，可用率一目了然

### ✍️ 两票电子签名：工作票 / 操作票走完闭环
- **工作票** `WT-YYYYMMDD-NNNN`：第一种 / 第二种 / 紧急抢修
  起草 → 签发（设备主管）→ 许可（许可人）→ 开工 → 终结 → 归档
- **操作票** `OT-YYYYMMDD-NNNN`：停电 / 送电 / 倒闸
  审核 → 批准 → 逐步执行（每步记录 PASS/FAIL）→ 完成
- 每个签字节点 **HMAC-SHA256 二次密码**，签名链可一键重算验签
- 工作票"许可开工"自动转设备 `MAINTENANCE`，"归档"且无其它在工票自动恢复 `RUNNING`
- 工作票详情可一键 A4 排版打印（浏览器原生 print 即出 PDF）

### 🔮 预测性维护：哪台设备最该重点关注
综合风险分 = 缺陷数(30%) + CRITICAL 数(25%) + 点检异常(15%) + 健康度衰减(20%) + 设备等级加成 + 状态加成。给每台设备打 0–100 风险分 + 失效概率 + 处置建议，散点图直接看出 Top 30 重点设备。

### 📦 备件闭环 → 采购联动
- 缺陷 / 工作票 关联备件领用，出库自动扣库存
- `stock_qty < min_qty` 列表/Dashboard 自动标红
- **低库存自动批量建采购申请** → 推送到[燃料/物资采购系统](https://github.com/nizuowanzhenbang/fuel-procurement) → 到货后自动入库（StockMovement IN）

### 🔌 联动安全管理系统
`CRITICAL` 缺陷落库即推送到 [plant-safety](https://github.com/nizuowanzhenbang/plant-safety) 建一条重大隐患单（14 天整改期），失败 5 分钟自动重试，缺陷列表显示联动状态 + 隐患单号。

> 🧩 配 `SAFETY_SYSTEM_URL=http://localhost:8000` + 两侧 `INTEGRATION_SECRET` 一致即可。

---

## 🚀 快速开始

### Docker Compose 一键启动（推荐）

```bash
docker compose up -d --build
# 前端 http://localhost:8080
# 后端 http://localhost:8003/docs
# MinIO 控制台 http://localhost:9001（minioadmin/minioadmin）
# 默认账户 admin / admin123
```

### 本地开发

```bash
# 后端
cd backend
pip install -r requirements.txt
python seed_data.py      # 5 用户 + 18 设备 + 3 路线 + 一周任务 + 6 个典型缺陷
uvicorn app.main:app --port 8003 --reload

# 前端
cd frontend
npm install
npm run dev              # http://localhost:5175
```

## 🔐 默认账户

| 用户名 | 密码 | 角色 |
|---|---|---|
| `admin` | `admin123` | 管理员（全部） |
| `inspector` | `inspector123` | 点检员（任务/录入） |
| `repairman` | `repairman123` | 维修工（检修） |
| `supervisor` | `supervisor123` | 设备主管（派工/验收） |
| `viewer` | `viewer123` | 只读 |

> 🔒 生产部署请务必删掉 seed 用户、改强密码、关掉 `--reload`。

---

## 📋 业务规则速查

| 项 | 规则 |
|---|---|
| 设备分级 | A 关键 / B 重要 / C 一般 |
| 设备状态 | RUNNING ⇄ STANDBY / MAINTENANCE → DECOMMISSIONED |
| SLA | MINOR 72h / MAJOR 24h / CRITICAL 4h |
| 健康度 | 初始 100，缺陷扣分（-3 / -8 / -15），验收回弹 |
| 编号规则 | 设备 `EQ-{SYS}-NNNN` / 任务 `TK-YYYYMMDD-NNNN` / 缺陷 `DF-YYYYMMDD-NNNN` / 工作票 `WT-YYYYMMDD-NNNN` / 操作票 `OT-YYYYMMDD-NNNN` |

---

## 🛠️ 技术栈

| 层 | 选型 |
|---|---|
| 后端 | FastAPI · SQLAlchemy 2 · Pydantic v2 · APScheduler · JWT · boto3 · segno |
| 前端 | React 18 · TypeScript · Ant Design 5 · ECharts · Zustand · Vite · PWA(SW + IndexedDB) |
| 数据 | SQLite（开发）/ PostgreSQL 16（生产） |
| 存储 | 本地 disk / S3 / MinIO / 阿里云 OSS 可切换 |
| 端口 | 后端 `8003` / 前端 `5175`（容器 `8080`） |

## 📁 核心模型（14 张表）

`User · Equipment · InspectionRoute · InspectionPoint · InspectionTask · InspectionRecord · Defect · WorkTicket · OperationTicket · OperationTicketTemplate · SparePart · StockMovement · PurchaseRequest · AuditLog`

---

## 🔗 智慧发电厂全家桶中的位置

本项目是 [smart-power-plant](https://github.com/nizuowanzhenbang/smart-power-plant) 七大子系统中的"设备运维"模块，已对接：

| 系统 | 关系 |
|---|---|
| [plant-safety](https://github.com/nizuowanzhenbang/plant-safety) | `CRITICAL` 缺陷 → 推送重大隐患单（已实现） |
| [fuel-procurement](https://github.com/nizuowanzhenbang/fuel-procurement) | 备件采购申请 → 推送物资采购单（已实现） |
| [emission-monitoring](https://github.com/nizuowanzhenbang/emission-monitoring) | CEMS `FAULT` → 自动建点检缺陷（v3.1 规划） |

---

## 🚧 路线图（已实现 + 规划）

详细版本变更见下方分段，简要：

- ✅ **v1.0**：设备 + 路线 + 任务 + 缺陷工单全闭环
- ✅ **v2.0**：APScheduler 定时调度 + plant-safety 联动 + CSV 报表
- ✅ **v2.1**：照片真上传 + WebSocket 实时推送
- ✅ **v2.2**：两票管理 + 预测性维护 + PWA 扫码
- ✅ **v2.3**：备品备件 + 设备 360 全景 + 工作票打印
- ✅ **v2.4**：用户管理 + 操作票模板
- ✅ **v2.5**：QR 批量打印 + 审计日志
- ✅ **v3.0**：对象存储 + 两票电子签名 + PWA 离线点检 + 备件采购联动 + Docker Compose
- 🚧 **v3.1**：与 emission-monitoring 联动 + 健康度时间加权 + WebSocket Redis pubsub

<details>
<summary>📜 各版本详细变更（点击展开）</summary>

### v2.0
- 内置 APScheduler（4 个 job：超期扫描 / 漏检扫描 / 任务自动生成 / 联动重试）
- plant-safety 联动 + 失败重试
- CSV 导出 + 月度报表页面 + 调度器状态面板

### v2.1
- 照片真上传（本地 disk）
- WebSocket 实时推送 CRITICAL / OVERDUE / MISSED / 联动事件

### v2.2
- 工作票 + 操作票全闭环（关联缺陷工单，许可开工自动转设备状态）
- 预测性维护风险算法 + 散点图
- PWA + QR 扫码点检（BarcodeDetector + 手动输入降级）

### v2.3
- 备品备件 + 出入库流水 + 低库存预警
- 设备 360 全景（90 天点检 + 缺陷 + 工作票 + 备件耗用）
- 工作票 A4 打印视图
- plant-safety v1.1 接收接口（首个跨系统真闭环）

### v2.4
- 用户管理（ADMIN-only CRUD + 重置密码 + 启停）
- 操作票模板库

### v2.5
- 设备 QR 批量打印页（segno SVG，A4 4 列网格）
- 审计日志（关键写操作打点）

### v3.0
- 对象存储抽象（S3 / MinIO / OSS）+ 预签名 URL
- 两票电子签名（HMAC-SHA256 + 二次密码 + 签名链验签）
- PWA 离线点检（IndexedDB 队列 + 自动同步）
- 备件采购申请闭环（手工 + 低库存自动）→ fuel-procurement 联动
- Docker Compose 一键启动（4 服务）

</details>

## 📜 License

私有项目，未开源。


## 持续维护

[开发与验收说明](docs/MAINTENANCE.md)：自动检查、回归测试与演示边界。
