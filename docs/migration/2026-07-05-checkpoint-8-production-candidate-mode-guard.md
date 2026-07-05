# Checkpoint 8: production_candidate_swarm guarded route

日期：2026-07-05

## 目标

新增命名清晰的 `production_candidate_swarm` 执行模式入口，但在 candidate sidecar 和 release gate 完整接入前，必须保持 blocked + audit-only，避免误以为 Agent Swarm 已接管生产 final input。

## 改动

- `config/loader.py`
  - workflow execution mode allowlist 增加 `production_candidate_swarm`。
- `workflow/executor.py`
  - `production_candidate_swarm` 路由到受控 adapter。
- `workflow/controlled_adapter.py`
  - 根据 execution mode 生成 trace prefix、metadata、audit reason。
  - `production_candidate_swarm` 使用 `production-candidate-swarm-` trace prefix。
  - verdict reason 使用 `production_candidate_swarm_audit_only`。

## 验证

```powershell
python -m pytest tests/config/test_config.py::test_config_accepts_production_candidate_swarm_workflow_mode tests/workflow/test_controlled_adapter.py::test_run_executor_can_route_to_production_candidate_swarm_but_keeps_it_blocked -q
python -m pytest tests/config/test_config.py tests/workflow/test_controlled_adapter.py -q
```

## 边界

- 新模式当前仍是 audit-only guarded route。
- 不写通知。
- 不下单。
- 不改变默认 `legacy_baseline`。
- 不切换 `decision.final_input_mode=decision_input`。
- 尚未运行 candidate FinalDecisionAgent sidecar。
