# crypto-manual-alert

AI-assisted crypto manual alert and evaluation workbench.

本项目定位是“人工确认的加密货币操作提醒”，不是自动交易系统。系统可以抓取行情、调用固定 crypto skill、生成操作计划、记录 trace，并通过 Bark 强提醒用户手动核对；当前手动提醒阶段明确不提供下单、撤单、提现能力。

## 技术栈

- Python 3.11+：FastAPI、Agent workflow、skill 调用、行情、LLM、Bark、Trace/Eval。
- TypeScript / Next.js：本地工作台、手动 query、Runs/Trace 查看、后续 Eval/Candidates 页面。
- SQLite：默认本地存储，不依赖 Redis、队列、Temporal、向量库或外部 LLMOps 服务。

## 当前能力

- `GET /api/system/health`：API 健康检查。
- `POST /api/runs/manual`：提交一次手动分析，返回 `trace_id`、计划摘要和风控结论。
- `GET /api/runs`：查询最近运行记录。
- `GET /api/runs/{trace_id}`：查询 trace、span、LLM 摘要、badcase，默认隐藏原始 prompt/completion payload。
- CLI 入口：`crypto-alert run-once --symbol ETH-USDT-SWAP`。

## 当前架构状态

当前生产决策链仍是 legacy prompt 主链，不是 Agent Swarm 接管。真实链路是 `RunExecutor -> LegacyPlanRunnerAdapter -> LegacyDecisionWorkflow -> final LLM -> parser/gates -> journal/notification`。

仓库内已有 `agent_swarm/`、`lead/`、`artifacts/`、`decision/` 等受控 Agent Swarm 迁移模块，但目前默认只作为 shadow audit、candidate/replay 和结构化审计侧路使用；`DecisionInput` 仍不是生产 FinalDecisionAgent 的默认输入，`decision.final_input_mode` 默认仍是 `legacy_prompt`。后续重构以 `docs/formal/34-生产级AgentSwarm优化目标与执行计划.md` 的 checkpoint 为准；`31/32` 只保留为历史计划和背景材料。

## 本地启动

```powershell
cd <repo-root>
python -m pip install -e .
python -m pytest
uvicorn crypto_manual_alert.api.app:app --reload
```

前端工作台位于 `frontend/`，启动前先设置：

```powershell
$env:NEXT_PUBLIC_API_BASE_URL="http://127.0.0.1:8000"
```

## 环境变量

复制 `.env.example` 后只在本地填写真实值，不要提交 `.env`。

- `OPENAI_BASE_URL`、`OPENAI_API_KEY`、`OPENAI_MODEL`：仅在 `DECISION_ENGINE=openai_compatible` 时需要。
- `BARK_DEVICE_KEY`：仅在 `NOTIFICATION_ENABLED=true` 时需要。
- `OKX_API_KEY` 等只作为未来只读账户集成预留；当前手动提醒阶段禁止交易和提现 key。

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
src/crypto_manual_alert/
  api/        FastAPI 路由和响应契约
  agent_swarm/  受控 worker、harness、shadow 编排运行时
  artifacts/    结构化证据、贡献和编排输入
  cli/        命令行入口和子命令装配
  config/     配置模型、加载和安全校验
  context/    DecisionRequest、DecisionRunContext 和 artifact store
  decision/   决策输入、解析、门禁和最终输入选择
  domain/     领域数据结构
  lead/       LeadAgent 规划与 synthesis
  market/     行情 provider
  notification/ Bark 等通知 sink
  research_pipeline/ 检索降级链路
  skills/     skill runtime 与决策引擎适配
  storage/    SQLite journal 和查询仓储
  telemetry/  trace、span、LLM telemetry
  workflow/   RunExecutor、legacy workflow shell 和步骤编排
tests/        按业务域归档的测试，根层不放散落 .py
tools/local_stack/ 本地启动和烟测脚本
frontend/     Next.js TypeScript 工作台
docs/formal/  正式设计文档
docs/migration/ 每轮开发迁移记录
```

`src/crypto_manual_alert/` 根包只保留包元信息；新增 Python 实现必须进入对应业务子包，不能直接平铺到根包。
