# jiami-crypto-alert

AI-assisted crypto manual alert and evaluation workbench.

本项目定位是“人工确认的加密货币操作提醒”，不是自动交易系统。系统可以抓取行情、调用固定 crypto skill、生成操作计划、记录 trace，并通过 Bark 强提醒用户手动核对；v1 明确不提供下单、撤单、提现能力。

## 技术栈

- Python 3.11+：FastAPI、Agent workflow、skill 调用、行情、LLM、Bark、Trace/Eval。
- TypeScript / Next.js：本地工作台、手动 query、Runs/Trace 查看、后续 Eval/Candidates 页面。
- SQLite：默认本地存储，不依赖 Redis、队列、Temporal、向量库或外部 LLMOps 服务。

## 当前能力

- `GET /api/system/health`：API 健康检查。
- `POST /api/runs/manual`：提交一次手动分析，返回 `trace_id`、计划摘要和风控结论。
- `GET /api/runs`：查询最近运行记录。
- `GET /api/runs/{trace_id}`：查询 trace、span、LLM 摘要、badcase，默认隐藏原始 prompt/completion payload。
- CLI 旧入口仍兼容：`jiami-alert run-once --symbol ETH-USDT-SWAP`。

## 本地启动

```powershell
cd E:\file\project\selfproject\project\jiami
python -m pip install -e .
python -m pytest
uvicorn jiami_crypto_alert.api.app:app --reload
```

前端工作台位于 `frontend/`，启动前先设置：

```powershell
$env:NEXT_PUBLIC_API_BASE_URL="http://127.0.0.1:8000"
```

## 环境变量

复制 `.env.example` 后只在本地填写真实值，不要提交 `.env`。

- `OPENAI_BASE_URL`、`OPENAI_API_KEY`、`OPENAI_MODEL`：仅在 `DECISION_ENGINE=openai_compatible` 时需要。
- `BARK_DEVICE_KEY`：仅在 `NOTIFICATION_ENABLED=true` 时需要。
- `OKX_API_KEY` 等只作为未来只读账户集成预留；v1 禁止交易和提现 key。

## 安全边界

- `AUTO_ORDER_ENABLED` 必须保持 `false`。
- `manual_execution_required` 必须保持 `true`。
- 不注册任何下单、撤单、提现工具。
- eval/replay 不允许发 Bark。
- 前端/API/日志不返回完整 secret。
- 默认不暴露 raw prompt、raw completion 或 LLM 原始请求/响应。

## 测试

```powershell
python -m pytest
```

公开仓库推送前至少检查：

```powershell
rg -n "sk-[A-Za-z0-9]{20,}|BARK_DEVICE_KEY=[A-Za-z0-9]{20,}|OKX_API_SECRET=.+|OKX_API_PASSPHRASE=.+" . --glob "!data/**" --glob "!frontend/node_modules/**"
```

## 目录

```text
src/jiami_crypto_alert/
  api/        FastAPI 路由和响应契约
  context/    DecisionRequest 等请求语义
  workflow/   RunExecutor 受控执行入口
  storage/    UI/API 查询门面
  runner.py   legacy PlanRunner 管线
  journal.py  SQLite trace/journal
frontend/     Next.js TypeScript 工作台
docs/formal/  正式设计文档
docs/migration/ 每轮开发迁移记录
```
