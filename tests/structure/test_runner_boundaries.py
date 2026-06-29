from pathlib import Path


PLAN_RUNNER = Path("src/crypto_manual_alert/workflow/legacy_plan_runner.py")
LEGACY_WORKFLOW = Path("src/crypto_manual_alert/workflow/legacy_decision_workflow.py")
DECISION_INPUT = Path("src/crypto_manual_alert/decision/decision_input.py")


def _plan_runner_source() -> str:
    return PLAN_RUNNER.read_text(encoding="utf-8")


def test_legacy_plan_runner_does_not_own_payload_or_candidate_audit_helpers():
    runner_source = _plan_runner_source()

    forbidden_definitions = {
        "def _candidate_audit_payload(",
        "def _evidence_to_claims(",
        "def _redaction_policy(",
    }

    for definition in forbidden_definitions:
        assert definition not in runner_source


def test_legacy_plan_runner_does_not_import_control_gate_or_candidate_audit_internals():
    runner_source = _plan_runner_source()

    forbidden_imports = {
        "from crypto_manual_alert.decision.candidate_audit import",
        "from crypto_manual_alert.decision.production_control_gate import",
        "from crypto_manual_alert.decision.risk import check_plan",
    }

    for import_line in forbidden_imports:
        assert import_line not in runner_source


def test_legacy_plan_runner_does_not_own_research_orchestration_internals():
    runner_source = _plan_runner_source()

    forbidden_names = {
        "execute_research",
        "needs_research_fallback",
        "synthesize_search_evidence",
        "candle_max_age_seconds",
    }

    for name in forbidden_names:
        assert name not in runner_source


def test_legacy_plan_runner_does_not_own_pre_final_orchestration_internals():
    runner_source = _plan_runner_source()

    forbidden_imports = {
        "from crypto_manual_alert.artifacts.orchestration_inputs import build_audit_artifacts",
        "from crypto_manual_alert.decision.pre_final_input import build_pre_final_input_payload",
        "from crypto_manual_alert.agent_swarm.shadow_orchestration import run_shadow_swarm_audit",
    }

    for import_line in forbidden_imports:
        assert import_line not in runner_source


def test_legacy_plan_runner_does_not_own_legacy_final_input_internals():
    runner_source = _plan_runner_source()

    forbidden_imports = {
        "from crypto_manual_alert.decision.final_prompt import build_legacy_final_prompt_packet",
        "from crypto_manual_alert.decision.frozen_input import FrozenInput, freeze_decision_prompt_packet",
    }

    for import_line in forbidden_imports:
        assert import_line not in runner_source


def test_legacy_plan_runner_does_not_own_market_or_skill_loading_internals():
    runner_source = _plan_runner_source()

    forbidden_calls = {
        ".fetch_snapshot(",
        ".load_context(",
        "def _snapshot_summary(",
    }

    for call in forbidden_calls:
        assert call not in runner_source


def test_legacy_plan_runner_does_not_own_parser_or_persistence_internals():
    runner_source = _plan_runner_source()

    forbidden_imports_or_calls = {
        "from crypto_manual_alert.decision.plan_parser import parse_decision_plan",
        "build_plan_payload(",
        ".append_plan_run(",
        ".finish_trace(",
        ".append_notification(",
    }

    for item in forbidden_imports_or_calls:
        assert item not in runner_source


def test_legacy_plan_runner_does_not_own_legacy_step_sequence_imports():
    runner_source = _plan_runner_source()

    forbidden_imports = {
        "from crypto_manual_alert.context.artifacts import record_orchestration_artifacts",
        "from crypto_manual_alert.workflow.decision_control_step import",
        "from crypto_manual_alert.decision.final_decision_step import",
        "from crypto_manual_alert.decision.legacy_final_input_step import",
        "from crypto_manual_alert.workflow.market_context_step import",
        "from crypto_manual_alert.decision.plan_parse_step import",
        "from crypto_manual_alert.workflow.pre_final_orchestration import",
        "from crypto_manual_alert.workflow.research_orchestration import",
    }

    for import_line in forbidden_imports:
        assert import_line not in runner_source


def test_legacy_workflow_uses_typed_state_instead_of_magic_dict_keys():
    runner_source = PLAN_RUNNER.read_text(encoding="utf-8")
    workflow_source = LEGACY_WORKFLOW.read_text(encoding="utf-8")

    assert "LegacyDecisionWorkflowState" in runner_source
    assert "workflow_state: dict[str, Any] = {}" not in runner_source
    assert "workflow_state[" not in workflow_source


def test_legacy_workflow_does_not_import_agent_swarm_business_modules_directly():
    workflow_source = LEGACY_WORKFLOW.read_text(encoding="utf-8")

    forbidden_imports = {
        "from crypto_manual_alert.agent_swarm",
        "import crypto_manual_alert.agent_swarm",
        "from crypto_manual_alert.lead",
        "import crypto_manual_alert.lead",
        "from crypto_manual_alert.artifacts.evidence",
        "from crypto_manual_alert.artifacts.contributions",
        "from crypto_manual_alert.decision.decision_input import",
        "from crypto_manual_alert.agent_swarm.local_workers",
    }

    for import_line in forbidden_imports:
        assert import_line not in workflow_source


def test_decision_input_builder_does_not_own_lead_synthesis_construction():
    decision_input_source = DECISION_INPUT.read_text(encoding="utf-8")

    forbidden_items = {
        "from crypto_manual_alert.lead.synthesis import",
        "build_lead_synthesis_candidate",
        "DEFAULT_REQUIRED_AGENTS",
        "def _lead_synthesis(",
        "def _required_agents_from_lead_plan(",
    }

    for item in forbidden_items:
        assert item not in decision_input_source


def test_decision_input_builder_delegates_policy_rules():
    decision_input_source = DECISION_INPUT.read_text(encoding="utf-8")
    policy_module = Path("src/crypto_manual_alert/decision/decision_input_policy.py")

    assert policy_module.exists()
    assert "from crypto_manual_alert.decision.decision_input_policy import" in decision_input_source
    for helper_name in (
        "_missing_facts",
        "_conflicts",
        "_blocked_actions",
        "_confidence_policy",
        "_validation_summary",
        "required_dropped_contributions",
        "worker_hard_block_contributions",
        "_is_execution_blocked",
        "_as_float",
        "_dedupe",
    ):
        assert f"def {helper_name}(" not in decision_input_source
