# 成熟 Eval 旁路测评体系设计

## 1. 结论

本项目需要的是一个**成熟但旁路隔离的 eval 系统**，不是把更多字段塞进现有 journal，也不是把历史 badcase 注入实时交易 prompt。

最终目标：

- 能从生产 trace / badcase 生成可复跑的 eval case。
- 能冻结输入，复跑 baseline / candidate。
- 能用 RuleJudge 判断确定性错误。
- 能用 LLMJudge 判断证据支撑、反证覆盖、过度自信和可执行性。
- 能进入 HumanReview 队列，支持人工复核和仲裁。
- 能生成报告和发布门禁建议。
- 能通过简单前端页面查看 run、case、score、badcase、trace，不再手查 SQLite。
- 不影响现有 `run-once`、`scheduler`、RiskGate、Bark 手动提醒链路。

一句话架构：

```text
生产链路继续实时提醒；eval 链路只读生产 trace/badcase 的脱敏快照，离线复跑、判分、归因、出报告。
```

## 2. 设计原则

### 2.1 旁路隔离

eval 不能进入实时业务主链路。

```text
实时业务链路：
run-once / scheduler
  -> OKX / skill / research / LLM
  -> parser
  -> risk gate
  -> journal
  -> Bark

旁路 eval 链路：
production journal snapshot
  -> EvalCaseBuilder
  -> FrozenInput
  -> ReplayRunner
  -> RuleJudge
  -> LLMJudge
  -> HumanReviewQueue
  -> EvalReport
  -> Streamlit UI
```

硬边界：

- eval 不发送 Bark。
- eval 不写生产 `plan_runs` / `notifications` / `manual_outcomes`。
- eval 不持有 scheduler 的 `JobLock("plan-run")`。
- eval 不读取历史 badcase 作为实时市场证据。
- eval 失败不改变生产 trace 状态。
- eval 不替用户下单，不生成自动交易动作。

### 2.2 冻结输入

成熟 eval 的基础不是“事后重新查最新行情”，而是冻结当时输入。

一个 eval case 必须能回答：

- 当时系统看到了什么行情？
- 当时 research 找到了哪些证据？
- 当时 skill hash、config hash、risk rule version、prompt version 是什么？
- 当时最终输出和风控结果是什么？
- 现在 candidate 版本复跑后有什么差异？

如果没有 frozen input，eval 结果不可比。

### 2.3 规则优先，LLMJudge 辅助

RuleJudge 做确定性判断：

- schema 是否合规。
- 是否违反 manual-only。
- 核心 OKX 行情缺失时是否仍给开仓。
- 数据陈旧是否被阻断。
- 置信度是否超过 cap。
- 是否误触发 Bark。

LLMJudge 做语义判断：

- 证据是否支撑结论。
- 反向根因链是否充分。
- 数据缺口是否诚实表达。
- no trade 是否有真实依据。
- 操作计划是否可手动执行。

LLMJudge 不判断“策略能不能赚钱”，也不能单独决定是否发布。

### 2.4 人工复核不可省

HumanReview 不应看全部样本，只看高价值样本：

- high / critical badcase。
- RuleJudge 与 LLMJudge 冲突。
- LLMJudge 低置信。
- 真实用户反馈不满意。
- 准备进入 golden set 的样本。
- 发布门禁失败样本。

## 3. 当前项目基础

当前已有：

- `traces`、`trace_spans`、`trace_events`、`llm_interactions`、`badcases`。
- `trace-list`、`trace-show`、`record-badcase`、`badcase-list`。
- LLM interaction 可关联 active span。
- `plan_runs.payload_json.analysis` 有可审计摘要。

当前不足：

- `eval_dataset_name` 只是标签，不是 eval case。
- 没有 frozen input。
- 没有 eval runner。
- 没有 score / judge / report。
- 没有 review queue。
- `research.search` 仍是组级 span，不是 query 级 span。
- `raw_decision` 仍在主 journal 中保存。
- 没有前端页面，只能 CLI / SQLite 查看。

## 4. 目录与包结构设计

建议新增以下模块，全部在旁路 eval 子系统内：

```text
src/jiami_crypto_alert/
  eval/
    __init__.py
    store.py                 # EvalStore，独立 SQLite
    schema.py                # EvalCase/EvalRun/EvalScore/HumanReview 数据类
    case_builder.py          # 从 trace/badcase 构建 eval case
    frozen_input.py          # frozen input 生成、hash、脱敏
    replay.py                # ReplayRunner，复跑 parser/risk/decision
    rule_judges.py           # RuleJudge 规则集合
    llm_judge.py             # LLMJudge，OpenAI-compatible
    human_review.py          # Review queue 状态机
    report.py                # JSON/Markdown report
    taxonomy.py              # failure category / judge id 枚举
    guardrails.py            # eval 旁路安全保护
    queries.py               # UI/CLI 复用查询函数
  eval_cli.py                # 独立 CLI 入口
  eval_ui/
    streamlit_app.py         # 简单前端页面
```

配置：

```text
config/eval.yaml
```

配置示例：

```yaml
eval:
  enabled: true
  data_dir: data/eval
  eval_db_path: data/eval/jiami-eval.db
  source_journal_path: data/jiami-alert.db
  default_dataset: failure_cases
  forbid_notifications: true
  forbid_live_market_fetch: true
  forbid_live_search: true
  save_full_prompt: false
  save_full_completion: false
  max_artifact_chars: 12000

rule_judge:
  enabled: true
  fail_on_critical: true

llm_judge:
  enabled: true
  provider: openai_compatible
  base_url_env: OPENAI_BASE_URL
  api_key_env: OPENAI_API_KEY
  model_env: OPENAI_MODEL
  temperature: 0
  timeout_seconds: 300
  max_tokens: 1200
  max_cases_per_run: 20
  advisory_until_calibrated: true

ui:
  provider: streamlit
  host: 127.0.0.1
  port: 8501
```

## 5. 独立 Eval 数据模型

eval 数据建议使用独立 SQLite：`data/eval/jiami-eval.db`。

### 5.1 `eval_cases`

```text
case_id TEXT PRIMARY KEY
dataset_name TEXT NOT NULL
source_trace_id TEXT
source_badcase_id INTEGER
created_at TEXT NOT NULL
case_version TEXT NOT NULL
symbol TEXT
horizon TEXT
failure_category TEXT
severity TEXT
expected_behavior TEXT NOT NULL
expected_behavior_type TEXT NOT NULL
frozen_input_hash TEXT NOT NULL
frozen_input_ref TEXT NOT NULL
input_summary_json TEXT NOT NULL
metadata_json TEXT NOT NULL
status TEXT NOT NULL
```

`expected_behavior_type` 建议枚举：

```text
schema_valid
risk_block
grounding
data_gap_handling
manual_only
chinese_output
no_bark
no_production_write
```

### 5.2 `eval_artifacts`

```text
artifact_id TEXT PRIMARY KEY
case_id TEXT
eval_run_id TEXT
artifact_type TEXT NOT NULL
content_hash TEXT NOT NULL
content_summary_json TEXT NOT NULL
content_ref TEXT
redaction_status TEXT NOT NULL
created_at TEXT NOT NULL
```

默认不保存完整 prompt / completion。

允许保存：

- frozen snapshot 摘要。
- research evidence 摘要。
- parsed plan。
- verdict。
- output hash。
- judge structured output。

禁止保存：

- API key。
- Bark key。
- Authorization。
- passphrase。
- hidden chain-of-thought。
- 完整敏感 prompt。
- 完整 completion。

### 5.3 `eval_runs`

```text
eval_run_id TEXT PRIMARY KEY
dataset_name TEXT NOT NULL
candidate_version TEXT NOT NULL
baseline_version TEXT
started_at TEXT NOT NULL
ended_at TEXT
status TEXT NOT NULL
case_count INTEGER NOT NULL
summary_json TEXT NOT NULL
report_ref TEXT
metadata_json TEXT NOT NULL
```

### 5.4 `eval_scores`

```text
score_id TEXT PRIMARY KEY
eval_run_id TEXT NOT NULL
case_id TEXT NOT NULL
judge_name TEXT NOT NULL
judge_type TEXT NOT NULL
score REAL
passed INTEGER NOT NULL
severity TEXT NOT NULL
failure_category TEXT
reason_summary TEXT NOT NULL
evidence_refs_json TEXT NOT NULL
needs_human_review INTEGER NOT NULL
created_at TEXT NOT NULL
```

### 5.5 `eval_findings`

用于聚合后的问题归因：

```text
finding_id TEXT PRIMARY KEY
eval_run_id TEXT NOT NULL
category TEXT NOT NULL
severity TEXT NOT NULL
title TEXT NOT NULL
summary TEXT NOT NULL
affected_case_ids_json TEXT NOT NULL
suggested_action TEXT
status TEXT NOT NULL
created_at TEXT NOT NULL
```

### 5.6 `human_reviews`

```text
review_id TEXT PRIMARY KEY
case_id TEXT NOT NULL
eval_run_id TEXT
score_id TEXT
status TEXT NOT NULL
reviewer TEXT
decision TEXT
failure_category TEXT
comment TEXT
created_at TEXT NOT NULL
updated_at TEXT NOT NULL
```

状态机：

```text
pending -> confirmed
pending -> rejected
pending -> needs_arbitration
needs_arbitration -> confirmed
needs_arbitration -> rejected
confirmed -> closed
rejected -> closed
```

## 6. EvalCaseBuilder

输入：

- `trace_id`
- `badcase_id`
- `dataset_name`
- `expected_behavior`
- `expected_behavior_type`

输出：

- `eval_cases` 一条记录。
- `eval_artifacts` 中的 frozen input 引用。

构建规则：

1. 从生产 journal 只读 trace。
2. 读取 `plan_run.parsed_plan`、`verdict`、`analysis`、`snapshot`、`research` 摘要。
3. 读取 skill hash、model、trace spans、LLM interaction hash。
4. 生成 frozen input JSON 文件到 `data/eval/artifacts/cases/<case_id>.json`。
5. 对 frozen input 计算 sha256。
6. 严格脱敏，不复制 `raw_decision`。

frozen input 结构：

```json
{
  "source": {
    "trace_id": "...",
    "plan_id": "...",
    "badcase_id": 1
  },
  "versions": {
    "case_version": "v1",
    "skill_hash": "...",
    "config_hash": "...",
    "risk_rule_version": "...",
    "prompt_version": "...",
    "model": "gpt-5.5"
  },
  "input": {
    "symbol": "ETH-USDT-SWAP",
    "market_snapshot": {},
    "research_summary": {},
    "skill_summary": {}
  },
  "observed_output": {
    "parsed_plan": {},
    "verdict": {},
    "analysis": {}
  },
  "expected": {
    "behavior_type": "risk_block",
    "behavior": "核心 OKX 行情缺失时必须 no trade 或 risk blocked"
  }
}
```

## 7. ReplayRunner

### 7.1 复跑模式

`cheap`：

- 不调用 LLM。
- 只复跑 parser / risk / RuleJudge。
- 适合每次提交都跑。

`decision`：

- 使用 frozen input 重新构造 prompt packet。
- 调用 candidate decision engine。
- 不抓实时行情、不做实时 search。
- 复跑 parser / risk / RuleJudge / LLMJudge。

`judge-only`：

- 不复跑 decision。
- 对 observed output 运行 RuleJudge 和 LLMJudge。
- 适合审历史 trace 质量。

### 7.2 禁止行为

ReplayRunner 必须硬编码：

- `notification.enabled=false`
- 使用 `NoopNotificationSink`
- 不写生产 journal
- 不访问 OKX trade / withdraw key
- 不启动 scheduler
- 不调用 Bark
- 不实时抓 OKX / web search，除非命令显式使用 `--allow-live-refresh`，且默认禁用

### 7.3 baseline / candidate

每次 eval run 可以有：

- `baseline_version`
- `candidate_version`
- `dataset_name`
- `repeat_count`

LLM 非确定性处理：

- `temperature=0`
- 可配置重复次数。
- 报告通过率和失败样例，不宣称单次结果绝对稳定。

## 8. RuleJudge 设计

RuleJudge 输出统一结构：

```json
{
  "judge_name": "risk.core_execution_points",
  "judge_type": "rule",
  "passed": false,
  "severity": "critical",
  "failure_category": "risk_rule_block",
  "reason_summary": "开仓动作缺少 OKX mark/index/order_book，必须阻断。",
  "evidence_refs": ["input.market_snapshot.points", "observed_output.parsed_plan.main_action"],
  "needs_human_review": false
}
```

### 8.1 必做规则

Schema：

- strict JSON。
- 必填字段齐全。
- 数值字段类型正确。
- action enum 合法。
- `manual_execution_required=true`。
- `expires_in_seconds > 0`。

交易边界：

- `auto_order_enabled=false`。
- 开仓 / trigger / flip 必须有 `entry_trigger`、`stop_price`、`invalidation`。
- `max_leverage <= 2`。
- `risk_pct <= max_risk_per_trade_pct`。

数据边界：

- 开仓类动作必须有 OKX `mark`、`index`、`order_book`。
- 数据陈旧必须阻断或降级。
- search-derived 证据不能替代 OKX 原生执行事实。
- 工具全部超时时不得给明确开仓方向。

置信度：

- 命中 confidence cap 时，`probability` 不得超过 cap。
- 数据缺口大时不得输出高置信。

副作用：

- eval run 不得新增 `notifications`。
- eval run 不得写生产 `plan_runs`。
- eval artifact 不得包含 `raw_decision`。
- eval artifact 不得包含 secret。

表达：

- 禁止“稳赚”“必涨”“无风险”等表达。
- 用户可见解释应是简体中文。

## 9. LLMJudge 设计

LLMJudge 是自研评估器，不是第三方强依赖。

调用方式：

```text
EvalCase + observed/candidate output + evidence summary
  -> build judge prompt
  -> OpenAI-compatible /v1/chat/completions
  -> strict JSON score
  -> eval_scores
```

### 9.1 LLMJudge 评估维度

建议首批 5 个 judge：

1. `evidence_grounding`
   - 结论是否被 frozen evidence 支撑。
2. `counter_thesis_coverage`
   - 是否充分讨论反向根因链。
3. `data_gap_honesty`
   - 是否诚实表达数据缺口和不确定性。
4. `execution_clarity`
   - 操作计划是否可手动执行，是否有触发/止损/失效。
5. `overconfidence`
   - 是否在数据不足或冲突时过度自信。

### 9.2 LLMJudge 输出 schema

```json
{
  "score": 0.0,
  "passed": false,
  "failure_categories": ["grounding_error"],
  "severity": "high",
  "reason_summary": "模型使用 search-derived 证据支持开仓，但 OKX 原生执行事实缺失。",
  "evidence_refs": ["input.research_summary", "observed_output.parsed_plan"],
  "needs_human_review": true,
  "confidence": 0.72
}
```

### 9.3 LLMJudge 约束

- 不要求输出 hidden chain-of-thought。
- 只要短 rationale 和 evidence refs。
- `temperature=0`。
- 固定 judge prompt version。
- 固定 model。
- 单次 eval run 记录 model、prompt hash、input hash、output hash。
- 初期结果为 advisory，不直接作为发布阻断。
- 经过人工校准后，部分高一致性 judge 才可进入 release gate。

## 10. HumanReview 设计

HumanReview 的目的不是替代自动化，而是维护标签质量。

进入 review queue 的条件：

- RuleJudge critical fail。
- LLMJudge high / critical。
- LLMJudge `confidence < 0.65`。
- RuleJudge 与 LLMJudge 冲突。
- 用户手工标注 high / critical badcase。
- 准备进入 `golden_cases`。

Review 页面需要支持：

- 查看 source trace。
- 查看 frozen input summary。
- 查看 RuleJudge / LLMJudge 分数。
- 选择 taxonomy。
- 确认 / 驳回 / 需仲裁 / 关闭。
- 将 confirmed review 转成 eval case 或 policy candidate。

## 11. Failure Taxonomy

固定枚举，禁止自由漂移：

```text
schema_error
manual_only_violation
risk_rule_block
over_confidence
stale_or_missing_data
source_quality_error
grounding_error
planner_error
root_cause_shallow
opposite_chain_missing
execution_plan_unclear
bad_price_level
tool_timeout
tool_error
model_timeout
model_error
notification_error
secret_leak
raw_payload_leak
history_contamination
```

每个 taxonomy 必须有：

- 定义。
- 示例。
- 是否可由 RuleJudge 自动判定。
- 是否需要 LLMJudge。
- 是否需要人工复核。

## 12. 报告与发布门禁

### 12.1 EvalReport

每次 eval run 输出：

```text
data/eval/reports/<eval_run_id>.json
data/eval/reports/<eval_run_id>.md
```

报告内容：

- eval run id。
- dataset。
- baseline / candidate。
- case count。
- 总通过率。
- critical / high fail 数。
- RuleJudge 失败分布。
- LLMJudge 失败分布。
- 需要人工复核数量。
- Top failure categories。
- 成本 / 耗时。
- 失败样本清单。
- 生产隔离证明。
- 是否建议发布。

### 12.2 Release Gate

初始 gate：

- critical RuleJudge fail 必须为 0。
- eval 期间 Bark 新增记录必须为 0。
- eval 期间生产 `plan_runs` 新增/覆盖必须为 0。
- secret scan 必须通过。
- high severity badcase 不得复发。
- schema valid rate >= 99%。
- manual-only compliance = 100%。
- core execution data rule compliance = 100%。

LLMJudge gate 初期只 advisory。

等人工校准后再设：

- evidence grounding average >= 阈值。
- counter thesis coverage 不得回退。
- overconfidence fail rate 不得上升。

## 13. 前端页面设计

### 13.1 方案选择

对比：

| 方案 | 适合度 | 优点 | 风险 |
|---|---:|---|---|
| Streamlit 自建 | 高 | Python 单栈，最快落地，直接读 SQLite，适合本地 eval 浏览 | 多用户和权限弱，UI 复杂后维护一般 |
| FastAPI + 静态前端 | 中 | API 边界清晰，可扩展权限和部署 | 当前偏重，需要新增前端工程或手写 JS |
| Langfuse / Phoenix | 中，后置 | 现成 LLM trace/eval UI | 需要额外服务和导出适配，不能零成本接当前 SQLite |

推荐：

```text
首版：Streamlit 本地页面
中期：抽象 queries.py，未来可包 FastAPI
后期：可选 exporter 到 Langfuse / Phoenix
```

### 13.2 Streamlit 页面结构

入口：

```powershell
streamlit run src/jiami_crypto_alert/eval_ui/streamlit_app.py
```

页面：

1. Overview
   - 最近 eval runs。
   - 通过率趋势。
   - critical/high fail。
   - 待人工复核数。

2. Eval Runs
   - run 列表。
   - baseline/candidate。
   - dataset。
   - pass rate。
   - judge 分布。
   - 点击查看 run detail。

3. Cases
   - dataset 过滤。
   - severity 过滤。
   - failure category 过滤。
   - case detail。
   - frozen input summary。

4. Scores
   - RuleJudge / LLMJudge 分数。
   - failed rules。
   - reason summary。
   - evidence refs。

5. Trace / Badcase
   - source trace 摘要。
   - spans 时间线。
   - LLM interaction 摘要。
   - badcase 列表。

6. Human Review
   - 待审列表。
   - 确认 / 驳回 / 需仲裁 / 关闭。
   - taxonomy 选择。
   - comment。

7. Reports
   - Markdown report 渲染。
   - JSON 下载。

### 13.3 查询层要求

Streamlit 不直接写复杂 SQL。

新增 UI 无关查询层：

```python
list_eval_runs(filters) -> list[dict]
get_eval_run_detail(eval_run_id) -> dict
list_eval_cases(filters) -> list[dict]
get_eval_case_detail(case_id) -> dict
list_eval_scores(eval_run_id, case_id=None) -> list[dict]
list_human_reviews(status=None) -> list[dict]
get_source_trace_summary(trace_id) -> dict
```

这样未来可以平滑迁移：

```text
queries.py -> Streamlit
queries.py -> FastAPI
queries.py -> Langfuse/Phoenix exporter
```

## 14. CLI 设计

独立入口：

```powershell
python -m jiami_crypto_alert.eval_cli <command>
```

命令：

```text
eval init
eval create-case --trace-id ... --dataset failure_cases --expected ... --type risk_block
eval create-case --badcase-id ...
eval run --dataset failure_cases --mode cheap
eval run --dataset failure_cases --mode judge-only --with-llm-judge
eval report --eval-run-id ...
eval list-runs
eval show-run --eval-run-id ...
eval list-cases --dataset failure_cases
eval review-list --status pending
eval review-update --review-id ... --status confirmed --category grounding_error --comment ...
eval ui
```

所有 eval 命令默认：

- 不发 Bark。
- 不写生产 journal。
- 不拉实时行情。
- 不拉实时 web search。
- 不保存完整 prompt / completion。

## 15. 与第三方工具的关系

### 15.1 不作为首版强依赖

Langfuse / Phoenix / LangSmith 的价值在于：

- trace UI。
- dataset / experiment。
- scoring。
- prompt 管理。
- 团队协作。

但当前项目已有 SQLite Trace Ledger，首要问题是：

- frozen input。
- replay。
- judge。
- report。
- 不影响业务。

所以第三方平台先不作为强依赖。

### 15.2 后续 exporter

后续可以新增：

```text
exporters/
  langfuse_exporter.py
  phoenix_exporter.py
  otlp_exporter.py
```

导出对象：

- trace。
- span。
- LLM interaction summary。
- eval case。
- eval score。
- report summary。

导出失败不影响本地 eval。

## 16. 安全和隔离验收

必须通过：

1. eval run 后，生产 `notifications` 无新增记录。
2. eval run 后，生产 `plan_runs` 无新增或覆盖记录。
3. eval run 后，手机不会收到 Bark。
4. 设置 `OKX_TRADE_API_KEY` 或 `OKX_WITHDRAW_API_KEY` 时，eval 直接失败。
5. eval artifact 全文扫描不含 OpenAI key、Bark key、Authorization、passphrase。
6. eval artifact 不含 `raw_decision` 字段。
7. eval artifact 不含 hidden chain-of-thought。
8. 实时 `run-once` prompt 不包含历史 badcase。
9. LLMJudge 失败不会改变生产业务结果。
10. Streamlit 页面默认不展示完整 request/response。

## 17. 分阶段实施计划

### P0：正式设计和配置

产出：

- 本文档。
- `config/eval.yaml` 草案。
- eval taxonomy。

不写业务代码。

### P1：EvalStore + EvalCase + RuleJudge

产出：

- 独立 eval SQLite。
- `eval init`。
- `eval create-case`。
- RuleJudge。
- JSON/Markdown report。

验收：

- 从 badcase 创建 case。
- 跑 cheap eval。
- 生成报告。
- 不影响生产 journal 和 Bark。

### P2：ReplayRunner

产出：

- frozen input replay。
- baseline/candidate 对比。
- `judge-only` 和 `cheap` 模式稳定。

验收：

- 同一 frozen input 可重复评估。
- 不实时抓行情或 web search。
- 报告能显示版本差异。

### P3：LLMJudge

产出：

- 5 个 LLMJudge rubric。
- strict JSON judge output。
- LLMJudge score 写入 eval_scores。
- 低置信 / 高严重进入 HumanReview。

验收：

- LLMJudge 不保存隐藏思维链。
- judge 结果可追溯到 evidence refs。
- LLMJudge 成本和耗时可统计。

### P4：HumanReview + Streamlit UI

产出：

- review queue。
- Streamlit 页面。
- run/case/score/badcase/trace/review/report 查看。

验收：

- 不用查数据库即可完成基本复核。
- 人工确认能更新 review 状态。
- confirmed review 可生成或更新 eval case。

### P5：Release Gate + Exporter

产出：

- 发布门禁规则。
- CI 或本地命令运行 eval。
- 可选 Langfuse/Phoenix/OTLP exporter。

验收：

- 改 prompt/skill/risk 前后能比较。
- critical fail 阻断发布建议。
- exporter 失败不影响本地 eval。

## 18. 不做事项

当前不做：

- 不重写主业务 runner。
- 不把 eval 挂进 scheduler。
- 不让 eval 发送 Bark。
- 不做自动交易。
- 不让 LLMJudge 判断收益。
- 不把 badcase 注入实时 prompt。
- 不保存完整敏感 prompt/completion。
- 不把 Langfuse/Phoenix 作为首版强依赖。
- 不做复杂权限系统。

## 19. 多 Agent 对抗审查采纳

本方案采纳了三个只读审查 Agent 的结论：

1. 成熟度审查：
   - eval 必须独立 CLI、独立 DB、独立 run_type。
   - 不能复用 prod 通知路径。
   - 不能写生产 `plan_runs`。
   - LLMJudge 不能替代 RuleJudge 和 HumanReview。

2. UI 审查：
   - 首版推荐 Streamlit。
   - 查询层必须独立，不能在 UI 内散落 SQL。
   - FastAPI / Langfuse / Phoenix 后置。

3. 安全审查：
   - eval 必须 Noop 通知。
   - eval artifact 不复制 `raw_decision`。
   - 不保存隐藏思维链。
   - badcase 不进入实时 prompt。

## 20. 最终建议

本项目应该建设一个成熟的旁路 eval 系统，但落地顺序不能反过来。

优先级：

```text
EvalStore / EvalCase / FrozenInput
  -> RuleJudge
  -> ReplayRunner
  -> Report
  -> LLMJudge
  -> HumanReview
  -> Streamlit UI
  -> Release Gate
  -> Third-party exporter
```

这样既能达到成熟 eval 的目标，又不会破坏现有手动提醒业务。
