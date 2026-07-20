from __future__ import annotations

from pathlib import Path


DOC_29 = Path("docs/formal/29-Agent与Skill拆分详细设计.md")
DOC_30 = Path("docs/formal/30-受控AgentSwarm-MVP实施契约.md")
DOC_31 = Path("docs/formal/31-受控AgentSwarm主链收敛与质量切换计划.md")
DOC_33 = Path("docs/formal/33-compatibility-wrapper-lifecycle.md")
DOC_INDEX = Path("docs/formal/00-文档索引.md")
README = Path("README.md")
DEPLOYMENT = Path("docs/deployment.md")
MAIN_FLOW_CHECKPOINT = Path("docs/migration/2026-07-09-checkpoint-main-flow-recovery-and-proof-boundaries.md")
CURRENT_DELIVERY_CHECKLIST = Path("docs/implementation/2026-07-09-current-delivery-checklist.md")
MAIN_FLOW_PRODUCTION_RECOVERY_CHECKLIST = Path(
    "docs/implementation/2026-07-09-main-flow-production-recovery-checklist.md"
)
MAIN_FLOW_MODULE_OWNERSHIP = Path(
    "docs/implementation/2026-07-09-main-flow-module-ownership.md"
)


V2_IMPLEMENTATION_STATUS = Path("docs/v2/15-v2-implementation-status.md")
PRODUCT_API_SCHEMA = Path("frontend/src/lib/schemas/product-api.ts")
PRODUCT_API_CLIENT = Path("frontend/src/lib/api/product-client.ts")
PRODUCT_API_PROXY = Path("frontend/src/lib/api/product-proxy.ts")
OFFICIAL_RUN_STREAM = Path(
    "frontend/src/features/agent-runtime/official-run-stream.tsx"
)


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


def test_v2_product_api_contract_is_typed_from_zod_schema_through_same_origin_bff():
    schema = PRODUCT_API_SCHEMA.read_text(encoding="utf-8")
    client = PRODUCT_API_CLIENT.read_text(encoding="utf-8")
    proxy = PRODUCT_API_PROXY.read_text(encoding="utf-8")
    status = V2_IMPLEMENTATION_STATUS.read_text(encoding="utf-8")

    for required_text in (
        "analysisSubmissionSchema = z.strictObject",
        "query_text: z.string().trim().min(1).max(2000)",
        "productRunListSchema = z.strictObject",
        "productTaskSchema = z",
        "productErrorSchema = z.strictObject",
        "provider: z.string().regex",
        "error_type: z.string().regex",
        "attempt: z.number().int().min(1).max(100)",
    ):
        assert required_text in schema

    for required_text in (
        "analysisSubmissionSchema.parse(input)",
        '"/api/product/api/v2/analysis"',
        "`/api/product/api/v2/tasks/${encodeURIComponent(taskId)}${runSelection}`",
        "`/api/product/api/v2/runs?limit=${normalizedLimit}`",
        "productTaskSchema.safeParse(body)",
        "productRunListSchema.safeParse(body)",
    ):
        assert required_text in client

    assert 'method === "GET" && path === "api/v2/runs"' in proxy
    assert 'method === "POST" && path === "api/v2/analysis"' in proxy
    assert 'return method === "GET" && isTaskReadRoute(pathSegments);' in proxy
    assert "create analysis、run list、get task" in status
    assert "`GET /api/v2/tasks/{task_id}` 支持显式 `run_id`" in status
    assert "V2 = PARTIAL" in status
    assert "Production Ready = NO" in status
    assert "V1 parity/removal 均不存在" in status


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
        assert "37-真实多Agent对抗审查与交付方向裁决.md" in source, name
        assert "legacy_prompt" in source, name
        assert "34-生产级AgentSwarm优化目标与执行计划.md`：当前新的执行入口" not in source, name
        assert "当前执行阶段以 `34-生产级AgentSwarm优化目标与执行计划.md`" not in source, name

    assert "当前执行阶段以 `31-受控AgentSwarm主链收敛与质量切换计划.md`" not in sources["formal_index"]


def test_formal_index_points_day_to_day_execution_to_current_delivery_checklist():
    source = DOC_INDEX.read_text(encoding="utf-8")

    assert "当前日常执行入口以 `docs/implementation/2026-07-09-current-delivery-checklist.md` 为准" in source
    assert "`37-真实多Agent对抗审查与交付方向裁决.md` 是方向裁决" in source
    assert "当前新的执行入口" not in source


def test_old_formal_execution_plans_are_marked_historical_or_post_p0():
    expected = {
        "31-受控AgentSwarm主链收敛与质量切换计划.md": "历史 AgentSwarm 迁移进度",
        "32-架构功能收敛总计划与追踪清单.md": "post-P0 architecture backlog",
        "35-剩余主缺口对抗审查与执行清单.md": "历史 AgentSwarm 缺口清单",
        "36-成熟观测与评测平台接入方案.md": "post-v1 proposal",
    }

    for filename, marker in expected.items():
        source = (Path("docs/formal") / filename).read_text(encoding="utf-8")
        assert marker in source
        assert "docs/implementation/2026-07-09-current-delivery-checklist.md" in source


def test_main_flow_checkpoint_records_canonical_main_chain_and_outcome_operations():
    source = MAIN_FLOW_CHECKPOINT.read_text(encoding="utf-8")

    required_paths = (
        "src/crypto_manual_alert/api/routes_runs.py",
        "src/crypto_manual_alert/workflow/executor.py",
        "src/crypto_manual_alert/workflow/legacy_adapter.py",
        "src/crypto_manual_alert/workflow/legacy_decision_workflow.py",
        "src/crypto_manual_alert/decision/final_engine.py",
        "src/crypto_manual_alert/decision/plan_parser.py",
        "src/crypto_manual_alert/decision/production_control_gate.py",
        "src/crypto_manual_alert/storage/business_summary.py",
        "src/crypto_manual_alert/eval/outcome_collector.py",
        "tools/deployment/smoke_real_outcome_evidence.py",
        "tools/deployment/smoke_hosted_real_outcome_collection.py",
    )
    for path in required_paths:
        assert path in source

    for required_text in (
        "production main path",
        "sidecar/audit/eval",
        "collect-outcomes",
        "exchange-native",
        "matured horizon",
        "mocked_outcome",
        "real_outcome_evidence",
        "hosted_real_outcome_collection",
        "not production success",
    ):
        assert required_text in source


def test_current_delivery_checklist_records_main_path_proof_levels_and_open_p0():
    source = CURRENT_DELIVERY_CHECKLIST.read_text(encoding="utf-8")

    for required_text in (
        "user query / audit note",
        "readable manual alert",
        "LegacyPlanRunnerAdapter",
        "LegacyDecisionWorkflow",
        "decision.final_input_mode=legacy_prompt",
        "business_summary",
        "result_review",
        "sidecar/audit/eval/diagnostic",
        "fixture",
        "mock",
        "staging",
        "local-browser",
        "hosted-runtime",
        "prod-config",
        "prod-actionable",
        "real-outcome",
        "not production success",
        "Manual-run success can jump to `/runs?latest={trace_id}`",
        "data-latest-run=\"true\"",
        "Real external `prod-actionable` smoke succeeds",
        "exchange_native + matured + can_score",
        "smoke_hosted_real_outcome_collection.py",
        "same-host DATA_DIR",
        "api_config_preflight",
        "collection_errors_allowed=false",
        "new_refs_verified=true",
        "Default fixture Docker/hosted-runtime smoke completes",
        "query_text",
        "audit_note",
        "Latest green result after public HTTPS/DNS, unexpired event-assertion, production main-path readiness, non-production model denylist, and strict Bark evidence hardening: `15 passed`",
        "Green result after config preflight and old-outcome linkage hardening: `16 passed`",
        "Python pytest `1113 passed, 2 warnings`",
        "Playwright `48 passed, 10 skipped`",
    ):
        assert required_text in source

    assert "Green after public HTTPS gate hardening: `6 passed`" not in source


def test_current_execution_checklists_lead_with_latest_authoritative_verification_snapshot():
    """Prevent stale historical rerun counts from being mistaken for current status."""

    for checklist_path in (CURRENT_DELIVERY_CHECKLIST, MAIN_FLOW_PRODUCTION_RECOVERY_CHECKLIST):
        source = checklist_path.read_text(encoding="utf-8")
        snapshot_heading = "## Latest Authoritative Verification Snapshot"
        history_heading = "## Fresh Verification Record"

        assert snapshot_heading in source
        assert history_heading in source
        assert source.index(snapshot_heading) < source.index(history_heading)

        for required_text in (
            "Historical records below are retained as chronology",
            "Python pytest `1113 passed, 2 warnings`",
            "Playwright `48 passed, 10 skipped`",
            "`prod-actionable` still exits `2` with `missing_readiness`",
            "BARK_DEVICE_KEY",
            "OPENAI_BASE_URL",
            "OPENAI_MODEL",
            "OPENAI_API_KEY",
            "MACRO_EVENT_PROVIDER=no_active_event",
            "hosted prod-actionable",
            "market_data.okx_base_url",
            "readiness.market_data.status=unsafe",
            "not production success",
        ):
            assert required_text in source


def test_v2_live_and_historical_ownership_is_documented_and_preserved_by_frontend_contracts():
    schema = PRODUCT_API_SCHEMA.read_text(encoding="utf-8")
    client = PRODUCT_API_CLIENT.read_text(encoding="utf-8")
    stream = OFFICIAL_RUN_STREAM.read_text(encoding="utf-8")
    status = V2_IMPLEMENTATION_STATUS.read_text(encoding="utf-8")

    for required_text in (
        'protocol: z.literal("langgraph-v2")',
        "assistant_id: z.string().trim().min(1).max(255)",
        "thread_id: z.string().trim().min(1).max(255)",
        "run_id: z.string().trim().min(1).max(255)",
        "agent_stream: agentStreamBindingSchema.nullable().default(null)",
    ):
        assert required_text in schema

    assert "`?run_id=${encodeURIComponent(runId)}`" in client
    assert 'import { useChannel, useStream } from "@langchain/react";' in stream
    assert "useChannel(stream, productCustomChannels" in stream
    assert "const { assistant_id: assistantId, thread_id: threadId } = binding;" in stream
    assert "apiUrl: officialAgentApiUrl(window.location.origin)" in stream
    assert "runId:" not in stream

    assert "same-origin agent/product BFF" in status
    assert "`@langchain/react` thread attachment" in status
    assert "Product task GET 可以用 `run_id` 选择历史 Product Run" in status
    assert "官方 HITL、notification 和 feedback 的 Product 侧交互" in status
    assert "完整 Protocol v2" in status
    assert "strict real Playwright 已在开发 Runtime 下通过" in status


def test_main_flow_checkpoint_records_latest_proof_gate_hardening_summary():
    source = MAIN_FLOW_CHECKPOINT.read_text(encoding="utf-8")

    for required_text in (
        "2026-07-09 追加：proof gate hardening and latest local matrix",
        "hosted prod-actionable API gate",
        "public HTTPS API base",
        "unexpired event assertion",
        "strict Bark notification row",
        "DNS 解析到 local/private/reserved",
        "production main path readiness",
        "non-production model denylist",
        "`15 passed`",
        "old outcome",
        "`16 passed`",
        "hosted-positive visual proof",
        "PLAYWRIGHT_FRONTEND_BASE_URL to be a public HTTPS URL",
        "local-prod-actionable-rehearsal",
        "production_success=false",
        "Python pytest `1113 passed, 2 warnings`",
        "Playwright `48 passed, 10 skipped`",
        "strict prod gate still exits `2`",
        "hosted-runtime only",
        "not production success",
    ):
        assert required_text in source


def test_hosted_runtime_docs_keep_fixture_and_production_intent_boundaries_consistent():
    checklist = CURRENT_DELIVERY_CHECKLIST.read_text(encoding="utf-8")
    checkpoint = MAIN_FLOW_CHECKPOINT.read_text(encoding="utf-8")
    recovery_plan = Path("docs/implementation/2026-07-08-production-main-flow-recovery-plan.md").read_text(
        encoding="utf-8"
    )

    assert "Default fixture Docker/hosted-runtime smoke completes" in checklist
    assert "tools/deployment/smoke_docker_hosted_runtime.py" in checklist
    assert "Proof level: `hosted-runtime` only" in checklist
    assert "not `prod-config`, not `prod-actionable`, and not `real-outcome`" in checklist
    assert "Production-intent hosted runtime with a filled `.env.production.example` profile" in checklist

    assert "默认 Docker hosted-runtime 已在后续重试中闭环" in checkpoint
    assert "Production-intent hosted runtime" in checkpoint
    assert "本地 strict `--prod-actionable --fail-on-skip` 也不能替代 hosted run-level gate" in checkpoint

    assert "default fixture `hosted-runtime` proof" in recovery_plan
    assert "Production-intent hosted runtime passes with a filled `.env.production.example` profile" in recovery_plan


def test_main_flow_module_ownership_map_keeps_backend_boundaries_explicit():
    source = MAIN_FLOW_MODULE_OWNERSHIP.read_text(encoding="utf-8")

    for required_text in (
        "POST /api/runs/manual -> build_manual_decision_request() -> RunExecutor.submit()",
        "LegacyPlanRunnerAdapter -> LegacyDecisionWorkflow",
        "decision.final legacy_prompt -> parser.strict_json -> production_control.check -> risk.check",
        "persist_run_result() -> JournalQueryRepository.get_run_detail()",
        "business_summary/result_review/notification projection",
        "src/crypto_manual_alert/api/routes_runs.py",
        "src/crypto_manual_alert/context/request.py",
        "src/crypto_manual_alert/workflow/executor.py",
        "src/crypto_manual_alert/workflow/legacy_adapter.py",
        "src/crypto_manual_alert/workflow/legacy_decision_workflow.py",
        "src/crypto_manual_alert/workflow/run_persistence_step.py",
        "src/crypto_manual_alert/decision/final_engine.py",
        "src/crypto_manual_alert/decision/plan_parser.py",
        "src/crypto_manual_alert/decision/production_control_gate.py",
        "src/crypto_manual_alert/decision/risk.py",
        "src/crypto_manual_alert/market/providers.py",
        "src/crypto_manual_alert/market/event_status.py",
        "src/crypto_manual_alert/notification/sinks.py",
        "src/crypto_manual_alert/storage/journal.py",
        "src/crypto_manual_alert/storage/query_repository.py",
        "src/crypto_manual_alert/storage/business_summary.py",
        "src/crypto_manual_alert/storage/result_review.py",
        "agent_swarm/**",
        "lead/**",
        "orchestration/**",
        "artifacts/**",
        "workflow/pre_final_orchestration.py",
        "workflow/candidate_sidecar_step.py",
        "workflow/controlled_adapter.py",
        "decision/decision_input*",
        "decision/pre_final*",
        "decision/candidate*",
        "eval/**",
        "api/routes_eval.py",
        "Production final input remains legacy_prompt",
        "query_text remains audit_note",
        "production_candidate_swarm is not the default main path",
        "runtime_role",
        "production_main",
        "production_blocking_audit",
        "product_projection",
        "diagnostic_projection",
        "eval_sidecar",
        "replay_only",
        "future_candidate",
        "audit-only input to production-blocking gate",
        "pre_final_orchestration, shadow workers, DecisionInput candidate, and candidate audit do not enter FinalDecisionAgent input",
        "gate failures may be promoted by production_control_gate",
        "business_summary/result_review/agent_audit_view are projections",
        "eval routes must not write production plan_runs or trigger Bark",
        "fixture/mock/staging/hosted-runtime are not production success",
        "No new AgentSwarm/eval expansion before P0 external proof",
    ):
        assert required_text in source
