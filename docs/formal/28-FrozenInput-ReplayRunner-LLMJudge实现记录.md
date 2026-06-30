# FrozenInput、ReplayRunner 与 LLMJudge 实现记录

## 1. 本轮目标

本轮目标是先把 eval 测评链路做到可回放、可审计、可对比，而不是继续停留在“把 badcase 摘要存起来”的玩具状态。

完成范围：

- 生产 `PlanRunner` 在决策模型调用前生成 `FrozenInput`。
- `RiskVerdict` 增加结构化 `RuleHit`，保留旧的 `reasons/warnings` 兼容字段。
- eval sidecar 独立保存 `eval_frozen_inputs` 和 `eval_replay_outputs`。
- `ReplayRunner` 基于冻结输入和历史观测结果做旁路 replay，不调用实时行情、不调用生产 runner、不发通知。
- 新增真实 OpenAI-compatible `LLMJudge`，在显式 `judge_openai` 模式下运行 5 个 judge。
- Eval 页面展示 Frozen hash、Replay 状态、Judge score、耗时和 token。

## 2. 关键设计

### 2.1 FrozenInput

新增模块：

```text
src/crypto_manual_alert/frozen_input.py
```

`PlanRunner` 在以下位置冻结输入：

```text
market.fetch
  -> skill.load
  -> optional research
  -> prompt.build
  -> input.freeze
  -> decision.final
```

冻结内容是最终送给决策模型的 prompt packet 的脱敏结构化副本。hash 使用稳定 JSON 序列化后计算 sha256。

生产 `plan_runs.payload_json` 新增：

```json
{
  "frozen_input": {
    "schema_version": 1,
    "kind": "decision_prompt_packet",
    "sha256": "...",
    "payload": {},
    "public_summary": {}
  },
  "frozen_input_hash": "..."
}
```

注意：

- Trace/API 默认仍不暴露完整 `raw_decision`。
- eval case 默认也不把完整 `FrozenInput.payload` 返回给前端。
- `Journal.get_plan_run_payload()` 是内部方法，用于 eval sidecar 构建冻结输入。

### 2.2 RuleHit

新增领域模型：

```python
RuleHit(
    rule_id: str,
    passed: bool,
    severity: str,
    message: str,
    blocking: bool,
    evidence_refs: list[str],
    details: dict
)
```

`RiskVerdict` 现在包含：

```python
allowed
reasons
warnings
rule_hits
```

稳定 rule_id 示例：

- `opening.stop_price.required`
- `opening.entry_trigger.required`
- `opening.invalidation.required`
- `market.core_execution.missing`
- `market.data.stale`
- `confidence.probability.cap`
- `pipeline.decision_engine.error`

旧页面或 API 仍可读取 `reasons/warnings`，新 eval 和 trace 可以读取结构化 `rule_hits` 做归因。

### 2.3 ReplayRunner

新增模块：

```text
src/crypto_manual_alert/eval/replay.py
```

ReplayRunner 的边界：

- 只读取 `eval_frozen_inputs`。
- 只读取 case 的历史 `observed_output`。
- 只写 `eval_replay_outputs`。
- 不调用 `PlanRunner.run_once()`。
- 不调用 OKX、web search、Bark。
- 不写生产 `plan_runs/notifications/manual_outcomes/traces/trace_spans/llm_interactions`。

当前 replay 模式是 `frozen_observed`，用于确认“本次 eval 使用哪份冻结输入、历史解析结果和风控结果”。它还不是 candidate workflow 的重新推理。后续做 baseline vs candidate 时，可以在同一张 replay 输出表中增加 candidate 输出。

### 2.4 LLMJudge

新增模块：

```text
src/crypto_manual_alert/eval/judges/llm.py
```

显式模式：

```text
judge_openai
```

5 个 judge：

- `llm.evidence_grounding`
- `llm.opposing_thesis`
- `llm.data_gap_honesty`
- `llm.execution_clarity`
- `llm.overconfidence`

LLMJudge 使用 OpenAI-compatible `/v1/chat/completions`，复用当前 `decision.openai_base_url`、`decision.openai_model`、`decision.openai_api_key_env` 配置。它不会写生产 `llm_interactions`，而是把耗时、token、finish_reason 写入 `eval_scores.metadata`。

模型返回必须是严格 JSON：

```json
{
  "passed": true,
  "score": 0.82,
  "severity": "low",
  "failure_category": "none",
  "reason_summary": "...",
  "evidence_refs": ["frozen_input_hash", "replay.output"],
  "needs_human_review": false
}
```

如果返回非法 JSON，本轮不会中断 eval run，而是生成稳定 failed score：

```text
failure_category = llm_judge_invalid_response
needs_human_review = true
```

## 3. 数据表变化

Eval sidecar SQLite 新增：

```text
eval_frozen_inputs
  frozen_input_hash
  schema_version
  kind
  source_trace_id
  source_badcase_id
  input_json
  public_summary_json
  metadata_json

eval_replay_outputs
  replay_id
  case_id
  source_trace_id
  source_badcase_id
  frozen_input_hash
  status
  mode
  final_action
  allowed
  output_hash
  reason_summary
  error_message
  duration_ms
  output_json
  metadata_json
```

生产 journal 未新增表，只是在 `plan_runs.payload_json` 里追加字段。

## 4. API 与 UI

Eval API 保持：

```text
GET  /api/eval/candidates
GET  /api/eval/runs
POST /api/eval/runs
GET  /api/eval/runs/{eval_run_id}
```

`GET /api/eval/runs/{id}` 的 `cases[]` 新增：

```json
{
  "frozen_input_hash": "...",
  "replay_result": {
    "status": "completed",
    "mode": "frozen_observed",
    "final_action": "no trade",
    "allowed": true,
    "output_hash": "...",
    "reason_summary": "...",
    "duration_ms": 0
  }
}
```

前端 `/eval` 页面新增：

- 最新 Frozen / Replay 表。
- Judge 明细中的 `Score` 列。
- Judge 明细中的耗时 / token 列。
- `judge_openai` 模式选项。

## 5. 安全边界

当前仍然是人工操作提醒系统：

- 不自动下单。
- eval 不触发通知。
- eval 不调用生产 `PlanRunner`。
- eval 不访问实时行情。
- eval 默认不跑真实 LLM，必须显式选择 `judge_openai`。
- 生产 trace/API 默认不暴露完整原始 completion。
- 真实 key 不写入代码、不写入文档、不提交仓库。

## 6. 配置要求

运行 `judge_openai` 需要：

```env
OPENAI_BASE_URL=https://your-compatible-endpoint
OPENAI_MODEL=your-model
OPENAI_API_KEY=your-key
```

或者通过配置文件设置：

```yaml
decision:
  openai_base_url: "https://your-compatible-endpoint"
  openai_model: "your-model"
  openai_api_key_env: "OPENAI_API_KEY"
```

`cheap` 和 `judge_only_fixture` 不需要真实模型 key。

## 7. 测试覆盖

新增或更新测试：

- `tests/test_plan_parser_and_risk.py`
  - 风控规则改为稳定 `rule_id` 断言。
  - 覆盖结构化 `RuleHit`。
- `tests/test_runner_cli.py`
  - 验证生产 run 持久化 exact FrozenInput。
  - 验证决策引擎失败时仍记录 FrozenInput 和 pipeline rule hit。
- `tests/test_eval_replay_llmjudge.py`
  - 验证 eval sidecar 保存 FrozenInput。
  - 验证 ReplayRunner 不产生生产副作用。
  - 验证真实 OpenAI-compatible LLMJudge mock 调用和 5 个 score。
  - 验证非法 judge JSON 会生成稳定人工复核 score。
- `tests/test_api_eval.py`
  - 验证 eval detail 暴露 `replay_result`。
  - fake store 补齐新接口，保留报告清理测试。

本轮已执行：

```text
pytest -q
npm run typecheck
npm run build
```

后续还需要执行项目总脚本：

```text
python tests/run_local_checks.py
```

## 8. 剩余边界

本轮还没有完成：

- candidate workflow replay，也就是用新版本 workflow 重新推理并与 baseline 比较。
- LLMJudge 分数作为 release gate 的硬门禁。
- Human review 前端表单。
- Judge rubric 页面化配置。
- LLMJudge 多模型互评或仲裁。
- Eval 报告中的 replay 输出展开展示。

这些应在当前闭环稳定后继续推进，不能直接塞进生产交易提醒主链路。
