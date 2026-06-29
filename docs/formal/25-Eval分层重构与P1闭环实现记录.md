# Eval 分层重构与 P1 闭环实现记录

## 1. 本轮目标

本轮不是继续扩大平台能力，而是把前期 P1/首版 eval 计划中已经承诺但未完全落地的部分补齐，并同步修正代码分层问题。

完成口径：

- `EvalRunner` 只做编排，不再堆具体规则、报告、CLI、安全检查。
- API 和 CLI 都能运行 `cheap` eval。
- `judge_only_fixture` 仍可用于本地语义审查闭环。
- 每次 eval run 生成 JSON/Markdown 报告。
- eval run 明确拒绝带交易/提现密钥的运行环境。
- eval detail 保留当次 case 快照，历史 run 不被后续 badcase 改动污染。
- 前端 Eval 页面能看到报告引用和每个 judge 的 evidence refs。
- 聚焦测试和前端类型检查通过。

## 2. 代码分层

当前 eval 目录结构：

```text
src/crypto_manual_alert/eval/
  cli.py                 # eval CLI 注册与命令处理
  case_builder.py        # 从生产 badcase/trace 构建脱敏 eval case
  runner.py              # 旁路 eval 编排：选 case、调 judge、写报告、落库
  schema.py              # EvalCase / EvalRun / EvalScore
  store.py               # 独立 eval SQLite sidecar
  guards/
    env.py               # eval 环境安全检查
  judges/
    common.py            # judge 公共取数与 score 构造
    rules.py             # RuleJudge 确定性规则
    fixture_llm.py       # 本地 fixture LLMJudge 替身
    side_effects.py      # 生产副作用 guard score
  reports/
    writer.py            # JSON/Markdown 报告生成
```

主 CLI 只负责注册和转发：

```text
src/crypto_manual_alert/cli.py
  -> eval.cli.add_eval_subcommands()
  -> eval.cli.handle_eval_command()
```

API route 只做请求校验和错误映射：

```text
POST /api/eval/runs
  -> EvalRunner.run()
```

## 3. Eval 模式

### cheap

用于提交前、本地回归和首版 P1 验收。

特点：

- 不调用真实 LLM。
- 不调用 fixture LLMJudge。
- 只运行 RuleJudge 和 side-effect guard。
- 生成报告。
- 写独立 eval sidecar。
- 不写生产 `plan_runs`、`notifications`、`manual_outcomes`。

### judge_only_fixture

用于本地页面演示和语义审查闭环。

特点：

- 运行 RuleJudge。
- 运行可复现的 `FixtureLLMJudge`。
- 不访问网络，不调用真实大模型。
- 生成报告。

真实 OpenAI-compatible LLMJudge 仍属于后续 P2+，不在本轮实现。

## 4. 已补齐的 P1 能力

### 4.1 JSON/Markdown 报告

每次 eval run 生成：

```text
data/eval/reports/<eval_run_id>.json
data/eval/reports/<eval_run_id>.md
```

报告引用写入 `EvalRun.metadata`：

```json
{
  "report_json_ref": "eval/reports/<eval_run_id>.json",
  "report_markdown_ref": "eval/reports/<eval_run_id>.md"
}
```

### 4.2 CLI

新增命令：

```powershell
python -m crypto_manual_alert.cli eval-run --dataset failure_cases --mode cheap
python -m crypto_manual_alert.cli eval-run --badcase-id 1 --mode judge_only_fixture
python -m crypto_manual_alert.cli eval-report --eval-run-id <eval_run_id>
python -m crypto_manual_alert.cli eval-list-runs
python -m crypto_manual_alert.cli eval-show-run --eval-run-id <eval_run_id>
```

项目脚本入口也可用：

```powershell
crypto-alert eval-run --dataset failure_cases --mode cheap
```

没有 case 时，CLI 返回稳定 JSON 错误：

```json
{
  "error": "eval_no_cases",
  "message": "no eval cases selected"
}
```

### 4.3 RuleJudge 覆盖

当前首版规则：

- `rule.action_enum`
  - 检查 `main_action` 是否属于允许枚举。
- `rule.expected_no_trade`
  - badcase 期望 no trade / 禁止 / 不得交易时，检查历史输出是否 no trade 或 risk blocked。
- `rule.opening_requirements`
  - 开仓、触发、反手、市价买入/卖出等意图必须有 `entry_trigger`、`stop_price`、`invalidation`。
- `rule.trace_required_spans`
  - trace 至少应包含 `decision.final` 和 `risk.check`。
- `rule.manual_only`
  - 不允许 `manual_execution_required=false`。
- `eval.side_effect_guard`
  - eval 前后生产 `plan_runs`、`notifications`、`manual_outcomes` delta 必须为 0。

### 4.4 eval 环境安全 guard

新增 `eval/guards/env.py`。

默认拒绝：

```text
OKX_TRADE_API_KEY
OKX_WITHDRAW_API_KEY
```

同时合并配置里的：

```yaml
security:
  forbidden_env_names:
    - OKX_TRADE_API_KEY
    - OKX_WITHDRAW_API_KEY
```

命中时 API 返回：

```json
{
  "code": "eval_forbidden_secret_env"
}
```

CLI 返回：

```json
{
  "error": "eval_forbidden_secret_env"
}
```

### 4.5 历史 case 快照

新增 `eval_run_cases` 表。

每次 eval run 会保存当次 case JSON 快照。后续同一 trace/badcase 被重新标注或新增 badcase，不会改变历史 eval run detail。

### 4.6 前端工作台补充

`/eval` 页面补充：

- 触发 eval 时可选择 `cheap` 或 `judge_only_fixture`。
- 最新 run 摘要显示 JSON/Markdown 报告引用。
- judge 明细表显示 `evidence_refs`。

## 5. 仍然后置的能力

这些不是本轮 P1 闭环阻断项：

- 完整 FrozenInput 文件 artifact 和 `eval_artifacts` 表。
- 真实 OpenAI-compatible LLMJudge。
- 5 个 LLMJudge rubric。
- token/cost/latency 统计。
- baseline/candidate replay 对比。
- HumanReview 状态机和 review queue。
- release gate。
- golden set。
- Langfuse/Phoenix/LangSmith exporter。
- 更完整的 OKX mark/index/order_book、stale block、confidence cap、risk/leverage、search-derived 边界规则。

## 6. 本轮测试

已通过聚焦测试：

```powershell
python -m pytest tests\test_api_eval.py tests\test_runner_cli.py -q
# 20 passed
```

已通过前端类型检查：

```powershell
cd frontend
npm run typecheck
```

全量验收仍以以下命令为准：

```powershell
python tests\run_local_checks.py
```

## 7. 后续维护要求

- 新增 eval judge 时放到 `eval/judges/` 下，不要塞进 `runner.py`。
- 新增报告格式时放到 `eval/reports/` 下。
- 新增安全边界时放到 `eval/guards/` 下。
- 新增 CLI 子命令优先放到 `eval/cli.py`，主 `cli.py` 只注册和分发。
- 新增 P2+ 能力前先补测试，再实现。
