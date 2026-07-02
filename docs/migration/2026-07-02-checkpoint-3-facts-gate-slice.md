# Checkpoint 3 Facts Gate Slice

Date: 2026-07-02

Source plan: `docs/formal/31-受控AgentSwarm主链收敛与质量切换计划.md`

## Scope

This is a partial Checkpoint 3 implementation. It strengthens the facts gate but does not complete the full real-time fact layer.

## Changes

- `EvidencePacket.can_satisfy_execution_fact` now requires both:
  - `source_type == exchange_native`
  - `freshness_status == fresh`
- `EvidencePacket` now carries `source_tier`.
- Source classification now distinguishes:
  - `exchange_native`
  - `official`
  - `aggregator_api`
  - `web_derived`
  - `search_derived`
  - `fixture`
- Market evidence freshness now applies per-data-type TTL defaults.
- Stale exchange-native points no longer satisfy execution facts.
- Conflicting exchange-native values for the same hard execution fact now make that fact ineligible and hard fail the facts gate.
- `liquidation` and `liquidation_heatmap` are normalized to the `liquidation` data type.
- FactsGate now distinguishes:
  - hard execution facts: `mark`, `index`, `order_book`
  - auxiliary derivatives/crowding facts: `funding`, `open_interest`, `liquidation`
- Missing hard execution facts still hard block opening/trigger/flip.
- Missing auxiliary derivatives/crowding facts now produce:
  - `severity: soft_downgrade`
  - `missing_auxiliary_facts`
  - `confidence_cap: 0.58`
  - `confidence_cap_reasons: ["facts_gate:derivatives_facts_missing"]`
- `DecisionInput` now includes facts-gate auxiliary missing facts in `missing_facts`.
- `DecisionInput.confidence_policy` now applies facts-gate confidence caps.
- `EvidencePacket` now records fallback metadata for lower-tier market data:
  - `fallback_used`
  - `fallback_reason`
  - existing `source_tier`
- Fresh fallback sources can cover auxiliary derivatives/crowding facts, but not hard execution facts.
- Core execution facts still require fresh `exchange_native` evidence.
- `can_satisfy_execution_fact` is now true only for hard execution facts, so fresh exchange-native auxiliary facts do not masquerade as core execution facts.
- FactsGate now records fallback usage:
  - `fallback_used`
  - `fallback_source_types`
  - `confidence_cap_reasons: ["facts_gate:fallback_source_used"]` when fallback evidence participates.
- `DecisionInput` evidence refs now preserve fallback metadata and inherit fallback confidence-cap reasons.
- Event status now has a dedicated fact gate path:
  - `active_event_status` data type.
  - `event_pool` source type.
  - event status TTL.
  - `missing_event_facts`.
  - `facts_gate:event_status_stale`.
  - `confidence_cap: 0.55` when stale event status hard-blocks directional actions.
- Missing `active_event_status` now fails closed instead of silently passing.
- Event status freshness now prefers payload `refreshed_at` before falling back to the point timestamp.
- `DecisionInput` now includes event missing facts and event confidence-cap reasons.
- `SkillRuntime` now includes `event-pool.md` in required references, prompt context, and skill hash calculation.
- Macro event evidence now has a surprise contract:
  - `event_name`
  - `consensus`
  - `actual`
  - `surprise`
  - `market_reaction`
  - `released_at`
- Incomplete `macro_event` evidence now produces:
  - `missing_macro_facts`
  - `confidence_cap: 0.58`
  - `confidence_cap_reasons: ["facts_gate:macro_surprise_incomplete"]`
- `DecisionInput` now includes macro missing facts and macro confidence-cap reasons.

## Verification

Commands run:

```powershell
python -m pytest tests/artifacts/test_evidence_packets.py::test_stale_exchange_native_points_cannot_satisfy_execution_facts tests/artifacts/test_evidence_packets.py::test_facts_gate_caps_confidence_when_derivatives_or_liquidation_facts_are_missing -q
python -m pytest tests/artifacts/test_evidence_packets.py::test_aggregator_market_points_are_tiered_but_cannot_satisfy_execution_facts tests/artifacts/test_evidence_packets.py::test_old_exchange_native_points_are_stale_by_data_type_ttl tests/artifacts/test_evidence_packets.py::test_official_and_web_derived_sources_are_classified_with_priority_tiers -q
python -m pytest tests/artifacts/test_evidence_packets.py::test_conflicting_exchange_native_execution_facts_are_hard_failed -q
python -m pytest tests/decision/test_decision_input.py::test_decision_input_confidence_policy_applies_facts_gate_soft_cap -q
python -m pytest tests/artifacts/test_evidence_packets.py::test_auxiliary_fallback_sources_are_marked_and_cap_confidence tests/artifacts/test_evidence_packets.py::test_facts_gate_hard_fails_when_execution_facts_are_only_search_derived tests/decision/test_decision_input.py::test_decision_input_confidence_policy_applies_fallback_source_cap -q
python -m pytest tests/artifacts/test_evidence_packets.py::test_exchange_native_auxiliary_points_are_not_core_execution_facts tests/artifacts/test_evidence_packets.py::test_core_execution_fact_fallback_matrix_cannot_satisfy_execution_facts tests/artifacts/test_evidence_packets.py::test_stale_auxiliary_fallback_source_is_missing_and_cap_confidence -q
python -m pytest tests/artifacts/test_evidence_packets.py::test_fresh_active_event_status_satisfies_event_fact_gate tests/artifacts/test_evidence_packets.py::test_stale_event_pool_status_hard_blocks_directional_actions tests/decision/test_decision_input.py::test_decision_input_inherits_event_status_stale_hard_block -q
python -m pytest tests/artifacts/test_evidence_packets.py::test_missing_active_event_status_hard_blocks_directional_actions tests/artifacts/test_evidence_packets.py::test_event_pool_status_uses_payload_refreshed_at_for_freshness tests/artifacts/test_evidence_packets.py::test_event_status_without_timestamp_or_refreshed_at_hard_blocks_directional_actions tests/artifacts/test_evidence_packets.py::test_fresh_official_active_event_status_satisfies_event_fact_gate tests/skills/test_runtime_contract.py::test_skill_runtime_hash_changes_when_event_pool_changes -q
python -m pytest tests/artifacts/test_evidence_packets.py::test_complete_macro_event_surprise_fields_do_not_cap_confidence tests/artifacts/test_evidence_packets.py::test_macro_event_with_only_name_is_incomplete_and_caps_confidence tests/artifacts/test_evidence_packets.py::test_macro_event_missing_market_reaction_is_incomplete_even_from_official_source tests/decision/test_decision_input.py::test_decision_input_inherits_macro_surprise_incomplete_cap -q
python -m pytest tests/artifacts/test_evidence_packets.py::test_any_incomplete_macro_event_keeps_macro_surprise_downgrade tests/artifacts/test_evidence_packets.py::test_complete_macro_event_surprise_fields_do_not_cap_confidence tests/artifacts/test_evidence_packets.py::test_macro_event_with_only_name_is_incomplete_and_caps_confidence tests/artifacts/test_evidence_packets.py::test_macro_event_missing_market_reaction_is_incomplete_even_from_official_source tests/decision/test_decision_input.py::test_decision_input_inherits_macro_surprise_incomplete_cap -q
python -m pytest tests/artifacts tests/decision/test_decision_input.py -q
python -m pytest tests/artifacts tests/decision/test_decision_input.py tests/decision/test_production_control_gate.py -q
python -m pytest tests/skills/test_runtime_contract.py tests/workflow/test_market_context_step.py -q
python -m pytest tests/skills -q
python -m pytest tests/workflow/test_pre_final_orchestration.py -q
python -m pytest tests/workflow/test_run_executor.py -q
python -m pytest tests/decision/test_replayable_input.py tests/eval/test_context_artifact_readback.py -q
python -m pytest tests/structure/test_formal_docs_current_state.py -q
```

Observed result:

- Focused stale-fact and derivatives confidence-cap tests passed.
- Source priority and TTL tests passed.
- Conflicting execution fact test passed.
- Fallback ladder tests passed.
- Reviewer-requested fallback matrix and auxiliary fact tests passed.
- Artifact and DecisionInput suites passed after fallback schema extension.
- Event status freshness and stale event-pool tests passed.
- Missing event status and payload `refreshed_at` freshness tests passed.
- SkillRuntime event-pool manifest tests passed.
- Macro surprise contract tests passed.
- Macro mixed complete/incomplete evidence behavior is locked: any incomplete macro event keeps the macro surprise downgrade.
- Checkpoint 3 current artifact/decision/control-gate suite passed.
- Workflow and replay readback regressions passed. The large combined workflow/replay command can exceed local shell timeout, so final verification used equivalent split commands.

## Checkpoint 3 Status

Checkpoint 3 is complete. The next implementation checkpoint is Checkpoint 4: Agent/Skill business decomposition.
