from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "deployment" / "smoke_docker_hosted_runtime.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("smoke_docker_hosted_runtime", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeRunner:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []
        self.envs: list[dict[str, str] | None] = []

    def __call__(self, command, **kwargs):
        cmd = list(command)
        self.commands.append(cmd)
        self.envs.append(kwargs.get("env"))
        if "smoke_hosted_workbench.py" in " ".join(cmd) and "--require-prod-config" in cmd:
            return subprocess.CompletedProcess(
                cmd,
                1,
                stdout='{"ok": false, "error": "production config requires decision.engine=openai_compatible"}',
                stderr="",
            )
        return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": true}', stderr="")


def test_docker_hosted_runtime_smoke_runs_compose_smoke_strict_negative_and_cleanup():
    module = _load_module()
    runner = _FakeRunner()

    result = module.run_smoke(
        project_name="crypto-alert-runtime-smoke-test",
        api_port=18010,
        frontend_port=13001,
        python_base_image="public.ecr.aws/docker/library/python:3.12-slim",
        node_base_image="public.ecr.aws/docker/library/node:22-alpine",
        runner=runner,
    )

    assert result["ok"] is True
    assert result["proof_level"] == "hosted-runtime"
    assert result["hosted_runtime_only_not_prod_actionable"] is True
    assert result["strict_prod_config_check"] == "expected_negative_rejected_fixture"

    compose_up = runner.commands[0]
    assert compose_up == [
        "docker",
        "compose",
        "-p",
        "crypto-alert-runtime-smoke-test",
        "up",
        "-d",
        "--build",
        "api",
        "frontend",
    ]
    compose_env = runner.envs[0]
    assert compose_env["API_PORT"] == "18010"
    assert compose_env["FRONTEND_PORT"] == "13001"
    assert compose_env["NEXT_PUBLIC_API_BASE_URL"] == "http://127.0.0.1:18010"
    assert compose_env["PYTHON_BASE_IMAGE"] == "public.ecr.aws/docker/library/python:3.12-slim"
    assert compose_env["NODE_BASE_IMAGE"] == "public.ecr.aws/docker/library/node:22-alpine"

    assert any("smoke_hosted_workbench.py" in " ".join(command) for command in runner.commands)
    strict_command = next(command for command in runner.commands if "--require-prod-config" in command)
    assert "--api-base" in strict_command
    assert "http://127.0.0.1:18010" in strict_command
    assert runner.commands[-1] == [
        "docker",
        "compose",
        "-p",
        "crypto-alert-runtime-smoke-test",
        "down",
        "--remove-orphans",
    ]


def test_docker_hosted_runtime_smoke_cleans_up_after_compose_failure():
    module = _load_module()

    def failing_runner(command, **kwargs):
        cmd = list(command)
        if cmd[:4] == ["docker", "compose", "-p", "crypto-alert-runtime-smoke-test"]:
            if "up" in cmd:
                raise subprocess.CalledProcessError(1, cmd, output="", stderr="compose failed")
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": true}', stderr="")

    calls: list[list[str]] = []

    result = module.run_smoke(
        project_name="crypto-alert-runtime-smoke-test",
        api_port=18010,
        frontend_port=13001,
        runner=failing_runner,
    )

    assert result["ok"] is False
    assert result["stage"] == "docker_compose_up"
    assert result["proof_level"] == "hosted-runtime"
    assert calls[-1] == [
        "docker",
        "compose",
        "-p",
        "crypto-alert-runtime-smoke-test",
        "down",
        "--remove-orphans",
    ]


def test_docker_hosted_runtime_smoke_retries_transient_hosted_smoke_failure():
    module = _load_module()
    smoke_attempts = 0

    def flaky_runner(command, **kwargs):
        nonlocal smoke_attempts
        cmd = list(command)
        if "smoke_hosted_workbench.py" in " ".join(cmd) and "--require-prod-config" not in cmd:
            smoke_attempts += 1
            if smoke_attempts == 1:
                raise subprocess.CalledProcessError(1, cmd, output="", stderr="frontend connection reset")
        if "smoke_hosted_workbench.py" in " ".join(cmd) and "--require-prod-config" in cmd:
            return subprocess.CompletedProcess(
                cmd,
                1,
                stdout='{"ok": false, "error": "production config requires decision.engine=openai_compatible"}',
                stderr="",
            )
        return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": true}', stderr="")

    result = module.run_smoke(
        project_name="crypto-alert-runtime-smoke-test",
        api_port=18010,
        frontend_port=13001,
        hosted_smoke_retries=2,
        retry_delay=0,
        runner=flaky_runner,
    )

    assert result["ok"] is True
    assert smoke_attempts == 2
