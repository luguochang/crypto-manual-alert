from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
PLAYWRIGHT = FRONTEND / "node_modules" / ".bin" / "playwright"
DISCOVERY_TASK_ID = "11111111-1111-4111-8111-111111111111"
DISCOVERY_RUN_ID = "22222222-2222-4222-8222-222222222222"


@dataclass(frozen=True)
class DiscoveryCase:
    profile: str
    specs: frozenset[str]
    projects: frozenset[str]
    environment: dict[str, str] = field(default_factory=dict)


PROFILE_CASES = (
    DiscoveryCase(
        profile="fixture",
        specs=frozenset(
            {
                "background-deep-research.spec.ts",
                "notification-recovery.spec.ts",
                "research-evidence-disclosure.spec.ts",
                "runs-product.spec.ts",
                "work-product.spec.ts",
            }
        ),
        projects=frozenset({"fixture-desktop", "fixture-pixel-7"}),
    ),
    DiscoveryCase(
        profile="real-provider",
        specs=frozenset({"real-product-flow.spec.ts"}),
        projects=frozenset({"real-provider-desktop", "real-provider-pixel-7"}),
        environment={"REAL_PRODUCT_E2E": "1"},
    ),
    DiscoveryCase(
        profile="failure-injection",
        specs=frozenset({"database-rollback.spec.ts", "provider-failures.spec.ts"}),
        projects=frozenset({"failure-injection-desktop", "failure-injection-pixel-7"}),
        environment={
            "FAILURE_INJECTION_ENABLED": "1",
            "FAILURE_INJECTION_CONTROL_TOKEN": "discovery-placeholder",
        },
    ),
    DiscoveryCase(
        profile="real-official-stream",
        specs=frozenset({"official-stream-main-flow.spec.ts"}),
        projects=frozenset({"fixture-desktop", "fixture-pixel-7"}),
        environment={"REAL_PRODUCT_E2E": "1"},
    ),
    DiscoveryCase(
        profile="real-cancel",
        specs=frozenset({"durable-cancel-flow.spec.ts"}),
        projects=frozenset({"fixture-desktop", "fixture-pixel-7"}),
        environment={"REAL_PRODUCT_E2E": "1"},
    ),
    DiscoveryCase(
        profile="real-hitl",
        specs=frozenset({"hitl-review-flow.spec.ts"}),
        projects=frozenset({"fixture-desktop", "fixture-pixel-7"}),
        environment={
            "REAL_PRODUCT_E2E": "1",
            "HITL_TASK_ID_DESKTOP": DISCOVERY_TASK_ID,
            "HITL_TASK_ID_MOBILE": DISCOVERY_TASK_ID,
        },
    ),
    DiscoveryCase(
        profile="real-inbox",
        specs=frozenset({"real-inbox-flow.spec.ts"}),
        projects=frozenset({"fixture-desktop", "fixture-pixel-7"}),
        environment={
            "REAL_PRODUCT_E2E": "1",
            "REAL_INBOX_TASK_ID": DISCOVERY_TASK_ID,
        },
    ),
    DiscoveryCase(
        profile="real-library",
        specs=frozenset({"real-library-run-detail.spec.ts"}),
        projects=frozenset({"fixture-desktop", "fixture-pixel-7"}),
        environment={"REAL_LIBRARY_E2E": "1"},
    ),
    DiscoveryCase(
        profile="real-fork",
        specs=frozenset({"real-fork-flow.spec.ts"}),
        projects=frozenset({"fixture-desktop", "fixture-pixel-7"}),
        environment={
            "REAL_FORK_E2E": "1",
            "REAL_FORK_TASK_ID_DESKTOP": DISCOVERY_TASK_ID,
            "REAL_FORK_SOURCE_RUN_ID_DESKTOP": DISCOVERY_RUN_ID,
            "REAL_FORK_TASK_ID_MOBILE": DISCOVERY_TASK_ID,
            "REAL_FORK_SOURCE_RUN_ID_MOBILE": DISCOVERY_RUN_ID,
        },
    ),
    DiscoveryCase(
        profile="real-multi-interrupt",
        specs=frozenset({"real-multi-interrupt-flow.spec.ts"}),
        projects=frozenset({"fixture-desktop", "fixture-pixel-7"}),
        environment={"REAL_MULTI_INTERRUPT_E2E": "1"},
    ),
    DiscoveryCase(
        profile="controlled-deep-research-hitl",
        specs=frozenset({"deep-research-hitl-flow.spec.ts"}),
        projects=frozenset({"fixture-desktop", "fixture-pixel-7"}),
        environment={
            "REAL_PRODUCT_E2E": "1",
            "CONTROLLED_DEEP_RESEARCH_HITL_E2E": "1",
            "DEEP_RESEARCH_HITL_TASK_ID_DESKTOP": DISCOVERY_TASK_ID,
            "DEEP_RESEARCH_HITL_TASK_ID_MOBILE": DISCOVERY_TASK_ID,
        },
    ),
    DiscoveryCase(
        profile="real-deep-research",
        specs=frozenset({"real-deep-research-flow.spec.ts"}),
        projects=frozenset({"fixture-desktop", "fixture-pixel-7"}),
        environment={
            "REAL_PRODUCT_E2E": "1",
            "REAL_DEEP_RESEARCH_E2E": "1",
            "PLAYWRIGHT_EVIDENCE_DIR": "/tmp/crypto-alert-v2-discovery-evidence",
        },
    ),
    DiscoveryCase(
        profile="m4-security",
        specs=frozenset({"cross-tenant-security.spec.ts"}),
        projects=frozenset({"fixture-desktop", "fixture-pixel-7"}),
        environment={"M4_SECURITY_E2E": "1"},
    ),
)


def _discovery_environment(
    profile: str, extra: dict[str, str] | None = None
) -> dict[str, str]:
    environment = {
        "HOME": os.environ["HOME"],
        "PATH": os.environ["PATH"],
        "PLAYWRIGHT_EXTERNAL_SERVER": "1",
        "V2_E2E_PROFILE": profile,
    }
    environment.update(extra or {})
    return environment


def _run_list(
    *,
    profile: str,
    environment: dict[str, str] | None = None,
    command: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    assert PLAYWRIGHT.is_file(), "install frontend dependencies before discovery"
    return subprocess.run(
        command or [str(PLAYWRIGHT), "test", "--list"],
        cwd=FRONTEND,
        env=_discovery_environment(profile, environment),
        capture_output=True,
        text=True,
        check=False,
    )


def _collected(
    result: subprocess.CompletedProcess[str],
) -> tuple[set[str], set[str], set[tuple[str, str]]]:
    assert result.returncode == 0, result.stdout + result.stderr
    matches = re.findall(
        r"^\s+\[([^\]]+)]\s+.*?([^/\\\s]+\.spec\.ts):\d+:\d+\s+",
        result.stdout,
        flags=re.MULTILINE,
    )
    assert matches, result.stdout
    pairs = set(matches)
    return (
        {spec for _, spec in pairs},
        {project for project, _ in pairs},
        pairs,
    )


@pytest.mark.parametrize("case", PROFILE_CASES, ids=lambda case: case.profile)
def test_each_playwright_profile_collects_only_its_owned_specs(
    case: DiscoveryCase,
):
    specs, projects, pairs = _collected(
        _run_list(
            profile=case.profile,
            environment=case.environment,
        )
    )

    assert specs == set(case.specs)
    assert projects == set(case.projects)
    assert pairs == {
        (project, spec) for project in case.projects for spec in case.specs
    }


@pytest.mark.parametrize(
    ("script", "profile", "spec", "projects", "environment"),
    (
        (
            "test:e2e:real-provider",
            "real-provider",
            "real-product-flow.spec.ts",
            {"real-provider-desktop", "real-provider-pixel-7"},
            {"REAL_PRODUCT_E2E": "1"},
        ),
        (
            "test:e2e:official-stream",
            "real-official-stream",
            "official-stream-main-flow.spec.ts",
            {"fixture-desktop", "fixture-pixel-7"},
            {"REAL_PRODUCT_E2E": "1"},
        ),
        (
            "test:e2e:real-cancel",
            "real-cancel",
            "durable-cancel-flow.spec.ts",
            {"fixture-desktop", "fixture-pixel-7"},
            {"REAL_PRODUCT_E2E": "1"},
        ),
        (
            "test:e2e:real-hitl",
            "real-hitl",
            "hitl-review-flow.spec.ts",
            {"fixture-desktop", "fixture-pixel-7"},
            {
                "REAL_PRODUCT_E2E": "1",
                "HITL_TASK_ID_DESKTOP": DISCOVERY_TASK_ID,
                "HITL_TASK_ID_MOBILE": DISCOVERY_TASK_ID,
            },
        ),
        (
            "test:e2e:real-inbox",
            "real-inbox",
            "real-inbox-flow.spec.ts",
            {"fixture-desktop", "fixture-pixel-7"},
            {
                "REAL_PRODUCT_E2E": "1",
                "REAL_INBOX_TASK_ID": DISCOVERY_TASK_ID,
            },
        ),
        (
            "test:e2e:real-library",
            "real-library",
            "real-library-run-detail.spec.ts",
            {"fixture-desktop", "fixture-pixel-7"},
            {"REAL_LIBRARY_E2E": "1"},
        ),
        (
            "test:e2e:real-fork",
            "real-fork",
            "real-fork-flow.spec.ts",
            {"fixture-desktop", "fixture-pixel-7"},
            {
                "REAL_FORK_E2E": "1",
                "REAL_FORK_TASK_ID_DESKTOP": DISCOVERY_TASK_ID,
                "REAL_FORK_SOURCE_RUN_ID_DESKTOP": DISCOVERY_RUN_ID,
                "REAL_FORK_TASK_ID_MOBILE": DISCOVERY_TASK_ID,
                "REAL_FORK_SOURCE_RUN_ID_MOBILE": DISCOVERY_RUN_ID,
            },
        ),
        (
            "test:e2e:real-multi-interrupt",
            "real-multi-interrupt",
            "real-multi-interrupt-flow.spec.ts",
            {"fixture-desktop", "fixture-pixel-7"},
            {"REAL_MULTI_INTERRUPT_E2E": "1"},
        ),
        (
            "test:e2e:controlled-deep-research-hitl",
            "controlled-deep-research-hitl",
            "deep-research-hitl-flow.spec.ts",
            {"fixture-desktop", "fixture-pixel-7"},
            {
                "REAL_PRODUCT_E2E": "1",
                "CONTROLLED_DEEP_RESEARCH_HITL_E2E": "1",
                "DEEP_RESEARCH_HITL_TASK_ID_DESKTOP": DISCOVERY_TASK_ID,
                "DEEP_RESEARCH_HITL_TASK_ID_MOBILE": DISCOVERY_TASK_ID,
            },
        ),
        (
            "test:e2e:real-deep-research",
            "real-deep-research",
            "real-deep-research-flow.spec.ts",
            {"fixture-desktop", "fixture-pixel-7"},
            {
                "REAL_PRODUCT_E2E": "1",
                "REAL_DEEP_RESEARCH_E2E": "1",
                "PLAYWRIGHT_EVIDENCE_DIR": (
                    "/tmp/crypto-alert-v2-discovery-evidence"
                ),
            },
        ),
    ),
)
def test_real_npm_script_collects_its_target_spec_only(
    script: str,
    profile: str,
    spec: str,
    projects: set[str],
    environment: dict[str, str],
):
    specs, collected_projects, pairs = _collected(
        _run_list(
            profile=profile,
            environment=environment,
            command=["npm", "run", script, "--", "--list"],
        )
    )

    assert specs == {spec}
    assert collected_projects == projects
    assert pairs == {(project, spec) for project in projects}


@pytest.mark.parametrize(
    "profile",
    (
        "real-provider",
        "failure-injection",
        "real-official-stream",
        "real-cancel",
        "real-hitl",
        "real-inbox",
        "real-library",
        "real-fork",
        "real-multi-interrupt",
        "controlled-deep-research-hitl",
        "real-deep-research",
        "m4-security",
    ),
)
def test_non_fixture_profile_rejects_a_missing_environment_gate(profile: str):
    result = _run_list(profile=profile)

    assert result.returncode != 0
    assert f"V2_E2E_PROFILE={profile} requires " in result.stderr
