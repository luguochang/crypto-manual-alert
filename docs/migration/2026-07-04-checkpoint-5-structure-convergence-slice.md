# Checkpoint 5 Structure Convergence Slice

## Scope

This slice tightens structure boundaries without changing the production decision path. Production final input remains `legacy_prompt`; Agent Swarm, DecisionInput, candidate final, and financial quality remain candidate/audit/eval paths.

## Completed

- Added frontend route boundary guard:
  - `tests/structure/test_frontend_route_boundaries.py`
  - Eval page must keep large tables and Financial Quality in components.
  - Run detail page must keep Agent Audit panels in components.
- Added root package import guard:
  - `src/crypto_manual_alert/__init__.py` must not import business modules.
- Split Eval frontend page:
  - `frontend/src/app/eval/eval-format.ts`
  - `frontend/src/app/eval/eval-candidates-table.tsx`
  - `frontend/src/app/eval/eval-replay-table.tsx`
  - `frontend/src/app/eval/eval-judge-scores-table.tsx`
  - `frontend/src/app/eval/financial-quality-panel.tsx`
  - `frontend/src/app/eval/page.tsx` reduced from 372 lines to 186 lines.
- Split EvalStore schema initialization:
  - `src/crypto_manual_alert/eval/store_schema.py`
  - `src/crypto_manual_alert/eval/store.py` delegates schema creation and no longer contains SQL DDL blocks.
  - `src/crypto_manual_alert/eval/store.py` reduced from 591 lines to 434 lines.
- Split Skill facade boundaries:
  - `src/crypto_manual_alert/skills/facade.py` now owns concrete Skill facade run logic only.
  - `src/crypto_manual_alert/skills/contracts.py` owns `SkillTaskContext`, `EvidenceCandidate`, `SkillConstraints`, and `SkillToolResult`.
  - `src/crypto_manual_alert/skills/contract_policy.py` owns allowed skill/result/source/task policy constants.
  - `src/crypto_manual_alert/skills/contract_validation.py` owns type, semantic-leakage, and skill-contract validation helpers.
  - `src/crypto_manual_alert/skills/facade.py` reduced from 596 lines to 157 lines.
- Synchronized documentation authority:
  - `README.md`
  - `docs/deployment.md`
  - `docs/formal/00-文档索引.md`
  - `docs/formal/33-compatibility-wrapper-lifecycle.md`

## Tests

Commands run:

```powershell
python -m pytest tests/structure/test_frontend_route_boundaries.py tests/structure/test_root_package_structure.py -q
python -m pytest tests/structure/test_formal_docs_current_state.py tests/structure/test_frontend_route_boundaries.py tests/structure/test_root_package_structure.py -q
python -m pytest tests/structure -q
python -m pytest tests/structure/test_eval_store_boundaries.py tests/eval/test_store_rows.py tests/eval/test_replay_llmjudge.py tests/api/test_eval_routes.py -q
python -m pytest tests/skills/test_facade_contract.py tests/structure/test_skill_runtime_boundaries.py -q
python -m pytest tests/skills tests/structure/test_skill_runtime_boundaries.py tests/structure/test_skill_executor_boundaries.py tests/agent_swarm/test_llm_tool_worker.py -q
python -m pytest tests/structure -q
npm run typecheck
npm run build
```

## Remaining Structure Debt

- `src/crypto_manual_alert/eval/release_gate.py` remains large.
- `src/crypto_manual_alert/eval/case_builder.py` remains large.
- `src/crypto_manual_alert/storage/agent_audit_view.py` remains large despite projection helpers.
- `src/crypto_manual_alert/storage/journal.py` remains large.
- `src/crypto_manual_alert/workflow/legacy_decision_workflow.py` still contains legacy orchestration details.

These should be handled in later bounded structure slices with tests first. They should not be moved just for cosmetics.

## Side Effect Statement

This slice only moves presentation/schema initialization code and documentation. It does not write production journal outcomes, send notifications, place orders, live fetch market data, or switch `decision.final_input_mode`.
