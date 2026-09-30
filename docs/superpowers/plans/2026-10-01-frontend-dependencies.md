# 第5轮执行记录

设计：../specs/2026-10-01-frontend-dependencies.md。按用户自主决策授权执行，当前功能分支基于已通过全部CI的0b3ce56。

- [x] 核对官方迁移说明和当前使用点；选择兼容React18的Router7，Vite8/Node22，ECharts6。
- [x] 更新lock并重装；修复新的Axios兼容公告；npm audit全量0项。
- [x] tooltip回归先复现未转义HTML失败，然后添加转义；7项Node测试通过。
- [x] 三页图例位置与图表截图核对，5张画布等待动画稳定；4项Chromium本地生产preview验证通过。
- [x] CI加入audit阻断及JSON归档，记录残余Python公告和验证边界。
- [ ] 独立审查、提交、回退验证、推送新PR并等待最终CI。

Ruling: 不升React或重写SPA路由，Router7.18.4已满足本轮公告修复需求；代价是未来Router8仍需独立升级评估。
Ruling: tooltip直接拼接HTML属于检查中发现的具体风险，纳入本轮并以先红后绿覆盖；代价是增加少量应用代码而不只是依赖文件。

独立审查无Critical/Important；采纳Minor并把项目Node要求统一为22.12+，因为Node20不能运行既有去类型测试命令。
