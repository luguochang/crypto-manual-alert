# Eval 工作台首版实现记录

## 1. 本次目标

本次实现的目标不是完整自进化平台，而是把“可观测、可回归、可人工复核”的最小闭环先跑通：

- 从生产 `badcases` 和 `traces` 生成 eval 候选。
- 运行一次旁路 eval，只读生产 journal，写独立 eval sidecar。
- 展示候选 case、最近 eval run、judge 明细和 side-effect guard。
- 证明 eval 不触发 Bark，不新增生产 `plan_runs`、`notifications`、`manual_outcomes`。

## 2. 新增后端结构

新增目录：

```text
src/crypto_manual_alert/eval/
  __init__.py
  schema.py        # EvalCase / EvalRun / EvalScore 数据对象
  store.py         # 独立 eval SQLite: data/eval/crypto-eval.db
  case_builder.py  # 从 badcase + trace detail 构建脱敏 frozen summary
  judges.py        # RuleJudge + FixtureLLMJudge + side-effect guard
  runner.py        # 旁路 EvalRunner
```

新增 API：

```text
GET  /api/eval/candidates
GET  /api/eval/runs
POST /api/eval/runs
GET  /api/eval/runs/{eval_run_id}
```

`POST /api/eval/runs` 首版只支持 `mode=judge_only_fixture`，默认不调用真实 LLM，不访问外网，不触发 Bark。

## 3. Eval Sidecar 表

首版使用独立 SQLite：

```text
data/eval/crypto-eval.db
```

表：

- `eval_cases`
- `eval_runs`
- `eval_scores`

生产 journal 仍是：

```text
data/crypto-alert.db
```

EvalRunner 不持有 `PlanRunner`、`NotificationSink`、`MarketDataProvider`，路径上没有通知或交易副作用入口。

## 4. Judge 设计

首版包含这些评分：

- `rule.expected_no_trade`：如果 badcase 期望 no trade / 禁止交易 / 不得开仓，则检查历史输出是否 no trade 或 `allowed=false`。
- `rule.trace_required_spans`：检查 trace 至少包含 `decision.final` 与 `risk.check`。
- `rule.manual_only`：检查输出没有关闭 `manual_execution_required`。
- `llm.fixture_grounding`：fixture LLMJudge，不访问网络，用可复现逻辑检查“数据缺口 + 开仓动作”的语义冲突。
- `eval.side_effect_guard`：检查 eval 前后生产 `plan_runs`、`notifications`、`manual_outcomes` delta 必须为 0。

真实 OpenAI-compatible LLMJudge 后续应替换 `FixtureLLMJudge` 边界，而不是改 UI 或 store。

## 5. 前端工作台

新增：

```text
frontend/src/app/eval/page.tsx
frontend/src/app/eval/run-eval-form.tsx
frontend/src/lib/api/eval.ts
frontend/src/lib/schemas/eval.ts
```

导航新增 `Eval`。

页面展示：

- 候选 case 数、Open 数、High/Critical 数、数据集数。
- 最近 eval run 列表。
- 最新 eval run 摘要，包括 side-effect delta。
- 候选 case 表，支持跳转 source trace。
- 最新 judge 明细，展示 pass/fail、case、source trace、judge 名称、类型、严重度、原因和人工复核标记。
- 顶部表单可触发 `judge_only_fixture` eval，成功后刷新页面查看最新结果。

## 6. 测试与边界

新增测试：

```text
tests/test_api_eval.py
```

覆盖：

- `/api/eval/candidates` 返回 badcase + trace 摘要，并不泄露 `raw_decision/request_json/response_json`。
- `/api/eval/runs` 能运行 fixture eval，并写入 eval sidecar。
- eval run 前后生产 `plan_runs`、`notifications`、`manual_outcomes` 计数不变。
- 空数据集返回稳定错误 `eval_no_cases`。
- `parsed_plan`、badcase `input_ref`、badcase `metadata` 的自由字段会脱敏或白名单过滤，避免 secret/raw payload 泄露到 eval API。
- 显式 `badcase_ids` 不受最近列表 limit 截断，可以回归较早的历史 badcase。
- `eval_scores` 保存 `source_trace_id` 与 `source_badcase_id`，页面可从失败 score 跳回 source trace。

Smoke 增加 `/eval` 页面访问检查。

## 7. 审查修复记录

本轮多 agent 审查指出两个关键风险，已修复：

- `parsed_plan` 是模型自由输出，不能整包进入 eval detail。当前已改为 `SAFE_PARSED_PLAN_KEYS` 白名单，并递归脱敏敏感 key。
- badcase 的 `input_ref` / `metadata` 是人工或系统自由 JSON，候选 API 不能 `{**badcase}` 直接返回。当前已改为候选字段白名单，并对自由 JSON 递归脱敏。

同时修复：

- `Journal.list_badcases()` 支持数据库层 `ids/dataset/status/severity` 过滤，避免先 limit 后过滤导致历史 case 丢失。
- `EvalRunner` 自身拒绝非 `judge_only_fixture` 模式，避免只在 API route 做边界。
- `eval_scores` 保存 `source_trace_id` 与 `source_badcase_id`，页面可从失败 score 跳回 source trace。
- `.gitignore` 增加 `data/**/*.db`、`data/**/*.sqlite`、`data/**/*.sqlite3`，避免提交 eval sidecar 本地数据库。

## 8. 后续缺口

首版仍未实现：

- 真实 OpenAI-compatible LLMJudge。
- FrozenInput 文件 artifact。
- HumanReview 状态机。
- baseline/candidate 对比。
- release gate。
- third-party exporter。

这些能力应在 sidecar、case、score、UI 明细稳定后继续加，不应直接改主业务 runner。
