# Checkpoint 9: fact refs visibility

日期：2026-07-05

## 目标

让 Run Detail 页面直接显示 execution fact refs，避免管理者只能从 JSON/passthrough 字段里判断 `liquidity_order_book` 是否拿到了 mark/index/order_book 引用。

## 改动

- `frontend/src/lib/schemas/runs.ts`
  - tool call schema 增加 `fact_refs`。
- `frontend/src/app/runs/[traceId]/tool-call-graph.tsx`
  - Skill Tool Calls 表格增加 `Fact Refs` 列。
  - 固定展示 `mark`、`index`、`order_book` 三类 ref 的短文本。

## 验证

```powershell
npm run typecheck
```

Runtime smoke：

```text
trace_id=production-candidate-swarm-run_e96be3a707f34f15b71d9cdc1f89949b
GET /runs/{trace_id} -> HTTP 200
page contains: Fact Refs, order_book, Candidate Comparison, audit_only
```

API smoke：

```text
agent_audit_view.mode=production_candidate_swarm
tool_calls=realtime_search, root_cause_search, market_sentiment, liquidity_order_book
liquidity_order_book.fact_refs=mark,index,order_book
candidate_final_comparison.status=audit_only
candidate_final_comparison.candidate.error.type=input_gate_failed
```

## 边界

- 本切片只做显式展示，不新增交互图。
- 尚未把 execution refs 做成单独 drilldown 面板。
