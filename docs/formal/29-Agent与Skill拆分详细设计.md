# Agent 与 Skill 拆分详细设计

## 1. 设计目标

本文是 `crypto-macro-decision` 方法论拆分到项目 Agent/Skill 编排层的详细设计。

`27-轻量自研Workflow与受控Agent层重构建议.md` 记录的是总体方向；本文进一步定义 Agent、Skill、Schema、执行模式、代码门禁和迁移验收，作为后续实现前的设计约束。

核心目标：

- 不再把 `crypto-macro-decision` 当成一整段 prompt 直接交给最终 LLM。
- 将其中的交易思想拆成可编排、可审计、可回放的 Agent/Skill。
- 让实时事实、根因链、市场情绪、拥挤度、场景分叉、反方审查和最终决策各自有明确边界。
- 所有实时判断必须基于当前事实，历史经验只能作为方法论和低权重过程记忆，不能当作当前市场事实。
- 允许系统给出大胆预测，但大胆预测必须来自事实链条，并带有明确证伪条件。
- 交易动作必须唯一、可解析、可被风控门禁阻断或降级。

一句话原则：

```text
Skill 提供专业能力，Agent 负责任务分工和结构化贡献，LeadAgent 负责规整冲突，FinalDecisionAgent 只输出唯一动作，代码 Gate 负责硬边界。
```

## 2. 非目标

当前阶段不做：

- 自由聊天式多 Agent swarm。
- 动态发现任意 skill。
- 任意脚本自动注册为工具。
- 自动下单、撤单、提现。
- 让 LLM 修改生产 prompt、规则或 workflow。
- 把历史交易结论默认注入 live decision。
- 用社媒或 search snippet 替代交易所原生执行事实。
- 让 RootCauseSkill 或 reviewer 直接决定最终交易动作。

## 3. 方法论拆解

`crypto-macro-decision` 的核心思想应拆成以下能力：

| 方法论 | 编排落点 | 说明 |
|---|---|---|
| 实时事实防火墙 | `LiveFactSkill` + `FactsGate` | 所有实时决策先刷新事实，缺失/陈旧/冲突不能当作中性 |
| 来源优先级 | `SourcePriorityPolicy` | 代码化，不交给 LLM 自由判断 |
| 根因链 | `RootCauseSkill` | 从事件递归追溯到 durable root driver，并输出证伪条件 |
| 市场情绪与拥挤 | `SentimentCrowdingSkill` | 判断事实是否已定价、仓位是否拥挤、短期是否可能反向 |
| 宏观传导 | `MacroBridgeSkill` | 利率、DXY、VIX、油价、QQQ/NQ 如何传到 BTC/ETH/SOL |
| 衍生品结构 | `DerivativesSweepSkill` | funding、OI、long/short、liquidation、basis、CVD、options |
| 指标扫描 | `IndicatorSweepSkill` | 15 项指标只做异常扫描和 bucket 分类 |
| 场景分叉 | `ScenarioForkSkill` | 重大事件时输出 base/upside/downside，不生成多个动作 |
| 对抗审查 | reviewer agents | 多头、空头、数据质量、执行风险独立贡献 |
| 决策阶梯 | `DecisionLadderSkill` | 主信号投票、分数阶梯、已有仓位规则、event compression |
| 最终动作 | `FinalDecisionAgent` | 只消费 `DecisionInput`，输出 strict JSON |
| 风控门禁 | Parser/Facts/Semantic/Risk Gates | 代码强制执行，优先级高于 LLM |

## 4. 总体 Workflow

采用“串行控制骨架 + 并发研究/审查内核”：

```text
Manual/Scheduled Query
  -> SessionManager
  -> IntentClassifier
  -> ComplexityRouter
  -> SlotFiller
  -> DecisionRequestBuilder
  -> VersionLock(skill/rule/prompt/model/config)
  -> SkillLoader + ToolPolicy
  -> MarketFactAgent
  -> FactsGate(pre)

  -> LeadAgent.plan_tasks
  -> Parallel Worker Agents
       MarketFactAgent
       DerivativesAgent
       MacroResearchAgent
       FlowEventAgent
       RelativeStrengthAgent
       TechnicalGuardrailAgent
  -> EvidencePacketBuilder
  -> FactsGate(post)
  -> DataQualityGate

  -> RootCauseAgent
  -> SentimentCrowdingAgent
  -> ScenarioForkAgent(optional)
  -> Reviewer Agents
       BullReviewer
       BearReviewer
       DataQualityReviewer
       ExecutionRiskReviewer
  -> LeadAgent.synthesize
  -> DecisionInputBuilder
  -> FinalDecisionAgent
  -> ParserGate
  -> PlanSemanticGate
  -> RiskGate
  -> Journal / FrozenInput
  -> SideEffectGate
  -> Bark manual alert or eval/replay no side effect
```

必须串行的环节：

- session / intent / complexity / slots
- version lock
- pre facts gate
- lead synthesis
- decision input build
- final decision
- parser / semantic / risk gates
- journal / side effect gate

可以并发的环节：

- market facts 补充采集
- macro / flow / event research
- derivatives / relative strength / technical guardrails
- bull / bear / data quality / execution risk reviewers
- eval/replay 旁路测评

## 5. 核心数据结构

### 5.1 DecisionRequest

描述用户希望系统评估什么，不拉行情、不调用 LLM、不做交易判断。

```json
{
  "run_id": "string",
  "run_type": "manual | scheduled | eval | replay | postmortem",
  "query_text": "string",
  "symbol": "BTC-USDT-SWAP",
  "asset": "BTC",
  "horizon": "now | 1h | 4h | 1d | event_window",
  "position": {
    "side": "unknown | long | short | flat",
    "entry_price": null,
    "leverage": null,
    "liquidation_price": null
  },
  "manual_only": true,
  "session_id": "string|null"
}
```

### 5.2 EvidencePacket

所有工具和研究结果必须统一转成 `EvidencePacket`。原始网页片段、交易所原始 JSON、LLM 原始回答不能直接进入最终 prompt。

```json
{
  "evidence_id": "string",
  "name": "okx_mark_price",
  "symbol": "BTC-USDT-SWAP",
  "data_type": "mark | index | last | order_book | candles | funding | open_interest | liquidation | macro | news | etf_flow | stablecoin | options | sentiment",
  "value": {},
  "unit": "USDT",
  "observed_at": "ISO-8601",
  "retrieved_at": "ISO-8601",
  "age_seconds": 42,
  "source_type": "exchange_native | official_api | official_page | aggregator_api | reputable_news | web_derived | search_derived | social_rumor | fixture",
  "source_tier": 1,
  "source_name": "OKX",
  "source_url": "https://...",
  "freshness_status": "fresh | stale | unknown",
  "can_satisfy_execution_fact": true,
  "confidence_cap": null,
  "claims": [],
  "conflicts": [],
  "tool_latency_ms": 820,
  "trace_ref": "span_id"
}
```

关键规则：

- `exchange_native` 才能满足核心执行事实。
- `search_derived` 只能降低不确定性，不能满足 mark/index/order_book。
- 每个 packet 必须有 source、timestamp、freshness。
- missing/stale/conflict 必须显式写入，不能当中性。

### 5.3 AgentContribution

所有 Agent 输出都要归一为贡献对象，供 LeadAgent 汇总。

```json
{
  "contribution_id": "string",
  "agent_name": "RootCauseAgent",
  "status": "ok | partial | failed | skipped",
  "required": true,
  "summary": "string",
  "claims": [
    {
      "claim": "string",
      "claim_type": "known_fact | consensus | inference | scenario | rumor",
      "side": "bullish | bearish | mixed | neutral",
      "evidence_ids": [],
      "confidence": "high | medium | low",
      "freshness": "fresh | mixed | stale"
    }
  ],
  "constraints": {
    "confidence_cap": null,
    "blocked_actions": [],
    "allowed_action_classes": [],
    "required_confirmations": [],
    "next_review_minutes": null
  },
  "conflicts": [],
  "missing_facts": [],
  "trace_ref": "span_id"
}
```

### 5.4 DecisionInput

FinalDecisionAgent 只能消费 `DecisionInput`，不能访问工具、原始网页、原始交易所 JSON。

```json
{
  "request": {},
  "evidence_packets": [],
  "facts_gate_result": {},
  "root_cause": {},
  "sentiment_crowding": {},
  "scenario_fork": {},
  "review_contributions": [],
  "lead_synthesis": {
    "primary_signal_vote": {},
    "scorecard": {},
    "strongest_chain": {},
    "strongest_opposite_chain": {},
    "confidence_caps": [],
    "hard_blocks": [],
    "soft_downgrades": [],
    "required_refreshes": []
  },
  "allowed_actions": [
    "open long",
    "open short",
    "hold long",
    "hold short",
    "close long",
    "close short",
    "flip long to short",
    "flip short to long",
    "trigger long",
    "trigger short",
    "no trade"
  ]
}
```

## 6. Agent 分层设计

| Agent | 职责 | 输入 | 输出 | 能否调用工具 | 能否给最终动作 |
|---|---|---|---|---:|---:|
| `DecisionLeadAgent` | 规划任务、汇总贡献、处理冲突、构建 DecisionInput | request, facts gate, contributions | lead synthesis | 否或只读 registry | 否 |
| `MarketFactAgent` | 拉交易所原生执行事实 | symbol, requirements | EvidencePacket[] | 是 | 否 |
| `DerivativesAgent` | 整理 funding/OI/liquidation/basis/CVD/options | market facts | AgentContribution | 是或只读 | 否 |
| `MacroResearchAgent` | 查宏观、利率、DXY、VIX、油价、事件 | request, facts | AgentContribution | 是 | 否 |
| `FlowEventAgent` | 查 ETF、stablecoin、事件池、突发新闻 | request, event context | AgentContribution | 是 | 否 |
| `RelativeStrengthAgent` | 比较 BTC/ETH/SOL 强弱 | candles, price pairs | AgentContribution | 否或只读 | 否 |
| `TechnicalGuardrailAgent` | 执行质量：结构、ATR、RR、支撑阻力 | evidence packets | AgentContribution | 否或只读 | 否 |
| `RootCauseAgent` | 递归根因链和可证伪路径 | evidence, seed events | CausalEvidenceGraph | 通过受控事实请求 | 否 |
| `SentimentCrowdingAgent` | 情绪、拥挤、已定价、反身性 | facts, candidate direction | AgentContribution | 否或只读 | 否 |
| `ScenarioForkAgent` | base/upside/downside 场景 | event facts, consensus | ScenarioSummary | 否或只读 | 否 |
| `BullReviewer` | 最强多头链 | decision draft input | ReviewContribution | 否 | 否 |
| `BearReviewer` | 最强空头链 | decision draft input | ReviewContribution | 否 | 否 |
| `DataQualityReviewer` | 来源、新鲜度、冲突、cap | packets, facts gate | ReviewContribution | 否 | 否 |
| `ExecutionRiskReviewer` | entry/stop/target/RR/滑点/事件 | decision input draft | ReviewContribution | 否 | 否 |
| `FinalDecisionAgent` | 生成唯一 strict JSON DecisionPlan | DecisionInput | DecisionPlan raw JSON | 否 | 是，且必须过 gate |

## 7. Skill 拆分设计

| Skill | 职责 | 输入 | 输出 | 工具权限 |
|---|---|---|---|---|
| `request-normalization-skill` | 意图、symbol、horizon、仓位槽位标准化 | raw query, session | DecisionRequest draft | 无 |
| `live-fact-skill` | 实时事实总入口 | LiveFactRequest | LiveFactResponse | 行情/API/search 白名单 |
| `news-search-skill` | 固定 search lanes，结构化实时消息 | search plan | EvidencePacket[] | web_search |
| `derivatives-sweep-skill` | funding/OI/liquidation/long-short/basis/options | market facts | derivatives contribution | 行情/聚合数据 |
| `macro-bridge-skill` | rates/DXY/VIX/oil/QQQ/Fed path 传导 | macro facts | macro contribution | web/API |
| `flow-event-skill` | ETF/stablecoin/交易所流入流出/事件池 | event context | flow contribution | web/API |
| `indicator-sweep-skill` | 15 项指标 bucket 扫描 | evidence packets | bucket state table | 只读 |
| `root-cause-skill` | 递归因果检索和最大可能路径 | facts, seed event | CausalEvidenceGraph | 受控事实请求 |
| `sentiment-crowding-skill` | 已定价、拥挤、反身性、短期偏离 | objective facts, market facts | constraints contribution | 只读 |
| `scenario-fork-skill` | 重大事件路径分叉 | event window, consensus, facts | ScenarioSummary | 只读 |
| `adversarial-review-skill` | 多头/空头/数据/执行审查模板 | DecisionInput draft | ReviewContribution[] | 无 |
| `decision-ladder-skill` | 主信号投票、分数阶梯、已有仓位规则 | contributions | ladder result | 无 |
| `final-plan-skill` | strict JSON 决策计划 | DecisionInput | DecisionPlan raw JSON | 无 |
| `risk-gate-skill` | 风控 rule hit 文案模板 | plan, snapshot, gate result | risk explanation | 代码调用 |
| `eval-replay-skill` | frozen input 回放和候选评估 | frozen input, candidate | eval report | 只读 |

Skill 可以包含：

- prompt 片段
- 输入输出 schema
- tool policy
- 质量规则
- fallback 策略
- trace 记录规范

Skill 不应该：

- 自由注册工具
- 绕过 workflow
- 直接修改生产规则
- 直接产生副作用
- 动态发现未知脚本

## 8. LiveFactSkill / NewsSearchSkill / SourcePriorityPolicy

### 8.1 LiveFactSkill

职责：

- 作为实时事实总入口。
- 编排交易所 API、宏观/ETF/新闻覆盖、事实新鲜度检查。
- 输出覆盖率、缺口、冲突、confidence cap 和 hard block。

输入：

```json
{
  "run_id": "string",
  "symbol": "BTC-USDT-SWAP",
  "asset": "BTC",
  "run_mode": "simple_fast | standard | deep_research",
  "horizon": "now | intraday | event_window | swing",
  "as_of": "ISO-8601",
  "deadline_ms": 90000,
  "allow_web_search": true,
  "required_domains": [
    "execution_price",
    "derivatives",
    "btc_anchor",
    "macro",
    "breaking_news",
    "events"
  ],
  "requirements": [
    {
      "fact_id": "mark_price",
      "data_type": "mark",
      "required": true,
      "max_age_seconds": 120,
      "acceptable_source_types": ["exchange_native"],
      "can_be_satisfied_by_search": false
    }
  ]
}
```

输出：

```json
{
  "status": "ok | partial | blocked",
  "packets": [],
  "coverage": {
    "required": [],
    "covered": [],
    "missing": [],
    "stale": []
  },
  "hard_blocks": [],
  "soft_downgrades": [],
  "confidence_caps": [],
  "conflicts": [],
  "next_recheck_at": "ISO-8601"
}
```

### 8.2 NewsSearchSkill

职责：

- 执行固定 search lanes。
- 返回结构化来源证据。
- 不做交易判断。

典型 search lanes：

- Fed / rates / data expectations
- CPI / PPI / PCE / NFP / FOMC
- ETF flows
- stablecoin / exchange flows
- CoinGlass / Coinalyze / Velo / Laevitas
- Deribit options
- exchange / chain status
- Reuters / AP / Bloomberg / CNBC breaking news
- official issuer / regulator announcements

### 8.3 SourcePriorityPolicy

不建议做成 LLM Skill，应做成代码化规则。

优先级：

1. 交易执行事实：OKX/Binance/Bybit/Deribit 原生 API。
2. 全市场衍生品：CoinGlass / Coinalyze / Velo / Laevitas。
3. 宏观实际值：BLS / BEA / Fed / Treasury / Cboe / FRED。
4. 新闻：官方声明 > Reuters/AP/Bloomberg > CNBC/WSJ/FT > social。
5. 社媒：只作为 rumor risk，不能作为 confirmed fact。

硬规则：

- `search_derived` 不能满足 mark/index/order_book。
- 执行事实冲突时不取平均，必须二次验证；无法验证则 hard block/cap。
- 地缘新闻冲突时标为 `unconfirmed scenario`。
- ETF flows 必须看 total，不允许只看单一基金。

## 9. RootCauseSkill

### 9.1 定位

`RootCauseSkill` 是“递归因果检索与可证伪路径生成器”，不是最终交易决策器。

它围绕一个事件或异常市场事实递归追问：

- 为什么它发生？
- 它会通过哪些通道影响 BTC/ETH/SOL？
- 这些通道又受哪些更深层因素驱动？
- 哪条路径是当前事实下最大可能路径？
- 什么事实会证伪这条路径？

### 9.2 因果链格式

```text
observable fact
  -> prior expectation / positioning
  -> immediate cause
  -> deeper driver
  -> market transmission
  -> confirmation trigger
  -> trade implication
```

`SentimentCrowdingSkill` 参与后，链条必须显式包含：

```text
market interpretation / crowding distortion
```

### 9.3 输出

```json
{
  "skill": "RootCauseSkill",
  "status": "complete | partial | hard_blocked",
  "data_quality": {
    "freshness": "fresh | mixed | stale",
    "source_tiers_used": [],
    "missing_critical_facts": [],
    "confidence_cap": "none | <=58 | <=55 | no_directional_score"
  },
  "root_cause_graph": {
    "seed_event": "string",
    "nodes": []
  },
  "ranked_chains": [],
  "maximum_likelihood_path": {
    "summary": "string",
    "why_this_path_wins": [],
    "bold_falsifiable_prediction": "string",
    "falsifiers": []
  },
  "opposite_chain": {
    "summary": "string",
    "what_would_make_it_take_control": []
  }
}
```

### 9.4 循环停止条件

- 达到 `max_depth`，默认 4。
- 达到 `max_nodes`，默认 24。
- 当前链已落到 durable root driver。
- 新一层检索没有增加独立事实。
- 当前节点与交易 horizon 无关。
- 证据只能来自 rumor/social 且无法确认。
- 关键事实缺失导致方向无法评分。
- 来源冲突无法裁决。
- 触发 timeout 或 tool budget。

### 9.5 质量规则

- 每个 `known_fact` 必须绑定 evidence。
- 没有 evidence 的 claim 降级为 `scenario`。
- Rumor/social 不能成为主链根因。
- 每条 ranked chain 必须有 confirmation trigger 和 invalidation。
- 必须输出 strongest opposite chain。
- 最大可能路径必须有 price/event/derivatives/time 四类证伪条件。
- RootCauseSkill 禁止输出最终交易 enum。

## 10. SentimentCrowdingSkill

### 10.1 定位

`SentimentCrowdingSkill` 解决“事实正确但短期价格可能反向”的问题。

它回答：

- 市场是否已经充分定价某个事实？
- 多头/空头是否拥挤？
- 新信息是否还能带来边际买盘/卖盘？
- 清算、期权 gamma、社媒叙事、ETF 预期是否在扭曲传导？
- 当前方向应加分、降权、限制为 trigger，还是禁止追价？

它不输出交易动作，只输出约束和贡献。

### 10.2 需要分析的数据

- funding：当前值、年化、7d/30d percentile、跨交易所差异、下一次 funding。
- OI：1h/4h/24h 变化、价格/OI 组合、OI/volume、跨交易所集中度。
- long/short：账户比、持仓比、大户比。
- liquidation：1h/4h/24h/7d 清算簇。
- basis/perp premium：现货推动还是合约追涨。
- taker flow/CVD：主动买卖、吸收、背离。
- options skew：25-delta skew、put/call OI、IV、max pain、gamma zone。
- ETF flows：总净流入/流出和连续性。
- stablecoin/liquidity：稳定币供给、交易所 stablecoin 余额。
- fear/greed：只作为情绪温度计。
- social/news heat：新闻热度、叙事拥挤、KOL 一致性。
- cross-asset sentiment：VIX、DXY、收益率、QQQ/NQ、油价。

### 10.3 输出

```json
{
  "skill": "SentimentCrowdingSkill",
  "status": "ok | partial | unavailable | conflict",
  "crowding_state": "not_crowded | mildly_crowded | crowded_but_trending | dangerously_crowded",
  "priced_in_state": "not_priced_in | partly_priced_in | mostly_priced_in | overpriced",
  "reflexivity_state": {
    "direction": "upward | downward | two_way | none",
    "strength": "low | medium | high",
    "mechanism": "string"
  },
  "short_term_distortion": {
    "risk": "low | medium | high",
    "likely_against_objective_fact": true,
    "expected_window": "minutes | 1h | 4h | 1d",
    "reason": "string"
  },
  "constraints": {
    "max_confidence": 58,
    "max_position_size": "none | tiny | small | normal",
    "allowed_action_classes": [],
    "blocked_actions": [],
    "required_confirmations": [],
    "next_review_minutes": 30
  }
}
```

### 10.4 典型解释

好消息不等于做多：

```text
好消息
  -> 是否早已预期
  -> funding 是否极高
  -> OI 是否继续上升
  -> 多头清算簇是否密集在下方
  -> 是否只能等待突破接受或回踩确认
```

坏消息不等于做空：

```text
坏消息
  -> 空头是否拥挤
  -> funding 是否负
  -> 价格是否不再创新低
  -> 是否存在轧空风险
```

ETF 流入不等于上涨：

```text
ETF 总流入
  -> 是否连续
  -> 价格是否已提前反应
  -> 现货买盘是否被卖盘吸收
  -> BTC 结构是否确认
```

### 10.5 门禁规则

- 缺 funding 或 OI 时，杠杆方向置信度不得高于 60%。
- 单一 fear/greed、社媒热度、KOL 观点不能作为主方向依据。
- `search-derived` 不能替代 exchange-native mark/index/funding/OI。
- funding 极端同向 + OI 上升 + 价格接近阻力/支撑时，禁止追同向 market entry。
- ETF flows 必须看总净流量和连续性。
- 新闻热度高但价格不跟随，必须标记 `priced_in` 或 `absorption`。
- 数据窗口必须匹配交易周期。
- 多源衍生品冲突时输出 `conflict` 并触发 cap。
- 重大宏观事件或期权到期附近，options/gamma/liquidation 缺失必须降级。

## 11. Reviewer 设计

Reviewer 不是角色扮演，而是独立审查贡献。

| Reviewer | 必须回答 |
|---|---|
| `BullReviewer` | 最强多头根因链、确认条件、失效条件、为什么可以超过空头 |
| `BearReviewer` | 最强空头根因链、确认条件、失效条件、为什么可以超过多头 |
| `DataQualityReviewer` | 哪些事实 fresh/stale/missing/conflict，哪些 search-derived 不能用 |
| `ExecutionRiskReviewer` | entry/stop/T1/T2/RR、盘口、滑点、清算簇、事件窗口、是否只能 trigger |

每个 reviewer 必须：

- 有独立 span。
- 有 timeout。
- 有 status。
- 失败时写 `failed` 或 `partial`，不能伪装成功。
- required reviewer 失败会触发 hard block 或 confidence cap。
- optional reviewer 失败只写 unavailable。

## 12. LeadAgent 设计

LeadAgent 是中心协调者，但不是交易决策者。

职责：

- 根据 request、facts gate、复杂度决定需要哪些 Agent/Skill。
- 汇总 `EvidencePacket` 和 `AgentContribution`。
- 标记冲突、缺失、降级、confidence cap。
- 生成主信号投票材料。
- 生成 scorecard。
- 选择可进入 FinalDecisionAgent 的 root-cause chains。
- 构建 `DecisionInput`。

LeadAgent 不做：

- 不直接输出 `main_action`。
- 不绕过 gates。
- 不调用下单/通知工具。
- 不修改生产规则。
- 不把历史结论当当前事实。

## 13. FinalDecisionAgent 设计

FinalDecisionAgent 只消费 `DecisionInput`，输出 strict JSON `DecisionPlan`。

要求：

- `main_action` 必须且只能是一个合法枚举。
- 必须包含 entry/trigger、stop、T1/T2、invalidation、next review time。
- 必须解释 why-not-opposite。
- 必须体现 confidence cap 和 hard block。
- 不能调用工具。
- 不能搜索。
- 不能发通知。
- 不能修改 RiskVerdict。

允许动作：

```text
open long
open short
hold long
hold short
close long
close short
flip long to short
flip short to long
trigger long
trigger short
no trade
```

## 14. 执行模式

### 14.1 simple_fast

适用：

- 普通手动提醒。
- 无重大事件窗口。
- 无高杠杆/复杂持仓。
- 用户没有要求深度根因链。

链路：

```text
core market facts
  -> basic derivatives sweep
  -> light macro/event check
  -> compact review
  -> Lead summary
  -> FinalDecision
  -> gates
```

策略：

- 总耗时控制在 180-300 秒内。
- search group 60-90 秒。
- reviewer 可合并成 compact LLM。
- 缺辅助数据可 cap。
- 缺核心执行事实必须 block。
- 更倾向 `trigger long/short`，少给高置信 market entry。

### 14.2 standard

适用：

- 普通交易判断。
- 有仓位、杠杆、止损止盈。
- 无极端事件，但需要覆盖 research。

链路：

```text
full core fact pack
  -> derivatives / macro / flow coverage
  -> root-cause compact
  -> sentiment/crowding
  -> compact reviewers
  -> Lead synthesis
  -> FinalDecision
  -> gates
```

策略：

- 总耗时可到 900 秒。
- research 最多 180 秒。
- 缺关键事实不强行输出方向。

### 14.3 deep_research

适用：

- CPI/FOMC/NFP。
- ETF 异常。
- 地缘冲突。
- 暴涨暴跌。
- 爆仓链。
- 用户明确要求多 Agent、根因链、大胆预测。

链路：

```text
complete fact pack
  -> full macro/flow/derivatives/event research
  -> RootCauseSkill recursive graph
  -> SentimentCrowdingSkill
  -> ScenarioForkSkill
  -> independent reviewers
  -> Lead conflict resolution
  -> FinalDecision
  -> strict gates
```

策略：

- 总耗时可到 1800 秒。
- 必须标明不是极速短线提醒。
- reviewer 独立 span/timeout。
- 必须输出 strongest opposite chain。
- 必须标注 confidence cap 和 missing facts。
- 重大事件 6-24h 内优先 trigger/hold-to-near-target。
- 最终仍只允许一个 `main_action`。

## 15. 代码 Gate

以下必须由代码强制，不能交给 LLM：

- action enum 唯一性和合法性。
- strict JSON 和字段类型。
- `manual_execution_required=true`。
- eval/replay 不发 Bark、不写生产副作用。
- 禁止自动下单、撤单、提现。
- 禁止读取交易密钥。
- `search-derived` 不能满足 mark/index/order_book。
- 核心执行事实缺失时阻断开仓、反手、高杠杆入场。
- stale data 检查和 confidence cap。
- allowed symbols。
- max leverage。
- risk_pct。
- plan TTL。
- entry/stop/target 顺序。
- RR 下限。
- action-position 合法性。
- FinalDecisionAgent 不允许调用工具。
- RootCauseSkill 和 reviewers 不允许输出最终交易动作。

LLM 可以判断但必须结构化输出并被 gate 约束：

- 宏观事件如何传导到 BTC/ETH/SOL。
- 根因链质量。
- 最强反方论点。
- 新闻是否可能已定价。
- 拥挤程度的定性解释。
- 场景分叉。
- 主观概率说明。
- 为什么不用相反方向。
- 哪些证据会改变动作。

## 16. Trace / Eval / FrozenInput

每个 step、tool、agent、reviewer 都要有独立 trace span：

```text
workflow.session
workflow.intent
workflow.complexity
skill.load
tool.market.fetch
tool.news.search
gate.facts.pre
agent.macro_research
agent.root_cause
agent.sentiment_crowding
review.bull
review.bear
review.data_quality
review.execution_risk
agent.lead_synthesis
decision.input.build
decision.final
gate.parser
gate.semantic
gate.risk
journal.write
side_effect.notification
```

FrozenInput 必须保存：

- request
- evidence packet summaries
- facts gate result
- agent contributions
- lead synthesis
- decision input
- config/rule/prompt/model/skill hash

Eval 只评：

- 事实覆盖是否完整。
- 来源使用是否正确。
- search-derived 是否被错误用于执行事实。
- 根因链是否完整。
- 反方链是否存在。
- confidence cap 是否正确。
- action enum 是否唯一。
- 风控 gate 是否阻断该阻断的动作。

Eval 不评：

- 交易是否赚钱。
- 是否应该绕过 RiskGate。
- 是否自动发布候选。

## 17. 迁移阶段

### P0：设计冻结

内容：

- 本文档确认。
- 明确 schema。
- 明确 gate 优先级。
- 明确 simple_fast / standard / deep_research。

验收：

- 后续实现不得绕过本文定义的边界。

### P1：Context 与贡献对象

内容：

- 新增 `DecisionRunContext`。
- 新增 `EvidencePacket`。
- 新增 `AgentContribution`。
- 新增 `DecisionInput`。
- `RunExecutor` 创建 context。

验收：

- 主入口不再只传 symbol。
- 一轮运行有唯一 context。
- research/reviewer 输出可以记录为 contribution。

### P2：LiveFact 与 FactsGate

内容：

- 实现 `LiveFactSkill`。
- 实现 `SourcePriorityPolicy`。
- 实现 `FactsGate`。
- 将当前 market/research 结果转 EvidencePacket。

验收：

- `search-derived` 不能满足 mark/index/order_book。
- 缺核心执行事实时开仓/反手被阻断。

### P3：Agent 编排骨架

内容：

- 实现 LeadAgent planning/synthesis。
- worker agent 并发执行。
- reviewer 独立 span/status/timeout。

验收：

- 单个 reviewer 失败不会伪装成功。
- LeadAgent 能标记缺失 reviewer。
- contribution 可回放。

### P4：RootCause 与 SentimentCrowding

内容：

- 实现根因递归图。
- 实现拥挤/已定价/反身性约束。
- 接入 DecisionInput。

验收：

- 每条根因链有证据、确认、失效。
- 情绪拥挤能限制 fresh market entry。

### P5：FinalDecision 与 Gates

内容：

- FinalDecisionAgent 只消费 DecisionInput。
- ParserGate / PlanSemanticGate / RiskGate 完整接管。

验收：

- FinalDecisionAgent 无工具权限。
- 输出唯一动作。
- gate 可阻断或降级。

### P6：Eval / Replay

内容：

- frozen input 覆盖完整链路。
- badcase 变成 eval case。
- candidate 只走离线评估和人工审批。

验收：

- eval/replay 无 Bark。
- badcase 不污染 live decision。

## 18. 待确认问题

- `DecisionRunContext` 字段是否按模块拆分，避免成为新的大杂烩对象。
- RootCauseSkill 默认最大深度是否为 4，deep_research 是否允许提高到 5。
- simple_fast 是否默认跳过 ScenarioForkSkill。
- SentimentCrowdingSkill 是独立 LLM call，还是先规则化 + compact LLM。
- reviewer 默认 compact，还是 standard 就独立。
- NewsSearchSkill 是否优先使用 OpenAI web_search，再 fallback DuckDuckGo HTML。
- source freshness 阈值是否按 horizon 配置化。
- deep_research 最大运行时间是否接受 1800 秒。
- FinalDecisionAgent 的 prompt/version 是否独立于 skill version。
- 是否需要将 `SourcePriorityPolicy` 写入 YAML，还是先硬编码。

## 19. 当前结论

本项目的核心价值不是“写一个 skill 给 Codex 调”，而是把交易判断拆成可控链路：

```text
实时事实
  -> 受控检索
  -> 根因递归
  -> 情绪/拥挤约束
  -> 对抗审查
  -> Lead 规整
  -> 唯一动作
  -> 代码门禁
  -> trace/eval 回放
```

只有这样，系统才能在实时消息高度敏感的加密货币市场里，既允许大胆预测，又避免无依据的方向判断。
