# trace 查询与 badcase 回流落地说明

## 1. 本轮结论

本轮完成的是 Trace Ledger 的查询与人工 badcase 回流闭环，不建设完整 LLMOps / replay 平台。

已经落地：

- `trace-list`：查看最近运行记录，并展示 `span_count`、`llm_interaction_count`。
- `trace-show`：查看单次运行的 trace、span、LLM interaction 摘要、关联 plan 摘要、analysis 和 badcases。
- `record-badcase`：把人工发现的问题挂回 `trace_id` 或 `plan_id`，可选定位到 `span_id` / `llm_interaction_id`。
- `badcase-list`：查看已记录的 badcase。
- LLM interaction 会自动关联当前 active span，后续可以定位“哪一步模型调用导致问题”。
- trace 查询默认不返回 `request_json`、`response_json`、`raw_decision`，避免把完整 prompt、completion 或敏感上下文打印出来。

仍未落地：

- 自动 replay / eval runner。
- badcase 自动聚类和指标面板。
- 每个 research query 单独 span。
- 完整 StepSpec / retry / timeout 统一执行器。

## 2. 多 Agent 评审采纳情况

本轮使用了两个并行只读子 Agent 评审：

- Agent A：评审 badcase/eval 最小数据模型。
- Agent B：评审 trace 查询最小行为。

采纳点：

- badcase 只作为索引和回流入口，不复制大 payload。
- badcase 通过 `trace_id` 主关联，通过 `span_id` / `llm_interaction_id` 精确定位。
- `llm_interactions.span_id` 原来有列但没有写入，本轮已补 active span 关联。
- trace 查询默认只展示 hash、summary、status、analysis，不默认展示原始 request/response。
- `trace-list` 需要计数，便于快速判断一次运行是否缺 span 或缺 LLM 记录。

没有完全采纳的点：

- Agent B 建议首版不要做 badcase，但用户明确要求“后续要进行 badcase 评估”，因此本轮保留 badcase。
- 为避免过度建设，本轮没有做 replay fixture、eval_cases 独立表和外部 LLMOps 平台。

## 3. 数据结构变化

### 3.1 `llm_interactions`

`span_id` 现在会写入：

- 在 `ObservabilityRecorder.span()` 内会设置 active span。
- `record_llm_interaction()` 记录模型调用时，如果当前 active span 与 trace 一致，则写入对应 `span_id`。
- 如果模型调用不在 span 内，则 `span_id` 允许为空，查询时仍能按 trace 回溯。

### 3.2 `badcases`

新增或补齐字段：

```text
trace_id
plan_id
span_id
llm_interaction_id
category
severity
source
summary
comment
expected_behavior
actual_behavior
input_snapshot_hash
input_ref_json
evidence_refs_json
eval_dataset_name
status
metadata_json
```

字段边界：

- `summary` 是人类可读短摘要，必填，不保存完整 prompt/completion。
- `expected_behavior` 和 `actual_behavior` 用于后续 badcase 评估。
- `input_snapshot_hash`、`input_ref_json`、`evidence_refs_json` 用于后续 replay/eval 定位，不保存完整大快照。
- `eval_dataset_name` 可标记是否进入某个评估集，例如 `failure_cases`。

兼容性：

- 旧的 `comment` 参数仍兼容；如果没有传 `summary`，会用 `comment` 填充 summary。
- 初始化数据库时会检查并补列，避免旧 SQLite 文件缺列后直接崩溃。

## 4. 约束与校验

`record_badcase()` 当前会校验：

- `trace_id` 或 `plan_id` 至少提供一个。
- `plan_id` 能反查到对应 trace。
- `span_id` 必须属于同一个 trace。
- `llm_interaction_id` 必须属于同一个 trace。
- `severity` 只能是 `low`、`medium`、`high`、`critical`。
- `source` 只能是 `user`、`developer`、`auto`、`evaluator`。
- `summary` 不能为空。

这样做的目的不是做复杂平台，而是避免 badcase 记录本身污染后续评估数据。

## 5. CLI 使用方式

查看最近 trace：

```powershell
python -m jiami_crypto_alert.cli --config config/default.yaml trace-list --limit 5
```

查看某次 trace：

```powershell
python -m jiami_crypto_alert.cli --config config/default.yaml trace-show --trace-id <trace_id>
```

默认不会输出：

- `request_json`
- `response_json`
- `raw_decision`

如果本地排障确实要看已脱敏 request/response，可以显式加：

```powershell
python -m jiami_crypto_alert.cli --config config/default.yaml trace-show --trace-id <trace_id> --include-payloads
```

记录 badcase，推荐使用 `plan_id`：

```powershell
python -m jiami_crypto_alert.cli --config config/default.yaml record-badcase `
  --plan-id <plan_id> `
  --category execution_plan_unclear `
  --severity medium `
  --summary "用于回归评估" `
  --source developer `
  --eval-dataset failure_cases
```

记录更精确的 badcase：

```powershell
python -m jiami_crypto_alert.cli --config config/default.yaml record-badcase `
  --trace-id <trace_id> `
  --span-id <span_id> `
  --llm-interaction-id <llm_id> `
  --category grounding_error `
  --severity high `
  --summary "模型引用了不可靠证据" `
  --expected "数据不足时必须 no trade" `
  --actual "输出缺少证据映射"
```

查看 badcase：

```powershell
python -m jiami_crypto_alert.cli --config config/default.yaml badcase-list --limit 20
```

## 6. 安全边界

本轮继续遵守这些边界：

- 不保存 API key、Bark key、token、authorization、passphrase 等密钥。
- 不保存隐藏思维链。
- 默认不展示完整 LLM request/response。
- badcase 不复制 `raw_decision`、完整 prompt、完整 completion。
- analysis 只保存可审计摘要，例如 `reasoning_summary`、`decision_ladder`、`risk_rule_hits`。

当前剩余风险：

- `plan_runs.payload_json.raw_decision` 历史字段仍存在，后续应改为可配置 artifact 或默认 hash + summary。
- `_sanitize()` 主要按 key 名脱敏，如果敏感信息被用户写进普通文本字段，仍可能漏出。
- `--include-payloads` 会展示已脱敏并截断的 request/response，只建议本地排障使用。

## 7. 测试记录

本轮先写失败测试，再实现。

红测暴露的问题：

- `Journal.record_badcase()` 不支持 `plan_id`、`summary`、`source`、`eval_dataset_name`。
- `llm_interactions.span_id` 没有写入，导致 LLM 交互无法挂到具体 span。
- `trace-list` 没有 `span_count` 和 `llm_interaction_count`。
- CLI `record-badcase` 不支持用 `plan_id` 记录 badcase。

验证命令：

```powershell
pytest tests/test_journal_scheduler.py tests/test_runner_cli.py -q
pytest tests/test_journal_scheduler.py tests/test_runner_cli.py tests/test_openai_compatible.py -q
pytest -q
pytest --collect-only -q
```

验证结果：

- 定向测试 `tests/test_journal_scheduler.py tests/test_runner_cli.py`：通过。
- 观测与 OpenAI-compatible 相关测试：通过。
- 全量测试：通过。
- 当前收集到 65 个测试。

## 8. 后续建议

下一步建议按这个顺序继续：

1. 把 `research.search` 拆成 query 级 span，记录每个查询的耗时、失败原因和证据数。
2. 把 timeout/retry/failure_policy 收敛到 StepSpec / StepRunner，统一所有异步任务边界。
3. 把 `raw_decision` 改为默认不入主 journal，只保存 hash + summary，可选写入本地 artifact。
4. 增加 badcase replay/eval：从 `badcases` 生成 eval case，复跑后比较 expected/actual。
5. 增加 trace 导出命令，便于后续 badcase 评审和回归报告生成。
