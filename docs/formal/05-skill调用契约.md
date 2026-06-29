# Skill 调用契约

## 目标

v1 固定使用 `crypto-macro-decision`，不做任意 skill 动态发现。

## Skill 路径

固定路径：

```text
third_party/skills/crypto-macro-decision
```

必须存在：

```text
SKILL.md
references/data-sources.md
references/exchange-derivatives.md
references/templates.md
scripts/okx_snapshot.py
```

缺失任一必要文件时，当前 run 必须 block。

## 加载流程

```text
1. 读取 SKILL.md。
2. 计算 SKILL.md sha256。
3. 读取 v1 必需 references。
4. 校验 scripts/okx_snapshot.py 是否存在。
5. 构造 SkillContext。
```

## v1 必需 references

每次 live decision 必须加载：

- `references/data-sources.md`
- `references/exchange-derivatives.md`
- `references/templates.md`

按需加载：

- `references/event-pool.md`
- `references/factors-and-sop.md`
- `references/indicator-sweep.md`
- `references/lessons.md`

## OKX Snapshot 调用

优先调用：

```text
python scripts/okx_snapshot.py ETH-USDT-SWAP
```

返回内容必须被转换为 `EvidenceSnapshot`。

必须提取或标记：

- last
- mark
- index
- funding
- open interest
- 1H candles
- 4H candles
- order book
- source
- timestamp
- unavailable

## 工具超时

建议配置：

```yaml
tools:
  okx_snapshot_timeout_seconds: 30
  reference_load_timeout_seconds: 5
```

超时处理：

- reference 读取失败 -> block。
- OKX snapshot 超时 -> 进入 fallback 或 block。
- 不允许使用过时缓存伪装为 live facts。

## Web Fallback

v1.1 已接入受控 Web fallback。它不是绕过 skill，而是在 skill 的 live fact gate 和数据源优先级约束下，由 Leader 拆分检索任务，再由程序并发执行。

触发条件：

- OKX 不可用。
- 核心数据缺失。
- 核心数据 stale。
- active event window 内需要新闻确认。

执行流程：

```text
MarketSnapshot
  -> ResearchPlanner(static|llm)
  -> execute_research(max_workers=N)
  -> SearchAdapter(responses_web_search|duckduckgo_html|fixture|disabled)
  -> EvidenceSynthesizer
  -> LeaderResearchSynthesizer(static|llm)
```

返回结果必须标记来源：

- `web-derived`
- `search-derived`

web fallback 不能完全替代：

- mark
- index
- order book

这些缺失时必须保留 confidence cap 或 block。

## Leader / 多 agent 契约

这里的多 agent 是固定边界内的轻量编排，不是完整 swarm 平台：

- `LeaderResearchPlanner`：根据 skill 规则、缺失数据和 stale 数据拆分研究任务。
- `Concurrent Researchers`：每个 `ResearchQuery` 独立执行，互不共享状态。
- `LeaderResearchSynthesizer`：汇总证据、冲突、缺口和来源质量。
- `AdversarialReview`：必须包含 `bull_reviewer`、`bear_reviewer`、`data_quality_reviewer`、`execution_risk_reviewer`。

LLM planner / LLM synthesizer 失败时可以降级到 static，但必须把 fallback 原因写入 audit，不能假装 LLM 审查成功。

## Prompt 包结构

传给 LLM 的 prompt packet 必须包含：

```json
{
  "boundary": "manual-alert-only; do not place orders",
  "skill_context": {},
  "request": {},
  "session_context": {},
  "evidence_snapshot": {},
  "research": {
    "plan": {},
    "results": {},
    "leader_summary": {}
  },
  "root_cause_template": "客观事实 -> 机制解释 -> 路径预测 -> 反向链 -> 失效条件",
  "required_output": "strict JSON DecisionPlan"
}
```

## 禁止事项

- 不允许 skill script 下单。
- 不允许读取 trade / withdraw key。
- 不允许把密钥放进 prompt。
- 不允许任意脚本自动暴露为工具。
- 不允许从 journal 中读取旧结论替代 fresh facts。
