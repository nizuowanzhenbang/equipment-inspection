# 前端依赖升级：2026-10-01

## 变更与依据

- Vite 5.4.21 → 8.3.1，React插件6.1.1，构建使用Rolldown；项目Node要求22.12+（测试使用原生TypeScript去类型参数）。Docker/CI使用Node22，本地验证Node24。
- React Router DOM 6.30.6 → 7.18.4，保留React18和声明式BrowserRouter路由；没有data-router loaders、SSR或多段splat路径需要迁移。
- ECharts5 → 6.1.0；Dashboard/Reports显式指定legend.top=0，防止新默认主题使图例挤占现有底部坐标标签空间。
- Axios按本次新增公告兼容更新至1.20.0；没有使用npm audit fix --force。
- 预测维护自定义HTML提示框原来直接插入设备名称，现将所有插入值转义，保留受控br换行；针对恶意HTML和正常零值做回归。

官方迁移依据：[Vite](https://vite.dev/guide/migration)、[React Router](https://reactrouter.com/7.18.4/upgrading/v6)、[ECharts](https://echarts.apache.org/handbook/en/basics/release-note/v6-upgrade-guide/)。

## 验证与维护

2026-10-01 npm audit全量扫描为0个已知漏洞项，原始结果见dependency-audits/npm-20261001.json；这仅代表该时刻npm公告库结果。Python ecdsa既有公告、基础镜像OS扫描范围见REPRODUCIBLE-DEPLOYMENT.md，不宣称整个系统没有漏洞。

前端CI在npm ci之后运行npm audit --audit-level=low，扫描失败或命中任何级别公告都会阻止该job成功，并保存JSON14天。新公告出现时需人工评估兼容修复，不自动跨大版本更新。

本地npm ci、TS/生产构建、7项Node测试通过；4项Chromium测试覆盖登录/退出、受限路由、菜单导航、刷新、真实API数据和三页五张图表。使用生产dist的Vite preview与独立SQLite模拟后端，不能当成Docker验收。容器验收由远端Compose+PostgreSQL CI执行。

图表测试检查真实响应、非空画布、动画稳定及无未处理JS异常，并保存截图供人工查看；它不是像素级视觉基线，也没有证明预测模型业务准确性。已有单包体积警告保留，性能分包留作独立迭代。

## 回退

本轮没有数据库迁移，前一轮提交0b3ce56作为回退基线。回退完整代码与package-lock并重新npm ci/构建镜像，不改已有数据库卷。PR仍按依赖顺序集成，草稿PR不代表已合并或生产发布。
