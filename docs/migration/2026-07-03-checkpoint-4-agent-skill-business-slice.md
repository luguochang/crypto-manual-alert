# Checkpoint 4 Agent/Skill 业务化实施记录

Date: 2026-07-03

Source plan: `docs/formal/31-受控AgentSwarm主链收敛与质量切换计划.md`

## Status

Checkpoint 4 is complete.

Completed slices:

- 4A. 建立 `market_agents/` canonical owner 和结构护栏。
- 4B. 固化 `AgentContribution` 业务契约。
- 4C. 迁移现有本地审查 worker 到 `market_agents/`。
- 4D.1. `LiveFactAgent` 最小闭环。
- 4D.2. `DerivativesAgent` 最小闭环。
- 4D.3. `MacroEventAgent` 最小闭环。
- 4D.4. `RootCauseAgent` 与 `MarketSentimentAgent` 结构化升级。
- 4D.5. `DataQualityAgent` 与 `ExecutionRiskAgent` 专项业务测试。
- 4E. Skill facade 与实时信息边界。
- 4F. Lead/Harness/Runner 接入。
- 4G. Checkpoint 4 收口验收。

## 4A `market_agents/` 归属基线

建立 `src/crypto_manual_alert/market_agents/` 作为业务 Worker Agent 的 canonical owner。`agent_swarm/` 保留 runtime、registry 和兼容导出，不再承载市场业务规则。

Verification:

```powershell
python -m pytest tests/structure/test_market_agent_boundaries.py tests/structure/test_local_worker_boundaries.py -q
python -m pytest tests/agent_swarm/test_workers.py tests/agent_swarm/test_registry.py -q
```

Result: passed.

## 4B `AgentContribution` 业务契约

稳定 Lead synthesis、DecisionInput、release/eval gates 消费的 worker projection。harness 明确禁止 worker 输出可执行交易字段，例如 `entry`、`stop`、`target`、`leverage`、`position_size`。

Verification:

```powershell
python -m pytest tests/artifacts/test_contributions.py tests/agent_swarm/test_harness_validation.py tests/decision/test_decision_input.py -q
python -m pytest tests/agent_swarm tests/lead -q
python -m pytest tests/workflow/test_pre_final_orchestration.py tests/workflow/test_run_executor.py -q
```

Result: passed.

## 4C 本地审查 worker 迁移

将现有 RootCause、MarketSentiment、DataQuality、ExecutionRisk 本地审查 worker 迁移到 `market_agents/`，旧 `agent_swarm.local_workers.*` 路径保留兼容 re-export。

Verification:

```powershell
python -m pytest tests/market_agents/test_local_workers.py -q
python -m pytest tests/agent_swarm/test_workers.py tests/agent_swarm/test_registry.py -q
python -m pytest tests/structure/test_market_agent_boundaries.py tests/structure/test_local_worker_boundaries.py -q
```

Result: passed.

## 4D.1 `LiveFactAgent`

Added:

- `src/crypto_manual_alert/market_agents/live_fact.py`
- `tests/market_agents/test_live_fact_agent.py`

What changed:

- `LiveFactAgent` only consumes existing snapshot and facts_gate input.
- It audits execution fact coverage for `mark`, `index`, `order_book`.
- It emits neutral audit claims only and `decision_effect=none`.
- Required shadow worker coverage increased to five workers at that slice.

Verification:

```powershell
python -m pytest tests/market_agents/test_live_fact_agent.py tests/lead/test_agent.py tests/agent_swarm/test_registry.py tests/agent_swarm/test_shadow_swarm.py -q
python -m pytest tests/agent_swarm/test_workers.py tests/agent_swarm/test_shadow_orchestration.py tests/workflow/test_pre_final_orchestration.py tests/workflow/test_run_executor.py -q
python -m pytest tests/decision/test_switch_readiness.py tests/cli/test_runner_cli.py -q
python -m pytest tests/structure -q
```

Result: passed.

## 4D.2 `DerivativesAgent`

Added:

- `src/crypto_manual_alert/market_agents/derivatives.py`
- `tests/market_agents/test_derivatives_agent.py`

What changed:

- `DerivativesAgent` only consumes existing snapshot and facts_gate input.
- It audits funding, open interest, liquidation map, basis, long/short ratio, taker flow and crowding state.
- Missing derivative facts produce missing facts, conflicts, required confirmations, confidence cap and blocked action classes.
- Required shadow worker coverage increased to six workers at that slice.

Verification:

```powershell
python -m pytest tests/market_agents/test_derivatives_agent.py tests/market_agents/test_local_workers.py tests/lead/test_agent.py tests/agent_swarm/test_registry.py tests/agent_swarm/test_shadow_swarm.py -q
python -m pytest tests/agent_swarm/test_shadow_orchestration.py -q
python -m pytest tests/workflow/test_pre_final_orchestration.py -q
python -m pytest tests/workflow/test_run_executor.py -q
python -m pytest tests/cli/test_runner_cli.py -q
python -m pytest tests/structure -q
```

Result: passed.

## 4D.3 `MacroEventAgent`

Added:

- `src/crypto_manual_alert/market_agents/macro_event.py`
- `tests/market_agents/test_macro_event_agent.py`

Modified:

- `src/crypto_manual_alert/market_agents/common.py`
- `src/crypto_manual_alert/market_agents/__init__.py`
- `src/crypto_manual_alert/market_agents/registry.py`
- `src/crypto_manual_alert/agent_swarm/local_workers/__init__.py`
- `src/crypto_manual_alert/agent_swarm/workers.py`
- `src/crypto_manual_alert/agent_swarm/registry.py`
- `src/crypto_manual_alert/orchestration/harness.py`
- `src/crypto_manual_alert/lead/agent.py`
- `src/crypto_manual_alert/lead/synthesis.py`
- `src/crypto_manual_alert/decision/switch_readiness.py`

What changed:

- `MacroEventAgent` is a local audit worker only.
- It consumes only existing snapshot, facts_gate and optional evidence packets.
- It does not live fetch, web search, write journal or send notifications.
- It emits `decision_effect=none`.
- It structures event status, macro event details, surprise, market reaction, event compression, missing event facts, missing macro facts, blocked action classes and required confirmations.
- Missing event status blocks opening/trigger/flip and caps confidence unless an upstream facts_gate cap already applies.
- Missing macro facts cap confidence.
- Default required shadow worker coverage increased from six to seven.
- `llm_tool_shadow` keeps MacroEventAgent local-audit only, like LiveFactAgent and DerivativesAgent.

Red test evidence:

```powershell
python -m pytest tests/market_agents/test_macro_event_agent.py -q
```

Observed: failed because `crypto_manual_alert.market_agents.macro_event` did not exist.

Green verification:

```powershell
python -m pytest tests/market_agents/test_macro_event_agent.py tests/market_agents/test_local_workers.py tests/lead/test_agent.py tests/agent_swarm/test_registry.py tests/agent_swarm/test_shadow_swarm.py tests/agent_swarm/test_workers.py tests/workflow/test_pre_final_orchestration.py tests/decision/test_switch_readiness.py -q
python -m pytest tests/agent_swarm/test_workers.py tests/agent_swarm/test_shadow_orchestration.py tests/workflow/test_pre_final_orchestration.py tests/workflow/test_run_executor.py tests/decision/test_switch_readiness.py tests/cli/test_runner_cli.py -q -x
python -m pytest tests/market_agents tests/agent_swarm tests/lead tests/decision/test_switch_readiness.py -q
python -m pytest tests/workflow/test_pre_final_orchestration.py tests/workflow/test_run_executor.py -q
python -m pytest tests/cli/test_runner_cli.py -q
python -m pytest tests/structure -q
```

Result: passed.

## 4D.4 `RootCauseAgent` 与 `MarketSentimentAgent` 结构化升级

Added:

- `tests/market_agents/test_root_cause_agent.py`
- `tests/market_agents/test_sentiment_crowding_agent.py`

Modified:

- `src/crypto_manual_alert/market_agents/root_cause.py`
- `src/crypto_manual_alert/market_agents/sentiment_crowding.py`
- `tests/agent_swarm/test_workers.py`
- `tests/workflow/test_run_executor.py`

What changed:

- `RootCauseAgent` now outputs `root_cause_graph`, `direct_causes`, `second_order_causes`, `evidence_refs`, `missing_causal_facts`, `confidence_cap`, `confidence_cap_reasons` and `required_confirmations`.
- `RootCauseAgent` structures macro event surprise, derivative crowding amplifier and search-derived confirmation into replayable graph nodes.
- `MarketSentimentAgent` keeps the required worker manifest key while `SentimentCrowdingLocalWorker` remains the implementation class.
- `MarketSentimentAgent` now outputs `crowding_state`, `priced_in_assessment`, `reflexivity_risk`, `counter_thesis`, `missing_sentiment_facts` and `required_confirmations`.
- Search-derived sentiment remains confidence-capped and audit-only.
- The workflow replay/readback path now expects a structured counter thesis from `MarketSentimentAgent` when crowding evidence exists.
- `lead/synthesis.py` did not require logic changes; existing counter thesis and conflict refs already handled structured conflicts. Tests were updated to assert the new stronger counter thesis.

Red test evidence:

```powershell
python -m pytest tests/market_agents/test_root_cause_agent.py tests/market_agents/test_sentiment_crowding_agent.py -q
```

Observed:

- `RootCauseAgent` lacked `confidence_cap_reasons`, `root_cause_graph`, `direct_causes`, `second_order_causes` and related causal fields.
- `MarketSentimentAgent` lacked `crowding_state`, `priced_in_assessment`, `reflexivity_risk` and structured `counter_thesis`.

Green verification:

```powershell
python -m pytest tests/market_agents/test_root_cause_agent.py tests/market_agents/test_sentiment_crowding_agent.py -q
python -m pytest tests/market_agents tests/agent_swarm tests/lead tests/decision/test_switch_readiness.py -q
python -m pytest tests/workflow/test_pre_final_orchestration.py tests/workflow/test_run_executor.py -q
python -m pytest tests/cli/test_runner_cli.py -vv -x --durations=10
python -m pytest tests/structure -q
```

Result: passed.

## 4D.5 `DataQualityAgent` 与 `ExecutionRiskAgent` 专项业务测试

Added:

- `tests/market_agents/test_data_quality_agent.py`
- `tests/market_agents/test_execution_risk_agent.py`

Modified:

- `src/crypto_manual_alert/market_agents/data_quality.py`
- `src/crypto_manual_alert/market_agents/execution_risk.py`

What changed:

- `DataQualityAgent` now outputs `execution_fact_coverage`, `source_quality`, `staleness_details`, `conflicting_fact_details`, `missing_execution_facts`, `blocked_action_classes` and `required_confirmations`.
- `DataQualityAgent` distinguishes whether a fact is present from whether it can satisfy an execution fact. For example, an aggregator index can be present but still fail the exchange-native execution fact requirement.
- `DataQualityAgent` only lets `mark`, `index` and `order_book` from `snapshot.unavailable` enter missing execution facts. Non-execution unavailable prefixes are not echoed into conflicts or missing facts, which avoids harness forbidden-field leakage.
- `ExecutionRiskAgent` now outputs `hard_block`, `hard_block_reasons`, `allowed_action_class_reduction`, `manual_review_reminders`, `required_confirmations` and `execution_risk_summary`.
- `ExecutionRiskAgent` preserves the existing `execution_risk_hard_block` conflict and `facts_gate:execution_facts_missing` reason so existing DecisionInput, production control and release gate readback remain stable.
- Both workers remain local audit workers with `decision_effect=none` and do not write final decision, gate verdict, journal, notification or side-effect intent.

Red test evidence:

```powershell
python -m pytest tests/market_agents/test_data_quality_agent.py tests/market_agents/test_execution_risk_agent.py -q
```

Observed:

- `DataQualityAgent` lacked `execution_fact_coverage`, `source_quality`, `staleness_details` and `conflicting_fact_details`.
- `ExecutionRiskAgent` lacked `allowed_action_class_reduction`, `manual_review_reminders`, clean-path `hard_block` and `required_confirmations`.
- Subagent review found that arbitrary `snapshot.unavailable` prefixes could enter `missing_execution_facts`; `test_data_quality_agent_does_not_echo_non_execution_unavailable_prefixes` reproduced this before the filter was added.

Green verification:

```powershell
python -m pytest tests/market_agents/test_data_quality_agent.py tests/market_agents/test_execution_risk_agent.py -q
python -m pytest tests/market_agents tests/agent_swarm tests/lead tests/decision/test_switch_readiness.py -q
python -m pytest tests/workflow/test_pre_final_orchestration.py tests/workflow/test_run_executor.py -q
python -m pytest tests/cli/test_runner_cli.py -q -x
python -m pytest tests/structure -q
```

Result: passed.

## 4E Skill facade 与实时信息边界

Added:

- `src/crypto_manual_alert/skills/facade.py`
- `tests/skills/test_facade_contract.py`

Modified:

- `src/crypto_manual_alert/skills/__init__.py`
- `tests/structure/test_skill_runtime_boundaries.py`

What changed:

- Added `SkillTaskContext` as the controlled input object for skill facade calls.
- Added `SkillToolResult` as the structured tool result boundary. It is not a worker contribution and does not produce final decisions, gates, journals or notifications.
- Added typed/frozen `EvidenceCandidate` and `SkillConstraints`; `SkillToolResult` no longer accepts open `dict/list` payloads for evidence or constraints.
- Added `RealtimeSearchSkill`, `RootCauseSearchSkill`, `MarketSentimentSkill`, `MacroEventSkill` and `LiquidityOrderBookSkill`.
- Realtime/search-derived skills return `source_type=search_derived`, `can_satisfy_execution_fact=false` and `must_pass_facts_gate=true`.
- Root cause skill declares recursive factor search boundaries: `max_depth`, `timeout_seconds` and allowed factor types.
- Market sentiment skill declares objective-fact versus crowding separation and outputs for `crowding`, `priced_in` and `reflexivity`.
- Macro event skill declares required event status and macro surprise fields.
- Liquidity/order-book skill is restricted to `exchange_native` execution-fact candidates and states that search-derived results cannot satisfy execution facts.
- `skills.__init__` exports the facade contract through lazy imports.
- `SkillToolResult.to_public_dict()` now assembles output only from whitelisted typed fields and returns fresh dict/list snapshots.
- Per-skill contract matrix locks skill name, task id, result type, source type, execution-fact capability and constraints as a single legal combination.
- Structure tests prevent skill facade modules from importing business agents, swarm runtime, final decision runtime, workflow modules, or worker contribution types.

Red test evidence:

```powershell
python -m pytest tests/skills/test_facade_contract.py tests/structure/test_skill_runtime_boundaries.py -q
python -m pytest tests/skills/test_facade_contract.py::test_skill_facade_contract_is_exported_from_skills_package -q
```

Observed:

- `crypto_manual_alert.skills.facade` did not exist.
- `crypto_manual_alert.skills` did not export `SkillTaskContext`, `SkillToolResult` or facade classes.

Green verification:

```powershell
python -m pytest tests/skills/test_facade_contract.py tests/structure/test_skill_runtime_boundaries.py -q
python -m pytest tests/skills -q
python -m pytest tests/market_agents tests/agent_swarm tests/lead tests/decision/test_switch_readiness.py -q
python -m pytest tests/workflow/test_pre_final_orchestration.py tests/workflow/test_run_executor.py -q
python -m pytest tests/cli/test_runner_cli.py -q -x
python -m pytest tests/structure -q
```

Result: passed.

Review:

- Structure/contract review: Approved.
- Security boundary review: Approved.

## 4F Lead/Harness/Runner 接入

Modified:

- `src/crypto_manual_alert/decision/decision_input.py`
- `src/crypto_manual_alert/decision/decision_input_policy.py`
- `src/crypto_manual_alert/artifacts/contributions.py`
- `src/crypto_manual_alert/artifacts/__init__.py`
- `src/crypto_manual_alert/context/run_context.py`
- `src/crypto_manual_alert/orchestration/harness.py`
- `tests/artifacts/test_contributions.py`
- `tests/decision/test_decision_input.py`
- `tests/context/test_run_context.py`
- `tests/agent_swarm/test_harness_validation.py`
- `tests/workflow/test_pre_final_orchestration.py`

What changed:

- Pre-final `DecisionInput` now carries contribution refs for the seven required shadow workers: `LiveFactAgent`, `DerivativesAgent`, `MacroEventAgent`, `RootCauseAgent`, `MarketSentimentAgent`, `DataQualityAgent`, `ExecutionRiskAgent`.
- Contribution refs include the 4F safety projection fields: `task_id`, `evidence_ids`, `confidence_cap`, `confidence_cap_reasons`, `blocked_actions`, `hard_block`, `hard_block_reasons`, `manual_review_reminders`, `allowed_action_class_reduction`, `required_confirmations`, `trace_ref`, `output_hash`.
- Pre-final validation reports `decision_input.required_worker_refs_missing` as a hard fail when a required worker ref is missing and no valid drop record exists.
- `DecisionRunContext.to_artifact_summary()` exposes safe contribution refs with the same safety fields and still avoids raw payload leakage.
- `confidence_cap` is always explicit in contribution refs; no-cap workers project `confidence_cap: None`.
- `artifacts.contributions.contribution_safety_ref_fields()` is now the shared 4F safety projection helper for `DecisionInput` and `RunContext`.
- Harness validation rejects raw `SkillToolResult` public dicts and real `SkillToolResult` objects embedded inside `AgentContribution`, preserving the skill facade boundary.
- Production final input remains `legacy_prompt`; candidate/pre-final artifacts remain audit sidecars with `decision_effect=none`.

Red test evidence:

```powershell
python -m pytest tests/decision/test_decision_input.py::test_pre_final_decision_input_contribution_refs_include_required_workers_and_safety_fields -q
python -m pytest tests/agent_swarm/test_harness_validation.py::test_harness_validation_rejects_raw_skill_tool_result_payload_inside_contribution -q
python -m pytest tests/decision/test_decision_input.py::test_pre_final_decision_input_fails_when_required_worker_refs_are_missing_without_drop_record -q
python -m pytest tests/context/test_run_context.py::test_decision_run_context_contribution_refs_include_pre_final_safety_fields -q
```

Observed:

- Pre-final contribution refs initially missed safety fields such as `confidence_cap_reasons`.
- Actual pre-final refs omitted `confidence_cap` for workers without a cap.
- Harness initially accepted raw skill tool result payloads embedded in contribution constraints.
- Harness initially accepted real `SkillToolResult` objects embedded in contribution constraints.
- Pre-final validation initially did not hard-fail missing required worker refs.
- Context artifact summary initially omitted the pre-final safety projection fields.

Green verification:

```powershell
python -m pytest tests/decision/test_decision_input.py tests/context/test_run_context.py -q
python -m pytest tests/artifacts/test_artifacts_package_structure.py tests/artifacts/test_contributions.py -q
python -m pytest tests/agent_swarm/test_harness_validation.py tests/workflow/test_pre_final_orchestration.py -q
python -m pytest tests/workflow/test_pre_final_orchestration.py tests/workflow/test_run_executor.py tests/decision/test_decision_input.py -q
python -m pytest tests/market_agents tests/agent_swarm tests/lead tests/skills -q
python -m pytest tests/structure -q
```

Result: passed.

Review follow-up:

- Fixed high-priority spec review findings: explicit `confidence_cap` projection and raw `SkillToolResult` object rejection.
- Deferred hardening: Harness required-agent coverage, forbidden-field natural-language false positives and `cap_applied_by_gate` naming remain design-quality items for later checkpoints. 4F keeps required worker coverage in LeadAgent planning, pre-final DecisionInput validation and eval worker-manifest gates rather than changing Harness postflight defaults.

Verification scope note:

- `tests/workflow/test_run_executor.py` is a deep Runner/Journal/Replay/Release gate suite and should be used for checkpoint closeout or entry-boundary changes.
- Field projection, artifact summary and harness contract changes should use focused tests first, then one full-run validation at closeout.

## Boundaries Preserved

- Production still defaults to `legacy_baseline + legacy_prompt`.
- `DecisionInput` is still candidate/audit sidecar only.
- This checkpoint slice does not enable production LLM/tool workers.
- This checkpoint slice does not change `decision.final_input_mode`.
- This checkpoint slice does not add journal or notification side effects.
- Current workers remain audit-only workers with `decision_effect=none`.

## 4G Checkpoint 4 收口验收

Decision:

- `FlowLiquidityAgent` remains deferred.
- Rationale: Checkpoint 4 already has seven required workers and the liquidity/order-book capability is currently represented as `LiquidityOrderBookSkill`, with execution facts constrained by `LiveFactAgent`, `DataQualityAgent` and `ExecutionRiskAgent`.
- Adding an eighth required worker at closeout would expand the worker manifest, LeadAgent plan, DecisionInput refs, eval/replay gates and tests without a separately defined acceptance standard.

Closeout verification:

```powershell
python -m pytest tests/workflow/test_pre_final_orchestration.py tests/workflow/test_run_executor.py tests/decision/test_decision_input.py -q
python -m pytest tests/market_agents tests/agent_swarm tests/lead tests/skills -q
python -m pytest tests/structure -q
```

Result: passed.

Remaining follow-up moves to Checkpoint 5:

- Define the candidate `DecisionInput` schema and pre-final input gate before building candidate FinalDecisionAgent.
- Keep production default on `legacy_baseline + legacy_prompt` until the later controlled switch checkpoint.
