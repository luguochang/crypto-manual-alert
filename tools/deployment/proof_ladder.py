from __future__ import annotations

import json
from typing import Any


def build_proof_ladder() -> dict[str, Any]:
    return {
        "schema_version": "2026-07-09.main-flow-proof-ladder",
        "main_path": {
            "api_entry": "POST /api/runs/manual",
            "workflow": "RunExecutor -> LegacyPlanRunnerAdapter -> LegacyDecisionWorkflow",
            "decision_final_input_mode": "legacy_prompt",
            "candidate_sidecar_mode": "disabled",
            "workflow_execution_mode": "legacy_baseline",
            "manual_execution_required": True,
            "auto_order_enabled": False,
        },
        "definition_of_done": [
            "hosted_prod_config",
            "hosted_prod_actionable",
            "hosted_prod_actionable_visual",
            "hosted_real_outcome",
        ],
        "gates": [
            {
                "id": "local_no_secret_matrix",
                "proof_level": "local-browser+fixture/mock/staging",
                "command": "python3 tools/local_stack/run_local_checks.py",
                "production_success": False,
                "blocks_recovery_until_passed": True,
                "proves": "Local API, production Next build, Chromium rendering, fixture/mock/staging wiring, and collector wiring do not regress.",
                "does_not_prove": "not production success; does not prove real external LLM, real OKX public data, Bark sent, hosted prod config, or real outcome.",
            },
            {
                "id": "strict_local_prod_actionable_guard",
                "proof_level": "readiness-guard",
                "command": "python3 tools/local_stack/smoke_local_stack.py --prod-actionable --fail-on-skip",
                "production_success": False,
                "blocks_recovery_until_passed": False,
                "expected_block_exit_code": 2,
                "proves": "missing_readiness is surfaced loudly when real production dependencies are absent.",
                "does_not_prove": "does not prove hosted prod-actionable; exit 2 is an honest block, not a pass.",
            },
            {
                "id": "docker_hosted_runtime",
                "proof_level": "hosted-runtime",
                "command": "python3 tools/deployment/smoke_docker_hosted_runtime.py",
                "production_success": False,
                "blocks_recovery_until_passed": True,
                "proves": "Docker compose can build/start hosted API and frontend, run a manual path smoke, and reject fixture config under --require-prod-config.",
                "does_not_prove": "not prod-actionable; not prod-config by default; not real-outcome.",
            },
            {
                "id": "hosted_prod_config",
                "proof_level": "prod-config",
                "command": (
                    "python3 tools/deployment/smoke_hosted_workbench.py "
                    "--api-base <hosted-api> --frontend-base <hosted-frontend> "
                    "--symbol ETH-USDT-SWAP --query \"生产工作台配置 smoke\" --horizon 6h --require-prod-config"
                ),
                "production_success": False,
                "blocks_recovery_until_passed": True,
                "proves": "Hosted API/frontend are running with production-intent config and current legacy_prompt/manual-only boundaries.",
                "does_not_prove": "does not prove allowed=true, real LLM response, Bark sent, or matured real outcome.",
            },
            {
                "id": "hosted_prod_actionable",
                "proof_level": "prod-actionable",
                "command": (
                    "python3 tools/deployment/smoke_hosted_prod_actionable.py "
                    "--api-base <public-https-api> --symbol ETH-USDT-SWAP "
                    "--query \"Hosted prod-actionable smoke：验证真实人工提醒证据链\" --horizon 6h"
                ),
                "production_success": True,
                "blocks_recovery_until_passed": True,
                "requires_public_https_api_base": True,
                "hosting_boundary": "api-base must be a public HTTPS API base; localhost, private IPs, and non-HTTPS URLs are rejected by default.",
                "required_external_readiness": [
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
                ],
                "proves": "One hosted manual alert used real external LLM, real OKX public data, Bark sent evidence, unexpired no-active-event assertion, allowed=true, legacy_prompt, sidecar disabled, and manual-only safety.",
                "does_not_prove": "does not prove future financial outcome quality; real-outcome remains a separate gate.",
            },
            {
                "id": "hosted_prod_actionable_visual",
                "proof_level": "hosted-prod-actionable-visual",
                "command": (
                    "PLAYWRIGHT_REUSE_EXISTING_STACK=true "
                    "PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE=true "
                    "PLAYWRIGHT_FRONTEND_BASE_URL=<public-https-frontend> "
                    "PLAYWRIGHT_API_BASE_URL=<public-https-api> "
                    "npm --prefix frontend run e2e -- --project=chromium-desktop hosted-prod-actionable-visual.spec.ts"
                ),
                "commands": [
                    (
                        "PLAYWRIGHT_REUSE_EXISTING_STACK=true "
                        "PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE=true "
                        "PLAYWRIGHT_FRONTEND_BASE_URL=<public-https-frontend> "
                        "PLAYWRIGHT_API_BASE_URL=<public-https-api> "
                        "npm --prefix frontend run e2e -- --project=chromium-desktop hosted-prod-actionable-visual.spec.ts"
                    ),
                    (
                        "PLAYWRIGHT_REUSE_EXISTING_STACK=true "
                        "PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE=true "
                        "PLAYWRIGHT_FRONTEND_BASE_URL=<public-https-frontend> "
                        "PLAYWRIGHT_API_BASE_URL=<public-https-api> "
                        "npm --prefix frontend run e2e -- --project=chromium-mobile hosted-prod-actionable-visual.spec.ts"
                    ),
                ],
                "production_success": False,
                "blocks_recovery_until_passed": True,
                "requires_public_https_base_urls": True,
                "hosting_boundary": "frontend and API base URLs must be public HTTPS URLs; localhost, private IPs, and non-HTTPS URLs are rejected.",
                "proves": "The hosted prod-actionable visual path passes on desktop and mobile: each positive run renders model review, model summary, evidence, Bark status, proof strip, and layout without raw JSON, secrets, overlap, or responsive layout defects.",
                "does_not_prove": "does not replace run-level prod-actionable smoke or real-outcome collection.",
            },
            {
                "id": "hosted_real_outcome",
                "proof_level": "real-outcome",
                "command": (
                    "python3 tools/deployment/smoke_hosted_real_outcome_collection.py "
                    "--api-base <hosted-api> --symbol ETH-USDT-SWAP --limit 50 --min-count 1 "
                    "--same-host-data-dir-confirmed"
                ),
                "production_success": False,
                "blocks_recovery_until_passed": True,
                "proves": "A hosted collector and API sharing the same DATA_DIR exposed a new exchange-native matured scorable outcome.",
                "does_not_prove": "not prod-actionable; does not prove a fresh LLM run or Bark sent for the same alert.",
            },
        ],
    }


def main(argv: list[str] | None = None) -> int:
    _ = argv
    print(json.dumps(build_proof_ladder(), ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
