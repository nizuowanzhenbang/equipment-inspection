# 开发与验收

本仓库是电厂业务场景的个人软件原型。界面、规则和模拟数据用于学习与演示；未据此宣称在电厂投产、接入 DCS 或取得经营收益。

## 本地检查

在仓库根目录创建 Python 3.11 虚拟环境后执行：

```sh
python -m pip install -r backend/requirements.txt pytest httpx ruff
python -m ruff check backend --select E9,F63,F7,F82
cd backend && python -m pytest tests -q
cd frontend
npm ci --no-audit --no-fund
npm run build
```

GitHub Actions 对 PR、主分支提交及手动触发执行相同检查。前端锁文件用于重现依赖；更新依赖时一并更新锁文件并运行检查。现有旧版固定依赖仍需单独做兼容性及漏洞升级评估，这次未宣称完成依赖安全审计。

## 演示与边界

- 依照 README 的启动和模拟数据说明准备演示环境。
- 讲清输入、业务约束、角色权限、失败处理和数据库结果，展示一个正常流程和一个被拒绝的异常流程。
- 测试通过只代表覆盖的用例通过，不等于性能、并发、现场规程或生产安全验收。
- 使用个人构造的设备、人员和业务数据；真实部署另行配置密钥、账户、数据库备份及访问控制。
- 项目组合与讲解路线：[smart-power-plant](https://github.com/nizuowanzhenbang/smart-power-plant)。
