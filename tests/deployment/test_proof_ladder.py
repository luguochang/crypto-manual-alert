from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "deployment" / "proof_ladder.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("proof_ladder", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_proof_ladder_records_main_flow_gates_and_non_production_boundaries(capsys):
    module = _load_module()

    ladder = module.build_proof_ladder()

    assert ladder["schema_version"] == "2026-07-09.main-flow-proof-ladder"
    assert ladder["main_path"]["decision_final_input_mode"] == "legacy_prompt"
    assert ladder["main_path"]["manual_execution_required"] is True
    assert ladder["main_path"]["auto_order_enabled"] is False
    assert ladder["definition_of_done"] == [
        "hosted_prod_config",
        "hosted_prod_actionable",
        "hosted_prod_actionable_visual",
        "hosted_real_outcome",
    ]

    gates = {gate["id"]: gate for gate in ladder["gates"]}
    assert list(gates) == [
        "local_no_secret_matrix",
        "strict_local_prod_actionable_guard",
        "docker_hosted_runtime",
        "hosted_prod_config",
        "hosted_prod_actionable",
        "hosted_prod_actionable_visual",
        "hosted_real_outcome",
    ]

    assert gates["local_no_secret_matrix"]["proof_level"] == "local-browser+fixture/mock/staging"
    assert gates["local_no_secret_matrix"]["production_success"] is False
    assert "tools/local_stack/run_local_checks.py" in gates["local_no_secret_matrix"]["command"]
    assert "not production success" in gates["local_no_secret_matrix"]["does_not_prove"]

    assert gates["strict_local_prod_actionable_guard"]["expected_block_exit_code"] == 2
    assert gates["strict_local_prod_actionable_guard"]["production_success"] is False
    assert "missing_readiness" in gates["strict_local_prod_actionable_guard"]["proves"]

    assert gates["docker_hosted_runtime"]["proof_level"] == "hosted-runtime"
    assert gates["docker_hosted_runtime"]["production_success"] is False
    assert "tools/deployment/smoke_docker_hosted_runtime.py" in gates["docker_hosted_runtime"]["command"]
    assert "not prod-actionable" in gates["docker_hosted_runtime"]["does_not_prove"]

    assert gates["hosted_prod_config"]["proof_level"] == "prod-config"
    assert gates["hosted_prod_config"]["blocks_recovery_until_passed"] is True
    assert "--require-prod-config" in gates["hosted_prod_config"]["command"]

    assert gates["hosted_prod_actionable"]["proof_level"] == "prod-actionable"
    assert gates["hosted_prod_actionable"]["blocks_recovery_until_passed"] is True
    assert "tools/deployment/smoke_hosted_prod_actionable.py" in gates["hosted_prod_actionable"]["command"]
    assert "<public-https-api>" in gates["hosted_prod_actionable"]["command"]
    assert gates["hosted_prod_actionable"]["requires_public_https_api_base"] is True
    assert "public HTTPS API base" in gates["hosted_prod_actionable"]["hosting_boundary"]
    assert gates["hosted_prod_actionable"]["required_external_readiness"] == [
        "OPENAI_BASE_URL",
        "OPENAI_MODEL",
        "OPENAI_API_KEY",
        "BARK_DEVICE_KEY",
        "MACRO_EVENT_PROVIDER=no_active_event",
        "MACRO_EVENT_OPERATOR_REF",
        "MACRO_EVENT_CONFIRMED_AT",
        "MACRO_EVENT_SOURCE_REF",
        "MACRO_EVENT_ASSERTION_HORIZON",
        "MACRO_EVENT_VALID_UNTIL",
    ]

    assert gates["hosted_prod_actionable_visual"]["proof_level"] == "hosted-prod-actionable-visual"
    assert gates["hosted_prod_actionable_visual"]["blocks_recovery_until_passed"] is True
    assert "PLAYWRIGHT_REUSE_EXISTING_STACK=true" in gates["hosted_prod_actionable_visual"]["command"]
    assert "PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE=true" in gates["hosted_prod_actionable_visual"]["command"]
    assert "<public-https-frontend>" in gates["hosted_prod_actionable_visual"]["command"]
    assert "<public-https-api>" in gates["hosted_prod_actionable_visual"]["command"]
    assert gates["hosted_prod_actionable_visual"]["requires_public_https_base_urls"] is True
    assert "public HTTPS" in gates["hosted_prod_actionable_visual"]["hosting_boundary"]
    assert "hosted-prod-actionable-visual.spec.ts" in gates["hosted_prod_actionable_visual"]["command"]
    assert gates["hosted_prod_actionable_visual"]["commands"] == [
        (
            "PLAYWRIGHT_REUSE_EXISTING_STACK=true PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE=true "
            "PLAYWRIGHT_FRONTEND_BASE_URL=<public-https-frontend> PLAYWRIGHT_API_BASE_URL=<public-https-api> "
            "npm --prefix frontend run e2e -- --project=chromium-desktop hosted-prod-actionable-visual.spec.ts"
        ),
        (
            "PLAYWRIGHT_REUSE_EXISTING_STACK=true PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE=true "
            "PLAYWRIGHT_FRONTEND_BASE_URL=<public-https-frontend> PLAYWRIGHT_API_BASE_URL=<public-https-api> "
            "npm --prefix frontend run e2e -- --project=chromium-mobile hosted-prod-actionable-visual.spec.ts"
        ),
    ]
    assert "desktop and mobile" in gates["hosted_prod_actionable_visual"]["proves"]

    assert gates["hosted_real_outcome"]["proof_level"] == "real-outcome"
    assert gates["hosted_real_outcome"]["blocks_recovery_until_passed"] is True
    assert "--same-host-data-dir-confirmed" in gates["hosted_real_outcome"]["command"]
    assert "not prod-actionable" in gates["hosted_real_outcome"]["does_not_prove"]

    assert module.main([]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed == ladder
