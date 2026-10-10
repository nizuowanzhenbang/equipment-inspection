# Codex 电厂项目接续规则

本仓库属于用户的电厂项目。统一进度仓库：
https://github.com/nizuowanzhenbang/smart-power-plant/tree/main/progress （公开，默认分支 main，进度文件位于 progress/）。

## 开工先读

在分析或修改业务代码前，通过可用 GitHub 连接或已认证的 gh/git，读取 smart-power-plant 默认分支最新 `progress/AGENTS.md`、`progress/SUMMARY.md`、`progress/CURRENT.md`、`progress/TASKS.md`。按本轮范围再读 `REPOSITORIES.md`、`DECISIONS.md` 和相关日志/证据。读取路径是 smart-power-plant 的 progress/ 目录，不是当前代码仓库。

可以用 GitHub 文件读取工具；CLI 示例：

```bash
gh api repos/nizuowanzhenbang/smart-power-plant/commits/main --jq .sha
gh api repos/nizuowanzhenbang/smart-power-plant/contents/progress/AGENTS.md -H 'Accept: application/vnd.github.raw+json'
gh api repos/nizuowanzhenbang/smart-power-plant/contents/progress/SUMMARY.md -H 'Accept: application/vnd.github.raw+json'
gh api repos/nizuowanzhenbang/smart-power-plant/contents/progress/CURRENT.md -H 'Accept: application/vnd.github.raw+json'
gh api repos/nizuowanzhenbang/smart-power-plant/contents/progress/TASKS.md -H 'Accept: application/vnd.github.raw+json'
```

批量读取时先取得 SHA，再用同一 SHA 读取这些文件以保持一致；正式改动前核对远端是否更新。读取失败先检查连接和路径，不要输出认证凭证。

读取后简短报告进度 SHA、本轮任务编号、已完成且不重做的内容和第一项动作；在中央 `CURRENT.md` 认领当前任务。再核对本仓库分支/HEAD/未提交改动及相关 PR，读取本仓库现有 `CLAUDE.md`（如有）和任务相关源码。用户当前指令优先，历史授权文字不能扩大本轮范围。

## 避免重复

台账中“已合并”或“已有覆盖”默认不重做；只有真实回归、新要求或证据冲突才重新打开并记录原因。不要每轮重新扫描、重跑所有仓库。原始日志和历史方案只作为证据，不覆盖最新接续文件。

如果无法读取中央进度，说明原因，保留访问错误，可继续独立的只读核查；在已授权范围内必须继续工作时，明确以本仓库实际状态为依据并保存本地交接，最终标注“中央进度未读取/未同步”，不要声称已确认没有重复。

## 收尾回写

有实质工作时，在最终回复前更新中央 `CURRENT.md` 和 `TASKS.md`，追加本轮 `logs/`；能力、基线或决策变化时更新 `SUMMARY.md`、`REPOSITORIES.md`、`DECISIONS.md`。记录实际 SHA、PR、检查、剩余事项和第一项接续动作，提交并推送；并发更新先合并，不强推覆盖。

未完成、未推送、未合并、CI 待完成分别注明。回写受阻则保留本地交接并在最终回复明确“进度未同步”。不要把模拟数据、预测收益或历史测试写为本轮现场验证。
