# LLM 检索规划与 Web 降级方案

## 背景

上一版流程在 OKX public 行情全部超时时，只把缺口传给最终决策模型。
模型可以判断“数据不足”，但程序没有继续执行 web fallback，因此最终只能输出 `no trade`。

这不是模型能力不足，而是编排层没有把“应该查什么”变成“真的去查”。
OpenAI-compatible `/v1/chat/completions` 默认只是一轮文本生成，除非中转站显式提供 tool calling / web search，否则模型本身不会自动浏览网页。

## 目标

v1.1 增加一条可控降级链：

```text
OKX / skill script
  -> 若核心数据缺失或 stale
  -> Leader 生成检索计划(static|llm)
  -> 程序并发执行 WebSearchAdapter / 数据源查询
  -> EvidenceSynthesizer 合成结构化证据
  -> Leader 汇总证据与四角色对抗审查(static|llm)
  -> FinalDecision 输出 strict JSON
  -> RiskGate 校验
  -> Journal + Bark
```

## 设计原则

- 大模型负责判断检索方向、解释根因、做对抗审查。
- 程序负责实际执行检索、结构化证据、标注来源、执行风控和留审计。
- 不假设模型 API 一定有浏览器。
- 不把搜索结果当成交易所原生 mark/index/order book 的完全替代。
- web-derived / search-derived 数据必须进入 confidence cap 或 warning。
- 仍然不自动下单。

## 新模块

### 1. ResearchPlanner

输入：
- 当前 `MarketSnapshot`
- 缺失字段
- stale 字段
- skill context
- symbol / horizon

输出 `ResearchPlan`：

```json
{
  "queries": [
    {
      "name": "eth_perp_price",
      "query": "ETH-USDT-SWAP mark price OKX ETH perpetual latest",
      "purpose": "recover price context when OKX timeout",
      "required": true
    }
  ],
  "reason": "OKX core endpoints timed out; need price, funding, OI, liquidation and macro fallback."
}
```

首版支持两种规划模式：
- `static`：由代码按缺失字段生成固定查询，稳定、可测试。
- `llm`：由 OpenAI-compatible `/v1/chat/completions` 生成查询计划，失败时回落到 `static`，并把 fallback 原因写入 plan reason。

### 2. WebSearchAdapter

首版提供可插拔接口：

```text
SearchAdapter.search(query) -> SearchResult[]
```

首选实现：
- `responses_web_search`：调用 OpenAI-compatible `/v1/responses`，启用 `tools: [{"type": "web_search"}]`，让模型执行实时检索并返回带来源的研究摘要。

兜底实现：
- `disabled`：不执行搜索，只记录不可用。
- `fixture`：测试用。
- `duckduckgo_html`：轻量网页检索，结果只作为 search-derived 摘要。

后续可扩展：
- Brave Search API
- SerpAPI
- Tavily
- 自建浏览器 MCP

### 3. EvidenceSynthesizer

职责：
- 把 OKX snapshot 和搜索结果合并。
- 不覆盖 exchange-native 字段。
- 将搜索结果写入 `MarketSnapshot.points` 的补充字段，例如：
  - `web_eth_price_context`
  - `web_derivatives_context`
  - `web_macro_context`
- 将来源标注为 `search-derived`。
- 若 mark/index/order book 仍缺失，保留 confidence cap。

### 4. LeaderResearchSynthesizer / AdversarialReview

研究阶段采用 leader agent 编排：

```text
Leader
  -> 根据缺口拆分 research tasks
  -> 并发执行 researcher tasks
  -> 汇总证据、冲突、缺口、来源质量
  -> 输出 leader_summary
```

对抗审查阶段至少包含四个角色：

```text
bull reviewer: 多头根因链和确认条件
bear reviewer: 空头根因链和确认条件
data-quality reviewer: 数据来源、时效、冲突、crowding 风险
execution-risk reviewer: 入场、止损、滑点、事件风险、是否可执行
leader finalizer: 汇总为最终 evidence brief
```

首版可以把四角色审查压缩在同一次 `/v1/chat/completions` 调用中完成，但 prompt 必须显式要求四角色输出，journal 必须记录 `leader_summary`。
若 `leader_mode=llm` 调用失败，系统必须回落到 static reviewer，并在 `leader_summary.leader_finalizer.llm_leader_fallback` 和 `research.unavailable` 中记录原因。

## Runner 流程变化

原流程：

```text
fetch_snapshot -> build_prompt_packet -> final model -> parser -> risk
```

新流程：

```text
fetch_snapshot
  -> load crypto-macro-decision skill context
  -> if core missing or stale: plan_research
  -> execute search adapters concurrently
     -> preferred: Responses API web_search
     -> fallback: DuckDuckGo / external search API
  -> synthesize evidence
  -> leader synthesize evidence + adversarial review
  -> build prompt packet with evidence + research audit + leader_summary
  -> final model
  -> strict parser
  -> risk gate
  -> journal
  -> notify
```

## 风控要求

- 只要 mark/index/order book 仍缺失，不能把 search-derived 数据当成完全替代。
- search-derived 衍生品数据默认 confidence cap 不高于 `0.58`。
- 搜索失败不能导致程序崩溃；应记录 unavailable 并继续走 final decision。
- `responses_web_search` 必须记录 `tool_usage.web_search.num_requests`；如果为 0，应视为未实际检索。
- LLM planner 和 LLM leader reviewer 不负责真实浏览；真实浏览只通过配置的 `SearchAdapter` 执行。
- final decision 输出仍必须是单一 `DecisionPlan` strict JSON。
- `main_action` 仍只能是枚举值。
- 开仓、触发、翻仓动作缺少 mark/index/order book 时，RiskGate 必须 hard block。
- candles 的 stale 阈值按 `candle_bar + stale_market_data_seconds` 判断，不能用 ticker 级 120 秒阈值误杀当前 K 线。

## 超时与耗时策略

多 agent 根因链分析以结果质量优先，整轮任务允许 10 到十几分钟。

配置语义：

- `research.request_timeout_seconds`：单个研究阶段外部请求超时，包括 LLM planner、每个 researcher web search、LLM leader reviewer。推荐 300 秒。
- `research.max_workers`：并发 researcher 数量。推荐 2 到 4，避免中转站或搜索工具被打爆。
- `decision.timeout_seconds`：最终决策模型单次请求超时。推荐 900 到 1200 秒。
- `scheduler.job_timeout_seconds`：整轮任务预算或外部 watchdog 参考值。推荐 1800 秒。

不要把整轮任务硬限制为 60 秒。若需要防止无限挂起，应限制单个外部请求，并用 job lock 防止调度并发重入。

## 审计要求

Journal payload 必须记录：
- `research_plan`
- `search_results`
- `leader_summary`
- `evidence_snapshot`
- `skill_hash`
- `raw_decision`
- `parsed_plan`
- `risk_verdict`
- `notification_result`

## 首版不做

- 不接自动交易。
- 不把网页结果写成长期记忆。
- 不做动态 skill registry。
- 不做任意脚本工具暴露。
- 不默认相信模型自己已经完成 web search。

## 验收标准

1. 当 OKX 全部超时时，runner 会生成 research plan 并并发调用 search adapter。
2. 当核心数据 stale 时，runner 也会进入 research fallback。
3. search-derived 结果会进入 prompt packet 和 journal。
4. leader agent 会基于并发结果输出 `leader_summary`，包含 bull / bear / data-quality / execution-risk 四角色审查。
5. 最终模型可以基于 fallback evidence 和 leader_summary 输出计划。
6. 风控仍能因为 confidence cap / 缺核心事实阻断过高置信度。
7. Bark 能收到最终 allowed / blocked 结果；管线失败时按 `send_failure_alerts` 发送 blocked failure alert。
