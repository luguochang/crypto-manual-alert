from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def _read_env_template(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def test_container_default_scheduler_uses_staging_overlay_for_actionable_path():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert 'CMD ["crypto-alert", "--config", "config/default.yaml", "--config", "config/prod.yaml", "--config", "config/staging.yaml", "scheduler"]' in dockerfile


def test_compose_healthcheck_uses_same_staging_overlay():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert '["CMD", "crypto-alert", "--config", "config/default.yaml", "--config", "config/prod.yaml", "--config", "config/staging.yaml", "show-config"]' in compose


def test_python_container_declares_api_server_dependency():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "uvicorn" in pyproject


def test_compose_exposes_hosted_api_and_frontend_workbench():
    compose_text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    compose = yaml.safe_load(compose_text)
    services = compose["services"]

    api = services["api"]
    assert api["command"] == [
        "python",
        "-m",
        "uvicorn",
        "crypto_manual_alert.api.app:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8010",
    ]
    assert api["ports"] == ["${API_PORT:-8010}:8010"]
    assert api["environment"]["CONFIG_PATHS"] == "${CONFIG_PATHS:-config/default.yaml}"
    assert "/api/system/health" in " ".join(api["healthcheck"]["test"])

    frontend = services["frontend"]
    assert frontend["build"]["dockerfile"] == "Dockerfile.frontend"
    assert frontend["build"]["args"]["NEXT_PUBLIC_API_BASE_URL"] == "${NEXT_PUBLIC_API_BASE_URL:-http://127.0.0.1:8010}"
    assert frontend["environment"]["API_INTERNAL_BASE_URL"] == "${API_INTERNAL_BASE_URL:-http://api:8010}"
    assert frontend["ports"] == ["${FRONTEND_PORT:-3001}:3001"]
    assert frontend["depends_on"]["api"]["condition"] == "service_healthy"
    healthcheck_command = " ".join(frontend["healthcheck"]["test"])
    assert "API_INTERNAL_BASE_URL" in healthcheck_command
    assert "base + '/api/system/health'" in healthcheck_command
    assert "${base}" not in healthcheck_command
    assert "/api/system/health" in healthcheck_command


def test_frontend_api_client_separates_browser_and_server_api_base():
    client = (ROOT / "frontend" / "src" / "lib" / "api" / "client.ts").read_text(encoding="utf-8")

    assert "API_INTERNAL_BASE_URL" in client
    assert "typeof window" in client
    assert "NEXT_PUBLIC_API_BASE_URL" in client
    assert "frontend server-side API base" in client


def test_compose_env_file_is_optional_for_fresh_checkout():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    services = compose["services"]

    for service_name in ("manual-alert", "api"):
        assert services[service_name]["env_file"] == [{"path": ".env", "required": False}]


def test_compose_default_startup_is_hosted_workbench_first():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    services = compose["services"]

    assert services["manual-alert"]["profiles"] == ["scheduler"]
    assert "profiles" not in services["api"]
    assert "profiles" not in services["frontend"]


def test_frontend_dockerfile_builds_next_workbench():
    dockerfile = (ROOT / "Dockerfile.frontend").read_text(encoding="utf-8")

    assert "NEXT_PUBLIC_API_BASE_URL" in dockerfile
    assert "npm ci" in dockerfile
    assert "npm run build" in dockerfile
    assert "next\" , \"--\"" not in dockerfile
    assert "start" in dockerfile
    assert "3001" in dockerfile


def test_container_base_images_can_be_overridden_for_restricted_registries():
    """Deployment builds must not be hard-wired to Docker Hub base images."""

    api_dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    frontend_dockerfile = (ROOT / "Dockerfile.frontend").read_text(encoding="utf-8")
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "ARG PYTHON_BASE_IMAGE=python:3.12-slim" in api_dockerfile
    assert "FROM ${PYTHON_BASE_IMAGE}" in api_dockerfile
    assert "ARG NODE_BASE_IMAGE=node:22-alpine" in frontend_dockerfile
    assert frontend_dockerfile.count("FROM ${NODE_BASE_IMAGE}") == 3

    for service_name in ("manual-alert", "api"):
        assert compose["services"][service_name]["build"]["args"]["PYTHON_BASE_IMAGE"] == "${PYTHON_BASE_IMAGE:-python:3.12-slim}"
    assert compose["services"]["frontend"]["build"]["args"]["NODE_BASE_IMAGE"] == "${NODE_BASE_IMAGE:-node:22-alpine}"
    assert "PYTHON_BASE_IMAGE=python:3.12-slim" in env_example
    assert "NODE_BASE_IMAGE=node:22-alpine" in env_example


def test_deployment_manual_trigger_example_keeps_staging_overlay():
    docs = (ROOT / "docs" / "deployment.md").read_text(encoding="utf-8")

    assert "crypto-alert --config config/default.yaml --config config/prod.yaml --config config/staging.yaml run-once" in docs


def test_deployment_docs_describe_hosted_workbench_services():
    docs = (ROOT / "docs" / "deployment.md").read_text(encoding="utf-8")
    strict_config_section = docs.split("`--require-prod-config` 会", 1)[1].split("严格配置通过时", 1)[0]

    assert "api" in docs
    assert "frontend" in docs
    assert "http://127.0.0.1:8010/api/system/health" in docs
    assert "http://127.0.0.1:3001" in docs
    assert "tools/deployment/smoke_hosted_workbench.py" in docs
    assert "tools/deployment/smoke_docker_hosted_runtime.py" in docs
    assert "hosted_workbench" in docs
    assert "--require-prod-config" in docs
    assert "production_config_required" in docs
    assert "production_config_ready" in docs
    assert "decision.final_input_mode" in strict_config_section
    assert "legacy_prompt" in strict_config_section
    assert "market_data.okx_base_url" in strict_config_section
    assert "readiness.market_data.status!=unsafe" in strict_config_section
    assert "POST /api/runs/manual" in docs
    assert "不是 `prod-actionable`" in docs
    assert "--profile scheduler up -d manual-alert" in docs
    assert "SCHEDULER_DISABLED" in docs
    assert "scheduler.enabled=false" in docs
    assert "SCHEDULER_ENABLED=true" in docs


def test_deployment_docs_describe_real_outcome_evidence_gate():
    docs = (ROOT / "docs" / "deployment.md").read_text(encoding="utf-8")

    assert "tools/deployment/smoke_real_outcome_evidence.py" in docs
    assert "tools/deployment/smoke_hosted_real_outcome_collection.py" in docs
    assert "real_outcome_evidence" in docs
    assert "hosted_real_outcome_collection" in docs
    assert "real_exchange_native_matured_outcome_proven" in docs
    assert "source_type=exchange_native" in docs
    assert "matured=true" in docs
    assert "can_score=true" in docs
    assert "--symbol" in docs
    assert "--collected-after" in docs
    assert "window.collected_at" in docs
    assert "--same-host-data-dir-confirmed" in docs
    assert "api_config_preflight" in docs
    assert "market_data.okx_base_url" in docs
    assert "collection_errors_allowed=false" in docs
    assert "new_refs_verified" in docs
    assert "collected_refs" in docs
    assert "(decision_ref, evaluation_target, symbol, window_name)" in docs
    assert "real_outcome_evidence_not_linked_to_collection" in docs
    assert "不是 prod-actionable" in docs


def test_deployment_docs_reference_hosted_real_outcome_proof_output():
    script = (ROOT / "tools" / "deployment" / "smoke_hosted_real_outcome_collection.py").read_text(encoding="utf-8")
    docs = (ROOT / "docs" / "deployment.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    checklist = (
        ROOT
        / "docs"
        / "implementation"
        / "2026-07-09-current-delivery-checklist.md"
    ).read_text(encoding="utf-8")

    for required in (
        "--proof-output",
        "2026-07-09.hosted-real-outcome-proof.v1",
        "collect_outcomes_digest",
        "real_outcome_evidence_digest",
        "outcome_summary",
        "new_or_updated_ref_details",
        "does_not_prove",
        "hosted_prod_actionable",
    ):
        assert required in script

    for source in (docs, readme, checklist):
        assert "--proof-output" in source
        assert "hosted-real-outcome-proof.json" in source
        assert "collect_outcomes_digest" in source
        assert "real_outcome_evidence_digest" in source
        assert "outcome_summary" in source
        assert "new_or_updated_ref_details" in source
        assert "does_not_prove=hosted_prod_actionable" in source
        assert "同一 symbol" in source
        assert "collected_at" in source
        assert "collected_refs" in source
        assert "decision_ref, evaluation_target, symbol, window_name" in source


def test_deployment_docs_describe_safe_default_compose_config():
    docs = (ROOT / "docs" / "deployment.md").read_text(encoding="utf-8")

    assert "CONFIG_PATHS=config/default.yaml:config/prod.yaml:config/staging.yaml" in docs
    assert "API_INTERNAL_BASE_URL=http://api:8010" in docs
    assert "NEXT_PUBLIC_API_BASE_URL" in docs
    assert "PYTHON_BASE_IMAGE" in docs
    assert "NODE_BASE_IMAGE" in docs
    assert "受限网络或私有镜像源" in docs
    assert "Config file does not exist" in docs
    assert "CONFIG_ERROR" in docs
    assert "docker compose -p crypto-alert-prod up -d --build api frontend" in docs
    assert "默认 `docker compose up` 只加载 `config/default.yaml`" in docs


def test_prod_env_template_declares_hosted_workbench_production_intent():
    env_path = ROOT / ".env.production.example"
    values = _read_env_template(env_path)

    assert values["CONFIG_PATHS"] == "config/default.yaml:config/prod.yaml:config/staging.yaml"
    assert values["APP_MODE"] == "MANUAL_ALERT"
    assert values["AUTO_ORDER_ENABLED"] == "false"
    assert values["DIAGNOSTIC_ROUTES_ENABLED"] == "false"
    assert values["SCHEDULER_ENABLED"] == "false"
    assert values["MARKET_DATA_PROVIDER"] == "okx_public"
    assert values["DECISION_ENGINE"] == "openai_compatible"
    assert values["NOTIFICATION_ENABLED"] == "true"
    assert values["MACRO_EVENT_PROVIDER"] == "no_active_event"
    assert values["NEXT_PUBLIC_API_BASE_URL"] == "http://127.0.0.1:8010"
    assert values["API_INTERNAL_BASE_URL"] == "http://api:8010"
    assert "OPENAI_BASE_URL" in values
    assert "OPENAI_MODEL" in values
    assert "OPENAI_API_KEY" in values
    assert "BARK_DEVICE_KEY" in values
    assert "OKX_TRADE_API_KEY" not in values
    assert "OKX_WITHDRAW_API_KEY" not in values


def test_env_examples_do_not_offer_okx_private_account_credentials():
    forbidden_names = {"OKX_API_KEY", "OKX_API_SECRET", "OKX_API_PASSPHRASE"}

    for env_path in (ROOT / ".env.example", ROOT / ".env.production.example"):
        values = _read_env_template(env_path)

        assert forbidden_names.isdisjoint(values)


def test_deployment_docs_reference_prod_env_template_and_strict_smokes():
    docs = (ROOT / "docs" / "deployment.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    for source in (docs, readme):
        assert ".env.production.example" in source
        assert "cp .env.production.example .env" in source
        assert "tools/deployment/smoke_docker_hosted_runtime.py" in source
        assert "tools/deployment/smoke_hosted_prod_actionable.py" in source
        assert "tools/deployment/smoke_hosted_real_outcome_collection.py" in source
        assert "tools/deployment/smoke_hosted_workbench.py" in source
        assert "--require-prod-config" in source
        assert "market_data.okx_base_url" in source
        assert "readiness.market_data.status=unsafe" in source
        assert "tools/local_stack/smoke_local_stack.py --prod-actionable --fail-on-skip" in source


def test_deployment_docs_reference_hosted_prod_actionable_api_proof_output():
    script = (ROOT / "tools" / "deployment" / "smoke_hosted_prod_actionable.py").read_text(encoding="utf-8")
    docs = (ROOT / "docs" / "deployment.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    checklist = (
        ROOT
        / "docs"
        / "implementation"
        / "2026-07-09-current-delivery-checklist.md"
    ).read_text(encoding="utf-8")

    for required in (
        "--proof-output",
        "2026-07-09.hosted-prod-actionable-proof.v1",
        "config_digest",
        "run_detail_digest",
        "run_detail_summary",
        "does_not_prove",
        "hosted_real_outcome",
    ):
        assert required in script

    for source in (docs, readme, checklist):
        assert "--proof-output" in source
        assert "hosted-prod-actionable-proof.json" in source
        assert "config_digest" in source
        assert "run_detail_summary" in source
        assert "does_not_prove=hosted_real_outcome" in source


def test_deployment_docs_reference_machine_readable_proof_ladder():
    docs = (ROOT / "docs" / "deployment.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    checklist = (
        ROOT
        / "docs"
        / "implementation"
        / "2026-07-09-current-delivery-checklist.md"
    ).read_text(encoding="utf-8")

    for source in (docs, readme, checklist):
        assert "tools/deployment/proof_ladder.py" in source
        assert "main-flow-proof-ladder" in source
        assert "local_no_secret_matrix" in source
        assert "hosted_prod_actionable" in source
        assert "hosted_prod_actionable_visual" in source
        assert "hosted_real_outcome" in source
        assert "does not run the gates" in source


def test_deployment_docs_reference_hosted_prod_actionable_visual_gate():
    docs = (ROOT / "docs" / "deployment.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    checklist = (
        ROOT
        / "docs"
        / "implementation"
        / "2026-07-09-current-delivery-checklist.md"
    ).read_text(encoding="utf-8")

    for source in (docs, readme, checklist):
        assert "hosted-prod-actionable-visual.spec.ts" in source
        assert "PLAYWRIGHT_REUSE_EXISTING_STACK=true" in source
        assert "PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE=true" in source
        assert "PLAYWRIGHT_FRONTEND_BASE_URL" in source
        assert "PLAYWRIGHT_API_BASE_URL" in source
        assert "--project=chromium-desktop hosted-prod-actionable-visual.spec.ts" in source
        assert "--project=chromium-mobile hosted-prod-actionable-visual.spec.ts" in source
        assert "desktop and mobile" in source or "桌面和移动" in source
        assert "模型审阅" in source
        assert "Bark" in source
        assert "raw JSON" in source
        assert "DNS" in source
        assert "local/private/reserved" in source


def test_deployment_docs_require_public_https_for_hosted_prod_actionable():
    docs = (ROOT / "docs" / "deployment.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    for source in (docs, readme):
        assert "--api-base <public-https-api>" in source
        assert "PLAYWRIGHT_API_BASE_URL=<public-https-api>" in source
        assert "PLAYWRIGHT_FRONTEND_BASE_URL=<public-https-frontend>" in source
        assert "public HTTPS API base" in source
        assert "smoke_hosted_prod_actionable.py \\\n  --api-base http://127.0.0.1:8010" not in source


def test_hosted_prod_actionable_visual_gate_requires_reusing_existing_hosted_stack():
    config = (ROOT / "frontend" / "playwright.config.ts").read_text(encoding="utf-8")
    spec = (
        ROOT
        / "frontend"
        / "tests"
        / "e2e"
        / "hosted-prod-actionable-visual.spec.ts"
    ).read_text(encoding="utf-8")

    assert "expectHostedProdActionable" in config
    assert 'PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE === "true"' in config
    assert "PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE=true requires PLAYWRIGHT_REUSE_EXISTING_STACK=true" in config
    assert "PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE=true requires PLAYWRIGHT_FRONTEND_BASE_URL" in config
    assert "PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE=true requires PLAYWRIGHT_API_BASE_URL" in config
    assert "assertPublicHttpsBaseUrl(" in config
    assert "explicitFrontendBaseUrl" in config
    assert "explicitApiBaseUrl" in config
    assert "public HTTPS URL" in config
    assert "webServer: expectHostedProdActionable ? undefined : {" in config
    assert "throw new Error" in config
    assert 'PLAYWRIGHT_REUSE_EXISTING_STACK === "true"' in spec
    assert "PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE=true requires PLAYWRIGHT_REUSE_EXISTING_STACK=true" in spec
    assert "PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE=true requires PLAYWRIGHT_FRONTEND_BASE_URL" in spec
    assert "PLAYWRIGHT_EXPECT_HOSTED_PROD_ACTIONABLE=true requires PLAYWRIGHT_API_BASE_URL" in spec
    assert "assertPublicHttpsBaseUrl(" in spec
    assert "EXPLICIT_FRONTEND_BASE_URL" in spec
    assert "EXPLICIT_API_BASE_URL" in spec
    assert "public HTTPS URL" in spec
    assert "production_main_path_ready" in spec
    assert "main_path_blockers" in spec


def test_hosted_prod_actionable_visual_gate_rejects_private_dns_hostnames():
    spec = (
        ROOT
        / "frontend"
        / "tests"
        / "e2e"
        / "hosted-prod-actionable-visual.spec.ts"
    ).read_text(encoding="utf-8")

    assert 'from "node:dns"' in spec
    assert 'from "node:net"' in spec
    assert "dns.lookup" in spec
    assert "assertResolvablePublicHttpsBaseUrl" in spec
    assert "isLocalOrPrivateAddress" in spec
    assert "resolves to a local/private/reserved address" in spec
    assert "await assertHostedProdActionableGateEnvironment()" in spec


def test_hosted_prod_actionable_visual_gate_matches_strict_api_proof_predicates():
    spec = (
        ROOT
        / "frontend"
        / "tests"
        / "e2e"
        / "hosted-prod-actionable-visual.spec.ts"
    ).read_text(encoding="utf-8")
    checklist = (
        ROOT
        / "docs"
        / "implementation"
        / "2026-07-09-current-delivery-checklist.md"
    ).read_text(encoding="utf-8")

    for required in (
        "market_data.okx_base_url must be unset or https://www.okx.com",
        "readiness.market_data.status must not be unsafe",
        "isNonProdModelName",
        "decision.final real non-mock model",
        "assertStrictBarkSentNotification",
        "status_code",
        "runStartedAt",
    ):
        assert required in spec

    for required in (
        "market_data.okx_base_url",
        "readiness.market_data.status=unsafe",
        "non-production model",
        "HTTP 2xx",
        "not earlier than the manual-run start",
    ):
        assert required in checklist


def test_hosted_prod_actionable_visual_gate_writes_audit_manifest():
    spec = (
        ROOT
        / "frontend"
        / "tests"
        / "e2e"
        / "hosted-prod-actionable-visual.spec.ts"
    ).read_text(encoding="utf-8")
    docs = (ROOT / "docs" / "deployment.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    for required in (
        "hosted-prod-actionable-proof-manifest.json",
        "writeHostedProdActionableProofManifest",
        "testInfo.outputPath",
        "testInfo.attach",
        "config_digest",
        "run_detail_summary",
        "screenshot_path",
        "trace_id",
        "frontend_base_url",
        "api_base_url",
        "does_not_prove",
        "hosted_real_outcome",
    ):
        assert required in spec

    for source in (docs, readme):
        assert "hosted-prod-actionable-proof-manifest.json" in source
        assert "config_digest" in source
        assert "run_detail_summary" in source
        assert "screenshot_path" in source
        assert "does_not_prove=hosted_real_outcome" in source


def test_playwright_global_teardown_waits_for_launcher_pid_file_before_stopping_stack():
    teardown = (ROOT / "frontend" / "tests" / "e2e" / "global-teardown.ts").read_text(encoding="utf-8")

    assert "waitForPidFile" in teardown
    assert "pids.json" in teardown
    assert "setTimeout" in teardown
    assert "stop_local_stack.py" in teardown


def test_deployment_manual_trigger_example_carries_operator_query():
    docs = (ROOT / "docs" / "deployment.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    for source in (docs, readme):
        assert "run-once --symbol ETH-USDT-SWAP --query" in source
        assert "audit note" in source


def test_deployment_docs_distinguish_local_smoke_profiles():
    docs = (ROOT / "docs" / "deployment.md").read_text(encoding="utf-8")

    assert "python3 tools/local_stack/smoke_local_stack.py" in docs
    assert "python3 tools/local_stack/smoke_local_stack.py --with-mock-llm" in docs
    assert "python3 tools/local_stack/smoke_local_stack.py --with-actionable-staging" in docs
    assert "python3 tools/local_stack/smoke_local_stack.py --prod-actionable" in docs
    assert "python3 tools/local_stack/smoke_local_stack.py --prod-actionable --fail-on-skip" in docs
    assert '"smoke_profile": "prod_actionable"' in docs
    assert '"skip_reason": "missing_readiness"' in docs
    assert '"exit_semantics": "fail_on_skip"' in docs
    assert "structured skip" in docs
    assert "not production success" in docs
    assert '"proof_level": "local-prod-actionable-rehearsal"' in docs
    assert '"production_success": false' in docs
    assert '"does_not_prove": "hosted_prod_actionable"' in docs


def test_deployment_docs_define_prod_actionable_success_contract():
    docs = (ROOT / "docs" / "deployment.md").read_text(encoding="utf-8")

    for required in (
        "BARK_DEVICE_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_MODEL",
        "OPENAI_API_KEY",
        "MACRO_EVENT_PROVIDER=no_active_event",
        "MACRO_EVENT_OPERATOR_REF",
        "MACRO_EVENT_CONFIRMED_AT",
        "MACRO_EVENT_SOURCE_REF",
        "MACRO_EVENT_ASSERTION_HORIZON",
        "MACRO_EVENT_VALID_UNTIL",
        '"allowed": true',
        '"market_provider": "okx_public"',
        '"manual_execution_required": true',
        '"auto_order_enabled": false',
    ):
        assert required in docs


def test_readme_points_to_smoke_profile_runbook():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "tools/local_stack/smoke_local_stack.py" in readme
    assert "--with-mock-llm" in readme
    assert "--with-actionable-staging" in readme
    assert "--prod-actionable" in readme
    assert "--fail-on-skip" in readme
    assert "docs/deployment.md" in readme
    assert "not production success" in readme
