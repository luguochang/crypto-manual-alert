from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Sequence


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROJECT_NAME = "crypto-alert-runtime-smoke"
DEFAULT_API_PORT = 18010
DEFAULT_FRONTEND_PORT = 13001
DEFAULT_SYMBOL = "ETH-USDT-SWAP"
DEFAULT_QUERY = "Docker hosted runtime smoke：验证容器工作台人工提醒入口"
DEFAULT_HORIZON = "6h"
DEFAULT_PYTHON_BASE_IMAGE = "public.ecr.aws/docker/library/python:3.12-slim"
DEFAULT_NODE_BASE_IMAGE = "public.ecr.aws/docker/library/node:22-alpine"

Runner = Callable[..., subprocess.CompletedProcess[str]]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build/start the Docker hosted workbench, run hosted-workbench smoke, "
            "then clean up. Default mode proves fixture hosted-runtime only, not prod-actionable."
        )
    )
    parser.add_argument("--project-name", default=DEFAULT_PROJECT_NAME)
    parser.add_argument("--api-port", type=int, default=DEFAULT_API_PORT)
    parser.add_argument("--frontend-port", type=int, default=DEFAULT_FRONTEND_PORT)
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL)
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--horizon", default=DEFAULT_HORIZON)
    parser.add_argument("--python-base-image", default=DEFAULT_PYTHON_BASE_IMAGE)
    parser.add_argument("--node-base-image", default=DEFAULT_NODE_BASE_IMAGE)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--hosted-smoke-retries", type=int, default=3)
    parser.add_argument("--retry-delay", type=float, default=5.0)
    parser.add_argument(
        "--require-prod-config",
        action="store_true",
        help=(
            "Run hosted smoke in strict production-config mode and require it to pass. "
            "Default mode expects the strict check to reject fixture config."
        ),
    )
    parser.add_argument("--keep-running", action="store_true", help="Leave compose services running after smoke.")
    args = parser.parse_args(argv)

    result = run_smoke(
        project_name=args.project_name,
        api_port=args.api_port,
        frontend_port=args.frontend_port,
        symbol=args.symbol,
        query=args.query,
        horizon=args.horizon,
        python_base_image=args.python_base_image,
        node_base_image=args.node_base_image,
        timeout=args.timeout,
        hosted_smoke_retries=args.hosted_smoke_retries,
        retry_delay=args.retry_delay,
        require_prod_config=args.require_prod_config,
        keep_running=args.keep_running,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if result.get("ok") is True else 1


def run_smoke(
    *,
    project_name: str = DEFAULT_PROJECT_NAME,
    api_port: int = DEFAULT_API_PORT,
    frontend_port: int = DEFAULT_FRONTEND_PORT,
    symbol: str = DEFAULT_SYMBOL,
    query: str = DEFAULT_QUERY,
    horizon: str = DEFAULT_HORIZON,
    python_base_image: str = DEFAULT_PYTHON_BASE_IMAGE,
    node_base_image: str = DEFAULT_NODE_BASE_IMAGE,
    timeout: float = 10.0,
    hosted_smoke_retries: int = 3,
    retry_delay: float = 5.0,
    require_prod_config: bool = False,
    keep_running: bool = False,
    runner: Runner = subprocess.run,
) -> dict[str, Any]:
    api_base = f"http://127.0.0.1:{api_port}"
    frontend_base = f"http://127.0.0.1:{frontend_port}"
    env = {
        **os.environ,
        "API_PORT": str(api_port),
        "FRONTEND_PORT": str(frontend_port),
        "NEXT_PUBLIC_API_BASE_URL": api_base,
        "PYTHON_BASE_IMAGE": python_base_image,
        "NODE_BASE_IMAGE": node_base_image,
    }
    cleanup_result: dict[str, Any] | None = None

    try:
        _run(
            ["docker", "compose", "-p", project_name, "up", "-d", "--build", "api", "frontend"],
            runner=runner,
            env=env,
            stage="docker_compose_up",
        )
        hosted_smoke = _run_hosted_smoke_with_retries(
            api_base=api_base,
            frontend_base=frontend_base,
            symbol=symbol,
            query=query,
            horizon=horizon,
            timeout=timeout,
            require_prod_config=False,
            runner=runner,
            stage="hosted_workbench_smoke",
            retries=hosted_smoke_retries,
            retry_delay=retry_delay,
        )
        strict_smoke = _run_hosted_smoke(
            api_base=api_base,
            frontend_base=frontend_base,
            symbol=symbol,
            query=(
                "Docker hosted runtime production-config smoke"
                if require_prod_config
                else "Docker hosted runtime strict config negative smoke"
            ),
            horizon=horizon,
            timeout=timeout,
            require_prod_config=True,
            runner=runner,
            stage="strict_prod_config_smoke",
            check=require_prod_config,
        )
        strict_status = _strict_status(strict_smoke, require_prod_config=require_prod_config)
        if require_prod_config and strict_smoke.returncode != 0:
            return _failure(
                "strict_prod_config_smoke",
                strict_smoke,
                cleanup_result=None,
                proof_level="prod-config",
            )
        if not require_prod_config and strict_smoke.returncode == 0:
            return {
                "ok": False,
                "stage": "strict_prod_config_negative_smoke",
                "proof_level": "hosted-runtime",
                "error": "default fixture hosted runtime unexpectedly passed --require-prod-config",
                "hosted_runtime_only_not_prod_actionable": True,
            }

        return {
            "ok": True,
            "stage": "complete",
            "proof_level": "prod-config" if require_prod_config else "hosted-runtime",
            "project_name": project_name,
            "api": api_base,
            "frontend": frontend_base,
            "hosted_smoke": _json_or_text(hosted_smoke.stdout),
            "strict_prod_config_check": strict_status,
            "strict_prod_config_smoke": _json_or_text(strict_smoke.stdout),
            "production_config_required": require_prod_config,
            "hosted_runtime_only_not_prod_actionable": not require_prod_config,
        }
    except subprocess.CalledProcessError as exc:
        return _failure(
            str(getattr(exc, "stage", "command")),
            exc,
            cleanup_result=cleanup_result,
            proof_level="prod-config" if require_prod_config else "hosted-runtime",
        )
    finally:
        if not keep_running:
            try:
                cleanup = _run(
                    ["docker", "compose", "-p", project_name, "down", "--remove-orphans"],
                    runner=runner,
                    env=env,
                    stage="docker_compose_down",
                )
                cleanup_result = {
                    "returncode": cleanup.returncode,
                    "stdout": cleanup.stdout,
                    "stderr": cleanup.stderr,
                }
            except subprocess.CalledProcessError:
                pass


def _run_hosted_smoke(
    *,
    api_base: str,
    frontend_base: str,
    symbol: str,
    query: str,
    horizon: str,
    timeout: float,
    require_prod_config: bool,
    runner: Runner,
    stage: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        str(ROOT / "tools" / "deployment" / "smoke_hosted_workbench.py"),
        "--api-base",
        api_base,
        "--frontend-base",
        frontend_base,
        "--symbol",
        symbol,
        "--query",
        query,
        "--horizon",
        horizon,
        "--timeout",
        str(timeout),
    ]
    if require_prod_config:
        command.append("--require-prod-config")
    return _run(command, runner=runner, env=None, stage=stage, check=check)


def _run_hosted_smoke_with_retries(
    *,
    api_base: str,
    frontend_base: str,
    symbol: str,
    query: str,
    horizon: str,
    timeout: float,
    require_prod_config: bool,
    runner: Runner,
    stage: str,
    retries: int,
    retry_delay: float,
) -> subprocess.CompletedProcess[str]:
    attempts = max(1, retries)
    last_error: subprocess.CalledProcessError | None = None
    for attempt in range(1, attempts + 1):
        try:
            return _run_hosted_smoke(
                api_base=api_base,
                frontend_base=frontend_base,
                symbol=symbol,
                query=query,
                horizon=horizon,
                timeout=timeout,
                require_prod_config=require_prod_config,
                runner=runner,
                stage=stage,
            )
        except subprocess.CalledProcessError as exc:
            last_error = exc
            if attempt < attempts and retry_delay > 0:
                time.sleep(retry_delay)
    assert last_error is not None
    raise last_error


def _run(
    command: Sequence[str],
    *,
    runner: Runner,
    env: dict[str, str] | None,
    stage: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    try:
        return runner(
            list(command),
            cwd=str(ROOT),
            env=env,
            text=True,
            capture_output=True,
            check=check,
        )
    except subprocess.CalledProcessError as exc:
        setattr(exc, "stage", stage)
        raise


def _strict_status(result: subprocess.CompletedProcess[str], *, require_prod_config: bool) -> str:
    if require_prod_config:
        return "passed_required_prod_config"
    if result.returncode != 0:
        return "expected_negative_rejected_fixture"
    return "unexpected_passed_fixture"


def _failure(
    stage: str,
    exc: subprocess.CalledProcessError | subprocess.CompletedProcess[str],
    *,
    cleanup_result: dict[str, Any] | None,
    proof_level: str,
) -> dict[str, Any]:
    return {
        "ok": False,
        "stage": stage,
        "proof_level": proof_level,
        "returncode": exc.returncode,
        "stdout": getattr(exc, "stdout", None) or getattr(exc, "output", None),
        "stderr": getattr(exc, "stderr", None),
        "cleanup": cleanup_result,
        "hosted_runtime_only_not_prod_actionable": proof_level == "hosted-runtime",
    }


def _json_or_text(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


if __name__ == "__main__":
    raise SystemExit(main())
