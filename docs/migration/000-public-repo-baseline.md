# 000-public-repo-baseline

## 目标

建立公开 GitHub 仓库前的基础安全边界，避免真实 secret、本地数据库、日志和前端构建产物进入仓库。

## 改动文件

- `.gitignore`
- `README.md`

## 行为变化

- 新增 `.gitignore`，排除 `.env`、本地 SQLite、日志、Python 缓存、Next.js 构建产物和 `node_modules`。
- README 明确项目定位为人工提醒系统，不是自动交易系统。

## 安全影响

- 不提交真实 OpenAI key、Bark key、OKX key。
- 不提交 `data/*.db`、`data/*.sqlite`、日志和 raw artifact。
- README 保留 secret scan 命令，供推送前检查。

## 测试命令

```powershell
python -m pytest
rg -n "sk-[A-Za-z0-9]{20,}|BARK_DEVICE_KEY=[A-Za-z0-9]{20,}|OKX_API_SECRET=.+|OKX_API_PASSPHRASE=.+" . --glob "!data/**" --glob "!frontend/node_modules/**"
```

## 已知风险

- 当前目录还不是 Git 仓库，无法用 `git status` 验证跟踪文件。
- 历史对话中用户提供过真实 key，不能把对话内容复制进 README 或 docs。
