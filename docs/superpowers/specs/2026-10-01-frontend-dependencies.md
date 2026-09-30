# 第 5 轮设计：前端依赖安全与兼容升级

目标：处理第4轮 npm audit 剩余5个受影响包，并留下可重复升级案例。用户已授权自主决策和完成后进入下一轮。

选型：Vite 8.3.1 + @vitejs/plugin-react 6.1.1；React Router DOM 7.18.4（满足已知公告修复范围且兼容 React18）；ECharts6.1.0。保持现有SPA架构、React18与接口，避免把安全维护扩展成重写。Node22.12+，CI/Docker已有Node22。

方案：先记录旧锁 audit 失败；更新直接依赖并重新锁定。ECharts默认主题/图例布局有变化，显式保留上方图例以匹配现有grid。审查全部图表使用点（Dashboard/Reports/PredictiveMaintenance）。

验收：npm ci + audit 全量报告0已知项（仅当扫描成功）；TS/build、5项离线回归；真实Chromium验证未登录受限、登录、菜单导航、深链接刷新、图表非空画布与无未处理JS异常、退出后重新访问拒绝。图表截图人工查看，权限仍由后端测试支撑。继承Compose空卷冷启动CI；不宣称覆盖全部浏览器或所有漏洞。

维护：CI增加npm audit门禁和归档JSON。新公告导致CI失败时复核修复，禁止自动force升级；保留单独分支、PR和回退标签。Python ecdsa公告不在本轮改动范围，仍明确披露。

实施顺序：第4轮全部CI通过 -> 建分支/保存本设计 -> 更新依赖和必要兼容代码 -> 增强浏览器验收 -> 本地构建/测试/扫描 -> 独立审查 -> 推送PR -> 等最终CI和查看截图 -> 更新作品集交付记录。

官方依据：
- https://vite.dev/guide/migration
- https://reactrouter.com/7.18.4/upgrading/v6
- https://echarts.apache.org/handbook/en/basics/release-note/v6-upgrade-guide/

实施发现：新增 Axios 公告通过兼容升级至1.20.0修复。预测维护tooltip直接拼接设备名称HTML，加入转义（单测先重现失败）；此项属于本轮已确认的应用层安全问题。图表截图等待canvas动画稳定。
