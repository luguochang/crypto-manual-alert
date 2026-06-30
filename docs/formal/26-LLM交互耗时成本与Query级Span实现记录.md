# LLM 交互耗时成本与 Query 级 Span 实现记录

## 1. 背景

前一版 trace 页面已经能看到 trace、span、脱敏 LLM request/response，但仍有三个问题：

1. `llm_interactions` 只有 payload/hash/summary，缺少单次模型调用的耗时、token、finish reason、retry 和成本字段。
2. `research.search` 只有一个总 span，无法定位是哪一条 web search query 慢、失败或没有结果。
3. `execute_research()` 使用线程池并发，`ContextVar` 不会自动进入 worker，导致 worker 内部的 LLM web search 交互可能静默不记录，或无法关联到具体 query span。

本轮目标不是改交易决策逻辑，而是补齐可观测底座：以后每个结论都能回到具体 trace、span、LLM 调用和 query。

## 2. 已完成改造

### 2.1 LLM 交互一等观测字段

`llm_interactions` 新增字段：

| 字段 | 语义 |
| --- | --- |
| `duration_ms` | 单次 HTTP LLM 调用耗时，成功和失败都会尽量记录。 |
| `prompt_tokens` | OpenAI Chat Completions 的 `usage.prompt_tokens`，Responses API 映射 `usage.input_tokens`。 |
| `completion_tokens` | OpenAI Chat Completions 的 `usage.completion_tokens`，Responses API 映射 `usage.output_tokens`。 |
| `total_tokens` | `usage.total_tokens`。 |
| `finish_reason` | Chat Completions 的 `choices[0].finish_reason`；Responses API 没有时为空。 |
| `retry_count` | 当前调用实际重试次数；当前实现没有 LLM retry loop，因此为 `0`。 |
| `cost_usd` | 预留成本字段。没有模型价格配置时保持 `NULL`，不写错误成本。 |

迁移方式：

- 新库：建表 SQL 直接包含字段。
- 旧库：`Journal._init_db()` 对 `llm_interactions` 调用 `_ensure_columns()`，服务器已有 SQLite 文件会自动补列。
- 历史行：新字段允许为空；`retry_count` 使用 `INTEGER NOT NULL DEFAULT 0`。

### 2.2 LLM telemetry 提取模块

新增 `src/crypto_manual_alert/llm_telemetry.py`：

- `extract_chat_completion_telemetry()`
  - 提取 `usage.prompt_tokens`
  - 提取 `usage.completion_tokens`
  - 提取 `usage.total_tokens`
  - 提取 `choices[0].finish_reason`
- `extract_responses_telemetry()`
  - 映射 `usage.input_tokens -> prompt_tokens`
  - 映射 `usage.output_tokens -> completion_tokens`
  - 提取 `usage.total_tokens`

成本没有硬编码。原因是中转站、模型版本、计费规则可能变化，错误成本比空值更危险。后续如果要做成本统计，应先增加可配置 pricing 表和 `pricing_version`。

### 2.3 HTTP LLM 调用耗时记录

已覆盖的调用点：

- `OpenAICompatibleDecisionEngine.run()`
  - component: `decision.final`
  - endpoint: `/v1/chat/completions`
- `OpenAICompatibleResearchPlanner.plan()`
  - component: `research.plan`
  - 通过 `_post_chat_completion()` 记录
- `OpenAICompatibleLeaderResearchSynthesizer.synthesize()`
  - component: `leader.review`
  - 通过 `_post_chat_completion()` 记录
- `ResponsesWebSearchAdapter.search()`
  - component: `research.web_search`
  - endpoint: `/v1/responses`
  - metadata 保留 `query_name`

成功路径记录 usage/finish reason；失败路径至少记录 `duration_ms`、`error_type`、`error_message`。

### 2.4 Query 级并发 span

`execute_research()` 保持线程池并发，不把 query 串行化。

新增可选参数：

```python
execute_research(
    plan,
    adapter,
    max_workers=4,
    recorder=recorder,
    trace_id=trace_id,
    parent_span_id=outer_span_id,
)
```

当传入 `recorder` 和 `trace_id` 时，每个 query worker 会创建独立 span：

- `span_name`: `research.search.query`
- `span_type`: `research.search.query`
- `metadata.query_name`: query 名称
- `metadata.required`: 是否 required
- `output_summary.result_count`: 结果数量
- 出错时 span status 为 `error`，同时 `ResearchAudit.unavailable` 保持原有降级语义。

`runner.py` 仍保留外层 `research.search` 总 span，并把该 span 的 `span_id` 作为 `parent_span_id` 传给 query span。这样页面既能看总耗时，也能看每条 query。

### 2.5 线程池中的 LLM 关联

因为 Python `ContextVar` 不会自动传播到 `ThreadPoolExecutor` worker，本轮在 `_run_research_query()` 内显式：

1. `use_observability(recorder, trace_id)`
2. `recorder.span(... query span ...)`
3. 调用 `adapter.search(query)`

这样 `ResponsesWebSearchAdapter.search()` 内部的 `record_llm_interaction()` 会绑定到当前 query span，而不是丢失，也不会错误挂到外层 `research.search` 总 span。

### 2.6 前端 trace 详情页

`frontend/src/lib/schemas/runs.ts` 显式建模：

- span: `parent_span_id`、`metadata`、`error_type`
- LLM interaction: `span_id`、`created_at`、`endpoint`、`duration_ms`、tokens、`cost_usd`、`finish_reason`、`retry_count`、`metadata`

`frontend/src/app/runs/[traceId]/page.tsx` 新增展示：

- LLM 已知 token 总数
- 已知成本和缺失成本条数
- 每条 LLM 调用 header 展示：
  - `#id`
  - component
  - provider/model
  - status
  - duration
  - total tokens
- 展开后展示：
  - linked span
  - endpoint
  - created_at
  - finish reason
  - retry count
  - prompt/completion token
  - cost
  - input/output hash
  - metadata
  - 脱敏 request/response payload

## 3. Eval 回归样本补充

`EvalCaseBuilder` 的 frozen summary 已补充 LLM 观测字段：

- `span_id`
- `endpoint`
- `duration_ms`
- `prompt_tokens`
- `completion_tokens`
- `total_tokens`
- `cost_usd`
- `finish_reason`
- `retry_count`

后续 badcase 进入 eval dataset 后，可以判断问题是否来自：

- 某轮 LLM 超时或极慢；
- usage 缺失；
- `finish_reason` 异常；
- 某个 query span 失败或无结果；
- web search 的 LLM 交互没有绑定 query。

## 4. 仍未完成

本轮没有做以下内容：

1. 模型价格配置和 `pricing_version`。
   - 原因：没有可靠价格表时不应硬编码成本。
2. reviewer 角色级 span。
   - 当前 `leader.review` 仍是一个 LLM 调用，返回内部多个 reviewer key。
   - 后续如果把 bull/bear/data_quality/execution_risk 拆成真正并发 agent，再给每个 reviewer 独立 span。
3. 完整 replay/frozen input 重放。
   - 当前 eval case 已携带更多观测字段，但还没有做到一键按历史输入重放整条链路。
4. 在线自我改进闭环。
   - 现在是记录和评测入口，不会自动修改 prompt 或配置。

## 5. 验收命令

本轮已使用的聚焦验收命令：

```powershell
python -m pytest tests\test_journal_scheduler.py tests\test_openai_compatible.py tests\test_research_fallback.py tests\test_api_runs.py tests\test_query_repository.py tests\test_runner_cli.py -q
```

前端类型检查：

```powershell
cd frontend
npm run typecheck
```

最终合并前还需要执行完整本地检查：

```powershell
python tests\run_local_checks.py
```

## 6. 设计取舍

1. `duration_ms/tokens/finish_reason` 做成一等列，不放在 `metadata_json`。
   - 方便 trace 页面、eval、后续统计直接查询。
2. `cost_usd` 允许为空。
   - 空值表示未配置 pricing 或网关没有足够 usage，不等于 0 成本。
3. query span 在 worker 内创建。
   - 避免主线程串行等待 query；
   - 避免 `ContextVar` 在线程池中丢失；
   - 避免 web search LLM interaction 无 `span_id`。
4. `execute_research()` 的观测参数可选。
   - 单元测试和纯 research 调用仍能无 Journal 运行；
   - runner 生产链路传入 recorder/trace_id 后获得完整观测。
