from __future__ import annotations

from pathlib import Path


DOC_29 = Path("docs/formal/29-Agent与Skill拆分详细设计.md")
DOC_30 = Path("docs/formal/30-受控AgentSwarm-MVP实施契约.md")
DOC_31 = Path("docs/formal/31-受控AgentSwarm主链收敛与质量切换计划.md")
DOC_33 = Path("docs/formal/33-compatibility-wrapper-lifecycle.md")
DOC_INDEX = Path("docs/formal/00-文档索引.md")
README = Path("README.md")
DEPLOYMENT = Path("docs/deployment.md")


AGENT_AUDIT_VIEW = Path("src/crypto_manual_alert/storage/agent_audit_view.py")
FRONTEND_RUN_SCHEMA = Path("frontend/src/lib/schemas/runs.ts")
FRONTEND_RUN_PAGE = Path("frontend/src/app/runs/[traceId]/page.tsx")
FRONTEND_AGENT_AUDIT_PANEL = Path("frontend/src/app/runs/[traceId]/agent-audit-panel.tsx")
LOCAL_STACK_SMOKE = Path("tools/local_stack/smoke_local_stack.py")


def test_formal_contract_records_current_canonical_paths():
    source = DOC_30.read_text(encoding="utf-8")

    required_current_paths = {
        "`orchestration/shadow_audit.py`",
        "`orchestration/shadow_failure.py`",
        "`lead/agent.py`",
        "`lead/default_plan.py`",
        "`agent_swarm/default_lead_plan.py`",
        "`agent_swarm/shadow_worker_failures.py`",
        "`agent_swarm/local_workers/`",
        "`decision/replay_observed_refs.py`",
        "`decision/replay_worker_refs.py`",
        "`decision/replay_sanitization.py`",
        "`decision/decision_input_policy.py`",
        "`artifacts/hashing.py`",
        "`skills/context_loader.py`",
        "`skills/prompt_context.py`",
        "`decision/final_engine.py`",
        "`decision/pre_final_bundle.py`",
        "`decision/pre_final_switch_readiness.py`",
        "`research_pipeline/search_adapters.py`",
        "`research_pipeline/leader_synthesizers.py`",
        "`research_pipeline/llm_support.py`",
        "`research_pipeline/prompts.py`",
        "`storage/journal_schema.py`",
        "`storage/journal_rows.py`",
        "`eval/candidate_artifact_snapshots.py`",
        "`eval/context_artifact_summary.py`",
        "`eval/replayable_input_summary.py`",
        "`eval/candidate_artifact_consistency.py`",
        "`eval/worker_manifest_consistency.py`",
        "`eval/context_artifact_consistency.py`",
        "`eval/complete_replay_refs.py`",
        "`eval/counter_conflict_coverage.py`",
        "`eval/shadow_final_comparison.py`",
        "`eval/release_promotion_review.py`",
        "`eval/promotion_artifact_validation.py`",
        "`eval/candidate_artifact_validation.py`",
        "`eval/store_rows.py`",
        "`tests/structure/test_context_boundaries.py`",
        "`tests/structure/test_skill_runtime_boundaries.py`",
        "`tests/structure/test_eval_case_builder_boundaries.py`",
        "`tests/structure/test_eval_replay_boundaries.py`",
        "`tests/structure/test_release_gate_boundaries.py`",
        "`tests/structure/test_eval_store_boundaries.py`",
        "`tests/structure/test_shadow_swarm_boundaries.py`",
        "`tests/structure/test_orchestration_contract_boundaries.py`",
        "`tests/structure/test_root_package_structure.py`",
        "`tests/decision/test_pre_final_bundle.py`",
        "`tests/decision/test_pre_final_switch_readiness.py`",
        "`tests/workflow/test_run_executor.py`",
    }

    for path in required_current_paths:
        assert path in source

    assert "LeadAgent.plan_tasks(...)" in source


def test_agent_skill_design_distinguishes_shadow_progress_from_production_swarm_completion():
    source = DOC_29.read_text(encoding="utf-8")

    assert "shadow audit" in source
    assert "FinalDecisionAgent" in source
    assert "legacy prompt" in source


def test_formal_index_points_to_current_state_index_and_current_pipeline_shape():
    source = DOC_INDEX.read_text(encoding="utf-8")

    assert "31-" in source
    assert "30-" in source
    assert "LegacyDecisionWorkflow" in source
    assert "orchestration.shadow_audit" in source


def test_main_convergence_plan_records_execution_tracking_boundaries():
    source = DOC_31.read_text(encoding="utf-8")

    assert "legacy_baseline + legacy_prompt" in source
    assert "Checkpoint 8：Legacy 收敛" in source
    assert "Checkpoint 9：主流程与可视化审计收口" in source
    assert "decision.final_input_mode_switch_review_path" in source
    assert "fallback_behavior=legacy_prompt_on_candidate_failure" in source
    assert "auto_order_enabled=false" in source
    assert "`src/crypto_manual_alert/orchestration/`" in source
    assert "`src/crypto_manual_alert/agent_swarm/local_workers/`" in source
    assert "MarketSentimentAgent" in source
    assert "release gate" in source
    assert "tests/workflow/test_run_executor.py" in source


def test_formal_docs_do_not_reintroduce_stale_worker_count_or_owner_facts():
    combined = "\n".join(
        [
            DOC_29.read_text(encoding="utf-8"),
            DOC_30.read_text(encoding="utf-8"),
            DOC_31.read_text(encoding="utf-8"),
        ]
    )

    stale_phrases = [
        "4 个本地 shadow worker",
        "至少有 4 个独立 Worker Agent",
        "将 4 个本地 shadow worker",
        "默认计划仍只生成 4 个固定 shadow worker",
        "agent_swarm.local_workers` canonical",
        "`agent_swarm/local_workers/` 当 canonical owner",
    ]
    for phrase in stale_phrases:
        assert phrase not in combined

    assert "7 个 required shadow workers" in combined
    assert "`src/crypto_manual_alert/market_agents/` | 加密货币市场业务 Worker Agent 的 canonical owner" in combined
    assert "`src/crypto_manual_alert/agent_swarm/local_workers/` | 兼容 re-export only" in combined


def test_checkpoint_9_records_artifact_full_chain_guard():
    source = DOC_31.read_text(encoding="utf-8")

    assert "producer -> persistence -> API projection -> frontend view -> runtime smoke assertion" in source
    assert "新增 sidecar/artifact" in source
    assert "agent_audit_view" in source
    assert "tools/local_stack/smoke_local_stack.py" in source


def test_query_semantics_is_asserted_across_api_frontend_and_runtime_smoke():
    sources = {
        "agent_audit_view": AGENT_AUDIT_VIEW.read_text(encoding="utf-8"),
        "frontend_schema": FRONTEND_RUN_SCHEMA.read_text(encoding="utf-8"),
        "frontend_agent_audit_panel": FRONTEND_AGENT_AUDIT_PANEL.read_text(encoding="utf-8"),
        "runtime_smoke": LOCAL_STACK_SMOKE.read_text(encoding="utf-8"),
    }

    for name, source in sources.items():
        assert "query_semantics" in source, name
        if name != "frontend_agent_audit_panel":
            assert "audit_note" in source, name


def test_compatibility_wrapper_lifecycle_is_linked_from_main_plan():
    source = DOC_31.read_text(encoding="utf-8")

    assert DOC_33.exists()
    assert "33-compatibility-wrapper-lifecycle.md" in source


def test_current_execution_entry_is_consistent_across_public_docs():
    sources = {
        "README": README.read_text(encoding="utf-8"),
        "formal_index": DOC_INDEX.read_text(encoding="utf-8"),
        "deployment": DEPLOYMENT.read_text(encoding="utf-8"),
    }

    for name, source in sources.items():
        assert "34-生产级AgentSwarm优化目标与执行计划.md" in source, name
        assert "legacy_prompt" in source, name

    assert "当前执行阶段以 `31-受控AgentSwarm主链收敛与质量切换计划.md`" not in sources["formal_index"]
