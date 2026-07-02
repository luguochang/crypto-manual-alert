# Compatibility Wrapper Lifecycle

This document is the lifecycle table for compatibility wrappers kept during the controlled Agent Swarm convergence. It is referenced by `31-受控AgentSwarm主链收敛与质量切换计划.md` Checkpoint 8B.

These wrappers exist only to preserve historical import paths while the canonical modules settle. They must not receive new business rules, workflow behavior, production gates, or side effects.

Production code must use canonical owners directly. Tests may import wrappers only when they are explicitly verifying backwards compatibility or wrapper boundaries. Before removing any wrapper, the migration note must include an internal import scan, a supported external-caller scan, and a rollback note explaining how to restore the compatibility path if an external user still depends on it.

## Lifecycle Table

| Compatibility wrapper | Canonical owner | Allowed usage | No-new-logic rule | Removal condition | Current guard |
|---|---|---|---|---|---|
| `src/crypto_manual_alert/agent_swarm/contracts.py` | `src/crypto_manual_alert/orchestration/contracts.py` | compatibility import for legacy contract paths | no new logic; re-export orchestration contracts only | remove after internal imports and supported external callers use `orchestration.contracts` | structure test: `tests/structure/test_orchestration_contract_boundaries.py` |
| `src/crypto_manual_alert/agent_swarm/harness.py` | `src/crypto_manual_alert/orchestration/harness.py` | compatibility import for legacy harness paths | no new logic; re-export orchestration harness only | remove after harness callers use `orchestration.harness` directly | structure test: `tests/structure/test_orchestration_contract_boundaries.py` |
| `src/crypto_manual_alert/agent_swarm/default_lead_plan.py` | `src/crypto_manual_alert/lead/default_plan.py` | compatibility import for historical default lead plan path | no new logic; re-export lead default plan only | remove after `LeadAgent` planning callers stop importing from `agent_swarm.default_lead_plan` | structure test: `tests/structure/test_default_lead_plan_boundaries.py` |
| `src/crypto_manual_alert/agent_swarm/shadow_orchestration.py` | `src/crypto_manual_alert/orchestration/shadow_audit.py`; secondary failure owner: `src/crypto_manual_alert/orchestration/shadow_failure.py` | compatibility import for historical shadow audit entrypoint | no new logic; re-export orchestration shadow audit and failure entrypoints only | remove after workflow and CLI callers use `orchestration.shadow_audit` and `orchestration.shadow_failure` directly | structure test: `tests/structure/test_shadow_orchestration_boundaries.py` |
| `src/crypto_manual_alert/agent_swarm/shadow_failure.py` | `src/crypto_manual_alert/orchestration/shadow_failure.py` | compatibility import for historical shadow failure helper | no new logic; re-export orchestration shadow failure only | remove after failure envelope callers use `orchestration.shadow_failure` directly | structure test: `tests/structure/test_orchestration_contract_boundaries.py` |
| `src/crypto_manual_alert/agent_swarm/workers.py` | `src/crypto_manual_alert/market_agents/` | compatibility import for historical local worker exports | no new logic; re-export market agent worker classes/builders only | remove after worker callers use `market_agents` or `agent_swarm.registry` directly | structure test: `tests/structure/test_local_worker_boundaries.py` |
| `src/crypto_manual_alert/agent_swarm/local_workers/` | `src/crypto_manual_alert/market_agents/` | compatibility import for historical local worker module paths | no new logic; each file re-exports canonical market agent implementation only | remove after all local worker callers use `market_agents` directly | structure test: `tests/structure/test_local_worker_boundaries.py` |
| `src/crypto_manual_alert/skills/runtime.py` | `src/crypto_manual_alert/skills/context_loader.py`; `src/crypto_manual_alert/decision/final_engine.py` | compatibility import for historical skill runtime and legacy final engine exports | no new logic; re-export skill context and legacy final engine allowlist only | remove after internal and supported external callers use canonical skill and decision modules | structure test: `tests/structure/test_skill_runtime_boundaries.py` |

## Rules

- A compatibility wrapper may import from its canonical owner and declare `__all__`.
- A compatibility wrapper may not define new classes, functions, dataclasses, workflow branches, side-effect decisions, final decision logic, market business rules, or retry behavior.
- Internal production code must prefer canonical owners. Wrappers are for compatibility import paths only.
- Tests may use wrappers only for compatibility and boundary verification.
- New code must not add imports from these wrappers unless it is explicitly preserving a historical API boundary.
- Removal requires a dedicated checkpoint or migration note proving there are no internal imports and no supported external callers left.
- The removal note must record the exact scan command or review method used for both internal code and documented public examples.

## Non-Wrappers Kept In Place

The following `agent_swarm` modules are not compatibility wrappers in the current code shape:

| Module | Current role |
|---|---|
| `src/crypto_manual_alert/agent_swarm/registry.py` | Worker implementation registry and mode selection. It may depend on `market_agents.registry`, but it is still the registry owner for shadow worker implementations. |
| `src/crypto_manual_alert/agent_swarm/runtime.py` | Agent run request/result runtime contract and execution helper for controlled worker execution. |
| `src/crypto_manual_alert/agent_swarm/pool_runner.py` | Worker pool scheduling runtime. |
| `src/crypto_manual_alert/agent_swarm/llm_tool_worker.py` | Controlled LLM/tool worker implementation. |
| `src/crypto_manual_alert/agent_swarm/tool_executor.py` | Controlled tool executor boundary. |
| `src/crypto_manual_alert/agent_swarm/shadow_runner.py` | Shadow swarm runner orchestration over a prepared plan and worker map. |
| `src/crypto_manual_alert/agent_swarm/shadow_inputs.py` | Safe worker input view builder and redaction helper. |
| `src/crypto_manual_alert/agent_swarm/shadow_worker_failures.py` | Local failure contribution envelope builder for worker-level failures. |
| `src/crypto_manual_alert/agent_swarm/__init__.py` | stable package API facade, not a removable wrapper. It may expose supported runtime symbols but must not become a business logic owner. |
| `src/crypto_manual_alert/skills/__init__.py` | stable package API facade, not a removable wrapper. It may expose skill facade symbols and the legacy final-engine allowlist but must not become a runtime owner. |

These modules still need ordinary structure tests and ownership reviews, but they should not be recorded as removable wrappers until a canonical replacement exists.
