# 链路层级评估与 LLM 交互观测落地说明

## 1. 结论

本次实现先落地 P0/P1 的最小可控版本，没有做大目录搬迁。

已经完成：

- 生产配置不再默认继承 fixture 行情。
- Parser 严格拒绝字符串布尔、非正过期时间、越界 probability。
- RiskGate 对开仓、触发、反手动作新增 entry trigger 和 invalidation 硬阻断。
- 每次 `PlanRunner.run_once()` 生成 `trace_id`。
- 核心阶段写入 `trace_spans`。
- OpenAI-compatible chat/completions 和 Responses web_search 调用写入 `llm_interactions`。
- `plan_runs.payload_json` 增加 `trace_id`、`analysis` 和 `redaction`。
- LLM 交互默认保存脱敏 payload、hash 和摘要，不保存 API key、不保存隐藏思维链。

仍未完成：

- 尚未大规模拆分 `workflow/`、`agents/`、`rules/` 目录。
- 尚未实现独立 reviewer 并发模式。
- 尚未把所有硬编码规则迁移到 YAML。
- 尚未实现 trace CLI 查询和 eval/replay。

当前目标是先让旧 pipeline 可观测、可回溯、可阻断，再逐步重构为受控 agent-skill workflow。

## 2. 当前落地代码映射

| 能力 | 文件 | 说明 |
|---|---|---|
| Trace / Span / LLM 交互上下文 | `src/crypto_manual_alert/observability.py` | 新增 `ObservabilityRecorder`、`use_observability()`、`record_llm_interaction()` |
| SQLite 表 | `src/crypto_manual_alert/journal.py` | 新增 `traces`、`trace_spans`、`trace_events`、`llm_interactions` |
| 主链路插桩 | `src/crypto_manual_alert/runner.py` | `market.fetch`、`skill.load`、`research.*`、`decision.final`、`parser.strict_json`、`risk.check`、`journal.write`、`notification.send` |
| Final decision LLM 记录 | `src/crypto_manual_alert/skill_runtime.py` | `OpenAICompatibleDecisionEngine.run()` 记录请求/响应摘要、hash、状态 |
| Research/Leader/WebSearch LLM 记录 | `src/crypto_manual_alert/research.py` | planner、leader synthesizer、responses web_search 记录 LLM interaction |
| Parser 安全收紧 | `src/crypto_manual_alert/plan_parser.py` | 严格 bool、TTL、probability |
| RiskGate 安全收紧 | `src/crypto_manual_alert/risk.py` | opening action 必须有 entry trigger 和 invalidation |
| 生产配置修正 | `config/prod.yaml` | 显式 `market_data.provider: okx_public` |

## 3. 链路层级评估

### 3.1 Trigger 层

当前入口仍是：

```text
crypto-alert run-once --symbol ETH-USDT-SWAP
crypto-alert scheduler --symbol ETH-USDT-SWAP
```

已具备：

- 每次触发都会创建 `trace_id`。
- trace 记录 `run_type=manual`、`symbol`、运行状态和最终 action。

不足：

- 还没有 `DecisionRequest` 对象。
- 还没有 `--query`、horizon、position state 结构化入口。
- scheduled query 还没有配置化。

后续优化：

- 增加 `DecisionRequestBuilder`。
- 定时任务从 `scheduled_queries` 配置生成请求。
- trace 记录 `request_id` 和 query 摘要。

### 3.2 Config / Rules 层

已具备：

- `prod.yaml` 显式使用 OKX public 行情。
- 启动时继续禁止 `auto_order_enabled=true`。
- forbidden trade env var 仍然会被拦截。

不足：

- action enum、confidence cap、required points 仍主要在 Python 中。
- prompt 仍有部分硬编码。
- 配置 hash 尚未写入 trace。

后续优化：

- 增加 `rules/*.yaml`。
- 增加 `RulesLoader` 和 `config_hash`。
- 安全边界仍由代码强制，不允许配置关闭。

### 3.3 Market / Skill 层

已具备：

- `market.fetch` span 记录输入 symbol、输出点位名、unavailable。
- `skill.load` span 记录 skill name、hash 和 required references。

不足：

- OKX 请求仍主要由 `market_data.py` 执行，不是通过 `SkillRegistry` 包装 `okx_snapshot.py`。
- `market_data.aggregate_timeout_seconds` 尚未真正包住整组行情请求。
- market endpoint 级 span 还没有拆到每个 OKX endpoint。

后续优化：

- 增加 `SkillRegistry` / `ToolPolicy`。
- 把 `okx_snapshot.py` 包成受控 tool。
- endpoint 级 trace 记录 HTTP 状态、耗时和失败类型。

### 3.4 Research 层

已具备：

- `research.plan` span。
- `research.search` span。
- `evidence.synthesize` span。
- `leader.review` span。
- LLM planner / leader / responses web_search 在 active trace 下写入 `llm_interactions`。

不足：

- `research.search` 当前是组级 span，不是每个 query 一个 span。
- search query 的 retry 和 group deadline 尚未标准化。
- compact reviewer 仍是单次 LLM 多角色输出。

后续优化：

- 每个 search query 单独 span。
- `research_total_seconds` 作为组级 deadline。
- 根据 trace 结果决定是否启用 independent reviewer。

### 3.5 LLM Decision 层

已具备：

- `decision.final` span。
- `llm_interactions` 记录 final decision 的脱敏请求、响应、hash、model、endpoint、status。
- `plan_runs.payload_json.analysis` 记录分析摘要、决策阶梯、证据映射、反向链、数据缺口和风险命中。

不足：

- final decision 的完整 raw completion 仍保存在 `plan_runs.payload_json.raw_decision`。
- prompt version 尚未显式记录。
- `evidence_to_claims` 目前只从 research results 构造初版映射，尚未覆盖 OKX 原生点位。

后续优化：

- raw completion 改为可配置 artifact，默认 hash + summary。
- 增加 prompt version。
- 增加 `evidence_ref` 对 OKX mark/index/order_book 的引用。

### 3.6 Parser / Risk 层

已具备：

- Parser 拒绝非严格 JSON。
- Parser 拒绝字符串数字、字符串 bool、非正 TTL、越界 probability。
- RiskGate 拦截缺 stop、entry、invalidation、核心执行行情、stale、超 confidence cap。
- `risk.check` span 记录 allowed、reasons、warnings。

不足：

- RR、target、order book 深度、position state、flip 二次确认尚未实现。
- `plan_ttl_seconds` 上限尚未在 parser/risk 中统一校验。

后续优化：

- Risk rules 配置化。
- 增加 RR / target / entry quality 校验。
- 增加 position-aware 风控。

### 3.7 Journal / Notification 层

已具备：

- `journal.write` span。
- `notification.send` span。
- `plan_runs` payload 包含 `trace_id`。
- notification 失败仍不改变 verdict。

不足：

- `trace-show` CLI 尚未实现。
- `append_plan_run()` 仍是 `INSERT OR REPLACE`，严格 append 语义尚未修。
- Bark 通知还没有把 `trace_id` 显式放进内容。

后续优化：

- 增加 `trace-list` / `trace-show`。
- plan_runs 改为 append-only 或单独 run_id。
- Bark 内容增加 `trace_id` 和关键 risk reason。

## 4. LLM 交互记录设计

### 4.1 当前记录字段

`llm_interactions` 当前记录：

```text
trace_id
component
provider
model
endpoint
status
input_hash
output_hash
input_summary_json
output_summary_json
request_json
response_json
error_type
error_message
metadata_json
created_at
```

当前组件名：

```text
research.plan
research.web_search
leader.review
decision.final
```

### 4.2 脱敏策略

默认脱敏 key 包含：

```text
api_key
authorization
secret
token
passphrase
device_key
bark
```

策略：

- 只保存脱敏后的 request/response。
- 保存 input/output hash，便于复盘同一输入是否变化。
- 保存 summary，便于不打开大文本也能判断调用意图。
- 单条 payload 最多保存固定长度，超出截断。
- 不保存隐藏 chain-of-thought。

### 4.3 分析内容分层

本次开始在 `plan_runs.payload_json.analysis` 记录：

```json
{
  "reasoning_summary": "...",
  "decision_ladder": [],
  "evidence_to_claims": [],
  "opposing_thesis": "...",
  "data_gaps": [],
  "risk_rule_hits": []
}
```

字段含义：

- `reasoning_summary`：可展示的简体中文分析摘要，优先来自 leader finalizer 或 plan notes。
- `decision_ladder`：final decision 和 risk gate 的阶段结论。
- `evidence_to_claims`：当前 research evidence 到 claim 的初版映射。
- `opposing_thesis`：最强反向理由，对应 `why_not_opposite`。
- `data_gaps`：行情缺口、research 缺口、模型声明缺口。
- `risk_rule_hits`：代码层 hard block 命中。

这不是模型隐藏思维链，而是面向审计和回归的可解释摘要。

## 5. 本次测试覆盖

新增或增强测试覆盖：

- `tests/test_config.py`
  - prod config 必须使用 `okx_public`。
- `tests/test_plan_parser_and_risk.py`
  - 拒绝字符串 `manual_execution_required`。
  - 拒绝 `expires_in_seconds=0`。
  - 拒绝 `probability > 1`。
  - opening action 缺 entry / invalidation 会被 RiskGate 阻断。
- `tests/test_journal_scheduler.py`
  - trace、span、LLM interaction 可写入 SQLite。
  - LLM request 脱敏，不保存 secret。
- `tests/test_runner_cli.py`
  - 成功 run 写入 `trace_id`。
  - `market.fetch`、`decision.final` span 存在。
- `tests/test_openai_compatible.py`
  - final decision LLM 调用在 active trace 下写入 `llm_interactions`。
  - 不保存 API key。

验证命令：

```text
pytest -q
```

## 6. 当前风险

1. 观测已经起步，但还不是完整 LLMOps。
   - 现在能看 trace/span/LLM 摘要。
   - 还不能用 CLI 快速查看，需要直接查 SQLite。

2. raw completion 仍写在 `plan_runs.payload_json.raw_decision`。
   - 这是历史行为。
   - 后续应改为默认 hash + summary，完整 raw 作为可选 artifact。

3. research query 不是逐条 span。
   - 当前 `research.search` 是组级 span。
   - 后续要把每个 query 拆成独立 span，才能分析哪个 query 慢或失败。

4. 当前还没有 `StepSpec` 统一执行器。
   - 这次先做可观测插桩。
   - 后续再把 timeout/retry/failure_policy 放进统一 Step 层。

5. 当前没有把历史 trace 用于 eval。
   - 已经具备 trace 数据基础。
   - 还需要 replay/eval case 抽取。

## 7. 下一步建议

建议下一轮做：

1. 增加 `trace-show` CLI。
2. 把 `research.search` 拆成 query 级 span。
3. 增加 `StepSpec` / `StepResult`，统一 timeout、retry、failure_policy。
4. 把 raw completion 改为可配置 artifact。
5. 增加 `rules/*.yaml`，先迁移 confidence cap、required execution points、opening requirements。

