# Checkpoint 8: candidate state and gate diagnosis

日期：2026-07-06

## 目标

让 `production_candidate_swarm` 的 API 和页面明确显示当前候选状态，而不是让评审者从 `mode/audit_only` 推断。同时让 candidate sidecar input gate failure 输出可读诊断。

## 改动

- `workflow/controlled_adapter.py`
  - `controlled_shadow` payload 增加 `status=blocked`、`production_candidate=false`、`blocked=true`。
- `storage/agent_audit_view.py`
  - `controlled_shadow` projection 透出 `status`、`production_candidate`、`blocked`。
  - `candidate_final_comparison.candidate` 透出非空 `diagnosis`。
- `decision/candidate_final_decision.py`
  - input gate failure 增加 `diagnosis.summary` 和 `diagnosis.blocking_reasons`。
- `frontend/src/app/runs/[traceId]/candidate-comparison.tsx`
  - 显示 `Candidate Status`、`Production Input`、`Input Selection`。
  - 显示 sidecar gate diagnosis。
- `frontend/src/app/styles.css`
  - 增加 `audit-note` 提示块样式。

## 验证

```powershell
python -m pytest tests/decision/test_candidate_final_decision.py tests/workflow/test_controlled_adapter.py tests/storage/test_agent_audit_view.py -q
python -m pytest tests/api/test_runs_routes.py -q
npm run typecheck
```

Runtime smoke：

```text
trace_id=production-candidate-swarm-run_9581a9059cf84b3180b7fe4a5e1d920c
agent_audit_view.mode=production_candidate_swarm
controlled_shadow.status=blocked
controlled_shadow.production_candidate=false
controlled_shadow.blocked=true
candidate_final_comparison.production_final_input=false
candidate_final_comparison.candidate.diagnosis.summary=candidate final sidecar blocked by input gate
candidate_final_comparison.candidate.diagnosis.blocking_reasons=pre_final_input.validation_failed
tool_calls=realtime_search,root_cause_search,market_sentiment,liquidity_order_book
GET /runs/{trace_id}=200
page contains=Candidate Status, Production Input, candidate final sidecar blocked by input gate, pre_final_input.validation_failed
```

## 边界

- 仍不切换默认 `workflow.execution_mode`。
- 仍不切换默认 `decision.final_input_mode`。
- 仍不写通知、不下单。
- candidate sidecar 成功后的三方对比还需要继续补齐。
