from __future__ import annotations

from pathlib import Path
import re

import yaml


ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _yaml(relative: str) -> dict[str, object]:
    value = yaml.safe_load(_read(relative))
    assert isinstance(value, dict)
    return value


def test_task14_repository_owned_assets_exist() -> None:
    expected = {
        ".github/workflows/ci.yml",
        "backend/Dockerfile",
        "deploy/docker-compose.production.yml",
        "deploy/env.production.example",
        "deploy/alerts.yaml",
        "deploy/attestation-policy.yaml",
        "docs/v2/runbooks/production.md",
        "frontend/tests/e2e/hosted-production.spec.ts",
        "frontend/tests/e2e/hosted-security.spec.ts",
        "frontend/Dockerfile",
        "tools/v2/build_production_images.sh",
        "tools/v2/probe_production_stack.sh",
    }
    assert {path for path in expected if not (ROOT / path).is_file()} == set()


def test_production_compose_is_immutable_and_has_no_development_identity() -> None:
    source = _read("deploy/docker-compose.production.yml")
    compose = _yaml("deploy/docker-compose.production.yml")
    services = compose["services"]
    assert isinstance(services, dict)
    assert {
        "product-postgres",
        "agent-postgres",
        "langgraph-redis",
        "migrate",
        "langgraph-api",
        "langgraph-api-readiness",
        "command-worker",
        "frontend",
        "ingress",
    }.issubset(services)
    assert "development-bootstrap" not in services
    assert "backend/.env" not in source
    assert "env_file:" not in source
    assert "build:" not in source
    assert "DEVELOPMENT_BOOTSTRAP" not in source
    assert ":local" not in source
    assert "${BACKEND_IMAGE:?" in source
    assert "${FRONTEND_IMAGE:?" in source
    assert "${INGRESS_IMAGE:?" in source
    assert "APP_ENVIRONMENT: production" in source
    assert "read_only: true" in source
    assert "no-new-privileges:true" in source
    assert "cap_drop:" in source
    assert "127.0.0.1:${PRODUCTION_INGRESS_PORT:?" in source


def test_production_environment_example_contains_names_only() -> None:
    source = _read("deploy/env.production.example")
    assignments = [
        line for line in source.splitlines() if line and not line.startswith("#")
    ]
    assert assignments
    for assignment in assignments:
        name, separator, value = assignment.partition("=")
        assert separator == "="
        assert re.fullmatch(r"[A-Z][A-Z0-9_]*", name)
        assert value == ""
    for required in {
        "BACKEND_IMAGE=",
        "FRONTEND_IMAGE=",
        "INGRESS_IMAGE=",
        "PRODUCT_DATABASE_URL=",
        "AGENT_DATABASE_URL=",
        "OIDC_ISSUER=",
        "OIDC_CLIENT_ID=",
        "OIDC_CLIENT_SECRET=",
        "NEXTAUTH_SECRET=",
        "NEXTAUTH_URL=",
        "OPENAI_API_KEY=",
        "PRODUCTION_INGRESS_PORT=",
    }:
        assert required in assignments
    assert not re.search(r"(?:sk|tvly)-[A-Za-z0-9_-]{8,}", source)
    assert "BEGIN PRIVATE KEY" not in source


def test_production_images_are_locked_and_non_root() -> None:
    backend = _read("backend/Dockerfile")
    frontend = _read("frontend/Dockerfile")
    assert "FROM python:3.12-slim@sha256:" in backend
    assert "uv sync --frozen --no-dev --extra aegra" in backend
    assert "USER 10001:10001" in backend
    assert "COPY backend ./" in backend
    assert backend.index("USER 10001:10001") < backend.index("CMD [")
    assert frontend.count("FROM public.ecr.aws/docker/library/node:22@sha256:") == 3
    assert "RUN npm ci" in frontend
    assert "RUN npm run build" in frontend
    assert "USER node" in frontend
    assert "COPY --chown=node:node" in frontend
    assert "NEXT_PUBLIC_" not in frontend


def test_production_build_runner_reuses_free_scanners_and_fails_closed() -> None:
    source = _read("tools/v2/build_production_images.sh")
    assert "docker build --file backend/Dockerfile" in source
    assert "docker build --file frontend/Dockerfile" in source
    assert "anchore/syft:v1.27.1" in source
    assert '"$syft_image" scan "docker:$image_ref"' in source
    assert 'cyclonedx-json=/evidence/$output_name' in source
    assert "ghcr.io/aquasecurity/trivy:0.58.2" in source
    assert "tools/v2/summarize_trivy_image.py" in source
    assert "release image build requires a clean immutable source tree" in source
    assert "--allow-dirty-local-rehearsal" in source
    assert "registry_repo_digests_proved\": False" in source
    assert "docker push" not in source
    assert "docker login" not in source
    assert "backend/.env" not in source


def test_production_stack_probe_uses_compose_health_and_always_tears_down() -> None:
    source = _read("tools/v2/probe_production_stack.sh")
    assert "COMPOSE_DISABLE_ENV_FILE=1" in source
    assert "docker-compose.production.yml" in source
    assert 'trap cleanup EXIT' in source
    assert "down --volumes --remove-orphans" in source
    assert "up --detach --wait --wait-timeout 300" in source
    assert "/openapi.json" in source
    assert "/app/openapi.json" in source
    assert "NEXTAUTH_URL must use trusted HTTPS" in source
    assert "hosted production probe requires a clean immutable source tree" in source
    assert "backend/.env" not in source
    assert "production_ready\": False" in source


def test_alert_rules_cover_required_independent_failure_domains() -> None:
    document = _yaml("deploy/alerts.yaml")
    rules = document["rules"]
    assert isinstance(rules, list)
    ids = [rule["id"] for rule in rules]
    assert len(ids) == len(set(ids))
    assert {
        "agent_readiness_unavailable",
        "market_provider_exhausted",
        "search_provider_exhausted",
        "model_provider_exhausted",
        "langsmith_delivery_exhausted",
        "langfuse_delivery_exhausted",
        "projection_lag_high",
        "worker_stale",
        "outbox_dead_letter_present",
        "security_denial_spike",
        "error_budget_burn_fast",
    }.issubset(ids)
    for rule in rules:
        assert rule["source"] in {"metrics", "structured_logs"}
        assert rule["severity"] in {"critical", "warning"}
        assert rule["route"]
        assert rule["selector"]
    provider_rules = {
        rule["id"]: rule for rule in rules if rule["id"].endswith("delivery_exhausted")
    }
    assert provider_rules["langsmith_delivery_exhausted"]["selector"]["provider"] == "langsmith"
    assert provider_rules["langfuse_delivery_exhausted"]["selector"]["provider"] == "langfuse"
    assert provider_rules["langsmith_delivery_exhausted"]["selector"]["fingerprint"]
    assert provider_rules["langfuse_delivery_exhausted"]["selector"]["fingerprint"]


def test_attestation_policy_is_four_role_and_deny_by_default() -> None:
    policy = _yaml("deploy/attestation-policy.yaml")
    assert policy["verification"]["command"] == "cosign verify-blob"
    roles = policy["roles"]
    assert set(roles) == {
        "release_signer",
        "release_reviewer",
        "data_custodian",
        "platform_custodian",
    }
    for role in roles.values():
        assert role["status"] == "unconfigured"
        assert role["issuer"] == ""
        assert role["identity_regexp"] == "(?!)"
        assert role["independent_from"]
    assert policy["self_declared_signature_fields_accepted"] is False


def test_ci_and_runbook_keep_hosted_release_fail_closed() -> None:
    workflow = _read(".github/workflows/ci.yml")
    runbook = _read("docs/v2/runbooks/production.md")
    assert "permissions:\n  contents: read" in workflow
    assert "environment: v2-production" in workflow
    assert "startsWith(github.ref, 'refs/tags/v2-')" in workflow
    assert "backend/.env" not in workflow
    action_refs = re.findall(r"uses:\s+[^@\s]+@([^\s]+)", workflow)
    assert action_refs
    assert all(re.fullmatch(r"[0-9a-f]{40}", ref) for ref in action_refs)
    for command in {
        "pytest",
        "npm --prefix frontend run typecheck",
        "npm --prefix frontend run lint",
        "npm --prefix frontend run test:unit",
        "npm --prefix frontend run build",
        "docker compose",
        "tools/v2/build_production_images.sh",
        "--source-sha \"$GITHUB_SHA\"",
        "--output-digest \"$RUNNER_TEMP/production-image-set-digest.txt\"",
    }:
        assert command in workflow
    for section in {
        "## Deployment",
        "## Rollback",
        "## Backup And Restore",
        "## Key Rotation",
        "## Provider And Observability Outages",
        "## Quota And Entitlement Incidents",
        "## Data Deletion",
        "## Evidence Boundary",
    }:
        assert section in runbook
    assert "V2: PARTIAL" in runbook
    assert "Production Ready: `NO`" in runbook


def test_hosted_specs_require_real_https_and_forbid_route_interception() -> None:
    production = _read("frontend/tests/e2e/hosted-production.spec.ts")
    security = _read("frontend/tests/e2e/hosted-security.spec.ts")
    combined = production + security
    assert "https://" in combined
    assert "localhost" in combined
    assert "127.0.0.1" in combined
    assert "page.route(" not in combined
    assert "context.route(" not in combined
    assert "test.skip(" not in combined
    assert "HOSTED_PRODUCTION_E2E" in production
    assert "HOSTED_SECURITY_E2E" in security
    assert "storageState" in security
    assert "Pixel 7" in _read("frontend/playwright.config.ts")
