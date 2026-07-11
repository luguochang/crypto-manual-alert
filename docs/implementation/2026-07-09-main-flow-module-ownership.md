# Main Flow Module Ownership

Date: 2026-07-09

Purpose: freeze the current manual-alert production MVP boundary so backend work does not drift back into AgentSwarm, eval, raw trace, or observability expansion before the main flow has real external proof.

## Canonical Main Path

```text
POST /api/runs/manual -> build_manual_decision_request() -> RunExecutor.submit()
  -> LegacyPlanRunnerAdapter -> LegacyDecisionWorkflow
  -> decision.final legacy_prompt -> parser.strict_json -> production_control.check -> risk.check
  -> persist_run_result() -> JournalQueryRepository.get_run_detail()
  -> business_summary/result_review/notification projection
```

This is the only production MVP path for the current recovery. It is manual-only and must preserve:

- `manual_execution_required=true`
- `auto_order_enabled=false`
- `decision.final_input_mode=legacy_prompt`
- `decision.candidate_sidecar_mode=disabled`
- `workflow.execution_mode=legacy_baseline`

Production final input remains legacy_prompt.

`query_text` remains audit_note. It records the operator's focus or audit note. It does not yet drive facts, worker selection, event budgets, lead planning, or the final decision input.

query_text remains audit_note.

## Main Path Owners

Every new backend module or route must declare one `runtime_role` before it can be treated as part of the recovery plan:

| runtime_role | Meaning |
| --- | --- |
| `production_main` | Executes the current manual alert MVP path. |
| `production_blocking_audit` | Produces audit evidence that can block unsafe output, but cannot become final decision input. |
| `product_projection` | Converts stored decision/outcome data into user-readable product surfaces. |
| `diagnostic_projection` | Exposes raw, trace, payload, matrix, or engineering-only views. |
| `eval_sidecar` | Runs replay, judge, promotion, or outcome evaluation outside the production run. |
| `replay_only` | Reconstructs or replays prior artifacts without changing live decisions. |
| `future_candidate` | Candidate architecture that requires a separate design, switch review, release gate, and rollback plan before production use. |

If a module cannot be assigned exactly one primary role, split it or keep it out of the production MVP path.

These files are allowed to be treated as production main-path modules for the current recovery:

| Module | Ownership |
| --- | --- |
| `src/crypto_manual_alert/api/routes_runs.py` | Manual run API entry, async run polling, run detail/list projection entry. |
| `src/crypto_manual_alert/context/request.py` | Builds the manual decision request and preserves user text as audit note. |
| `src/crypto_manual_alert/workflow/executor.py` | Runtime submission boundary and execution status lifecycle. |
| `src/crypto_manual_alert/workflow/legacy_adapter.py` | Adapter from executor request to legacy decision workflow. |
| `src/crypto_manual_alert/workflow/legacy_decision_workflow.py` | Current manual alert decision workflow. |
| `src/crypto_manual_alert/workflow/persistence_payload.py` | Builds durable run payloads, including `main_path_contract`. |
| `src/crypto_manual_alert/workflow/run_persistence_step.py` | Persists workflow result and projections. |
| `src/crypto_manual_alert/decision/final_engine.py` | Current final decision engine call and LLM/fixture boundary. |
| `src/crypto_manual_alert/decision/plan_parser.py` | Strict JSON plan parsing contract. |
| `src/crypto_manual_alert/decision/production_control_gate.py` | Production readiness and manual-only control gate. |
| `src/crypto_manual_alert/decision/risk.py` | Risk gate and allowed/blocked verdict logic. |
| `src/crypto_manual_alert/market/providers.py` | Market data provider boundary, including real OKX public evidence. |
| `src/crypto_manual_alert/market/event_status.py` | Macro/no-active-event readiness evidence. |
| `src/crypto_manual_alert/notification/sinks.py` | Manual notification sink boundary, including Bark status. |
| `src/crypto_manual_alert/storage/journal.py` | Durable run journal writes. |
| `src/crypto_manual_alert/storage/journal_rows.py` | Journal row projection, including persisted `main_path_contract`. |
| `src/crypto_manual_alert/storage/query_repository.py` | Run list/detail read model. |
| `src/crypto_manual_alert/storage/business_summary.py` | Product-readable manual alert summary projection. |
| `src/crypto_manual_alert/storage/result_review.py` | Result review and outcome visibility projection. |
| `frontend/src/lib/schemas/manual-run.ts` | Manual-run API response schema, preserving `main_path_contract`. |
| `frontend/src/lib/schemas/runs.ts` | Run detail schema, preserving the same `main_path_contract`. |

Changes in these files may affect the product main flow. They need focused tests and, for user-visible behavior, local browser or hosted visual proof.

## Production Blocking Audit Owners

Some modules are not production final input, but they are also not harmless decoration. Their role is `production_blocking_audit`: they produce audit evidence that may block an unsafe manual alert through the production control gate.

The standard rule is:

```text
pre_final_orchestration, shadow workers, DecisionInput candidate, and candidate audit do not enter FinalDecisionAgent input;
gate failures may be promoted by production_control_gate.
```

These modules are audit-only input to production-blocking gate:

- `workflow/pre_final_orchestration.py`
- `orchestration/**`
- `lead/**`
- `agent_swarm/**`
- `artifacts/**`
- `decision/decision_input*`
- `decision/pre_final*`
- `decision/candidate*`

They must not change `decision.final_input_mode`, write the final plan, send notifications, or bypass `legacy_prompt`. They may only contribute structured gate evidence through the existing control/risk boundary.

## Sidecar, Eval, And Diagnostic Owners

The following are useful engineering systems, but they are not the production MVP final input path:

| Area | Current boundary |
| --- | --- |
| `agent_swarm/**` | Sidecar and production_blocking_audit evidence. Not a production default path. |
| `lead/**` | Sidecar planning/lead-agent experiments and production_blocking_audit evidence. |
| `orchestration/**` | Shadow/audit orchestration and production_blocking_audit evidence. |
| `artifacts/**` | Diagnostic, replay, and production_blocking_audit support artifacts. |
| `workflow/pre_final_orchestration.py` | Pre-final sidecar orchestration only. |
| `workflow/candidate_sidecar_step.py` | Candidate sidecar only. |
| `workflow/controlled_adapter.py` | Controlled experimental adapter, not current MVP main path. |
| `decision/decision_input*` | Candidate/decision-input experiments and audit material. |
| `decision/pre_final*` | Pre-final candidate/eval material. |
| `decision/candidate*` | Candidate final or comparison material. |
| `eval/**` | Evaluation, replay, judge, and outcome audit workflows. |
| `api/routes_eval.py` | Eval workbench API, not manual alert production path. |
| telemetry, observability, raw payload views | Diagnostics only. They must stay labeled or gated away from ordinary product routes. |

production_candidate_swarm is not the default main path.

No new AgentSwarm/eval expansion before P0 external proof.

## Projection Rules

Product and diagnostic projections must stay read-only:

- business_summary/result_review/agent_audit_view are projections.
- They must not call external providers.
- They must not change verdicts.
- They must not write journal rows.
- They must not trigger notifications.
- They must not become the next run's real-time decision input.

Eval routes must not write production plan_runs or trigger Bark. `api/routes_eval.py` and `eval/**` can write eval/outcome/promotion artifacts only.

eval routes must not write production plan_runs or trigger Bark.

## Proof Boundaries

The following proof levels must stay separate in docs, tests, logs, and release notes:

- `fixture`: local fixture provider only.
- `mock`: local mock LLM, mock OKX, or mocked outcome visibility only.
- `staging`: local staging wiring, including mock OKX actionable rehearsal.
- `local-browser`: real local API, production Next build, browser DOM/visual checks.
- `hosted-runtime`: hosted API/frontend starts and manual run path responds.
- `prod-config`: hosted runtime has production-intent configuration.
- `prod-actionable`: real external LLM, real OKX public data, Bark sent, no-active-event assertion, allowed manual review, legacy prompt, sidecar disabled, manual-only safety.
- `real-outcome`: real exchange-native matured scorable outcome collected and visible.

fixture/mock/staging/hosted-runtime are not production success.

Strict gate exit code `2` for missing readiness is an honest block. Do not weaken it to make a demo pass.

Every persisted manual run should carry a run-level `main_path_contract` when it is produced through the current main path. The current contract records environment-specific proof levels, including `proof_level=mock` for the local mock-LLM stack and `proof_level=production-intent-contract` for production-intent config contracts. The invariant fields are `production_success=false`, `hosted_proof_required=true`, `does_not_prove=hosted_prod_actionable`, `runtime_role=production_main`, `final_input_contract.mode=legacy_prompt`, `manual_only.manual_execution_required=true`, and `manual_only.auto_order_enabled=false`. This makes the proof boundary durable on the run itself, but still does not replace the hosted `prod-actionable` and `real-outcome` gates.

## P0 Before More Architecture Expansion

Backend cleanup should reduce cognitive overhead, not change the current production input mode. Until hosted `prod-actionable`, hosted visual proof, and hosted `real-outcome` pass:

- keep `legacy_prompt` as the production final input;
- keep `query_text` as `audit_note`;
- keep candidate, AgentSwarm, raw payload, and eval outputs sidecar-only;
- prefer product-readable projections over raw JSON on ordinary routes;
- require any route or UI that exposes raw payloads to be explicitly diagnostic;
- do not add new orchestration layers to the main path.

## Change Discipline

When a future change touches main path owners:

1. Add or update the smallest behavior test first.
2. Verify the test fails for the missing or broken behavior.
3. Implement the smallest production change.
4. Run focused tests.
5. If the behavior is visible in the workbench, run the relevant Playwright gate.
6. Record the proof level in the current delivery checklist.

When a future change touches sidecar/eval/diagnostic owners:

1. State why it is needed before P0, or defer it.
2. Keep it out of `decision.final_input_mode`.
3. Keep product navigation away from raw JSON-first surfaces.
4. Do not describe its success as production success unless the P0 hosted gates pass.
