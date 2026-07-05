# Checkpoint 8: candidate sidecar in production_candidate_swarm

日期：2026-07-05

## 目标

让 `production_candidate_swarm` 不只是安全路由，还能生成 audit-only candidate FinalDecisionAgent sidecar artifact。该 sidecar 不能成为生产 final input，不能写通知，不能下单。

## 改动

- `workflow/controlled_adapter.py`
  - `production_candidate_swarm` 模式下运行 `run_candidate_final_decision_sidecar()`。
  - 使用 `evaluate_pre_final_input_gate()` 作为 sidecar 输入 gate。
  - 使用当前 config 的 `DecisionEngine`。
  - 将 sidecar payload 传入 `build_candidate_audit_payload()`。
- `tests/workflow/test_controlled_adapter.py`
  - 新增断言：payload 中存在 `candidate_final_decision`。
  - 断言 `decision_effect=none`。
  - 断言 `production_final_input=false`。

## 验证

```powershell
python -m pytest tests/workflow/test_controlled_adapter.py::test_run_executor_can_route_to_production_candidate_swarm_but_keeps_it_blocked -q
python -m pytest tests/config/test_config.py tests/workflow/test_controlled_adapter.py -q
```

## 边界

- `controlled_shadow` 不强制运行 candidate sidecar。
- `production_candidate_swarm` 当前仍 blocked + audit-only。
- 当前 adapter 不运行 legacy production final，因此还不是完整 legacy/candidate 对比链路。
- 不改变默认 `workflow.execution_mode=legacy_baseline`。
