from __future__ import annotations

import argparse
import json
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin
from urllib.request import Request, urlopen


DEFAULT_API_BASE = "http://127.0.0.1:8010"
DEFAULT_FRONTEND_BASE = "http://127.0.0.1:3001"


class HostedWorkbenchSmokeError(RuntimeError):
    pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Smoke-test an already running hosted workbench: API health, frontend render, "
            "manual run creation, and run-detail projection. This is not prod-actionable proof."
        )
    )
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--frontend-base", default=DEFAULT_FRONTEND_BASE)
    parser.add_argument("--symbol", default="ETH-USDT-SWAP")
    parser.add_argument("--query", default="部署后工作台手动提醒 smoke：验证 API、前端、详情投影是否闭环。")
    parser.add_argument("--horizon", default="6h")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument(
        "--require-prod-config",
        action="store_true",
        help=(
            "Fail unless the hosted API reports production-intent config "
            "(openai_compatible, okx_public, Bark enabled, prod_actionable readiness)."
        ),
    )
    args = parser.parse_args(argv)

    try:
        result = run_smoke(
            api_base=args.api_base,
            frontend_base=args.frontend_base,
            symbol=args.symbol,
            query=args.query,
            horizon=args.horizon,
            timeout=args.timeout,
            require_prod_config=args.require_prod_config,
        )
    except HostedWorkbenchSmokeError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "smoke_profile": "hosted_workbench",
                    "error": str(exc),
                    "api": _normalize_base(args.api_base),
                    "frontend": _normalize_base(args.frontend_base),
                    "production_config_required": args.require_prod_config,
                    "hosted_runtime_only_not_prod_actionable": True,
                },
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
        )
        return 1

    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


def run_smoke(
    *,
    api_base: str,
    frontend_base: str,
    symbol: str,
    query: str,
    horizon: str,
    timeout: float,
    require_prod_config: bool = False,
) -> dict[str, Any]:
    api = _normalize_base(api_base)
    frontend = _normalize_base(frontend_base)

    health = _get_json(_join(api, "/api/system/health"), timeout=timeout, label="API health")
    _require_envelope_ok(health, "API health")

    config = _get_json(_join(api, "/api/system/config"), timeout=timeout, label="API config")
    config_data = _require_envelope_ok(config, "API config")
    trading = _require_dict(config_data.get("trading"), "API config trading")
    manual_execution_required = trading.get("manual_execution_required")
    auto_order_enabled = trading.get("auto_order_enabled")
    if manual_execution_required is not True:
        raise HostedWorkbenchSmokeError("API config must report manual_execution_required=true")
    if auto_order_enabled is not False:
        raise HostedWorkbenchSmokeError("API config must report auto_order_enabled=false")

    decision = config_data.get("decision") if isinstance(config_data.get("decision"), dict) else {}
    market = config_data.get("market_data") if isinstance(config_data.get("market_data"), dict) else {}
    notification = config_data.get("notification") if isinstance(config_data.get("notification"), dict) else {}
    macro_event = config_data.get("macro_event") if isinstance(config_data.get("macro_event"), dict) else {}
    workflow = config_data.get("workflow") if isinstance(config_data.get("workflow"), dict) else {}
    readiness = config_data.get("readiness") if isinstance(config_data.get("readiness"), dict) else {}
    prod_actionable = readiness.get("prod_actionable") if isinstance(readiness.get("prod_actionable"), dict) else {}
    market_readiness = readiness.get("market_data") if isinstance(readiness.get("market_data"), dict) else {}

    if require_prod_config:
        _require_prod_config(
            decision=decision,
            market=market,
            market_readiness=market_readiness,
            notification=notification,
            macro_event=macro_event,
            workflow=workflow,
            prod_actionable=prod_actionable,
        )

    _require_html(_get_text(frontend, timeout=timeout, label="frontend home"), "frontend home")

    manual = _post_json(
        _join(api, "/api/runs/manual"),
        {
            "symbol": symbol,
            "query": query,
            "horizon": horizon,
            "alert_channel": "bark",
        },
        timeout=timeout,
        label="manual run",
    )
    manual_data = _require_envelope_ok(manual, "manual run")
    trace_id = _require_string(manual_data.get("trace_id"), "manual run trace_id")
    _require_dict(manual_data.get("business_summary"), "manual run business_summary")
    result_review = _require_dict(manual_data.get("result_review"), "manual run result_review")
    plan = _require_dict(manual_data.get("plan"), "manual run plan")
    if plan.get("manual_execution_required") is not True:
        raise HostedWorkbenchSmokeError("manual run plan must keep manual_execution_required=true")

    detail = _get_json(_join(api, f"/api/runs/{quote(trace_id, safe='')}"), timeout=timeout, label="run detail")
    detail_data = _require_envelope_ok(detail, "run detail")
    plan_run = _require_dict(detail_data.get("plan_run"), "run detail plan_run")
    _require_dict(plan_run.get("business_summary"), "run detail business_summary")
    _require_dict(detail_data.get("result_review"), "run detail result_review")

    _require_html(
        _get_text(_join(frontend, f"/runs/{quote(trace_id, safe='')}"), timeout=timeout, label="frontend run detail"),
        "frontend run detail",
    )

    trace = detail_data.get("trace") if isinstance(detail_data.get("trace"), dict) else {}

    return {
        "ok": True,
        "smoke_profile": "hosted_workbench",
        "api": api,
        "frontend": frontend,
        "trace_id": trace_id,
        "allowed": trace.get("allowed", manual_data.get("verdict", {}).get("allowed") if isinstance(manual_data.get("verdict"), dict) else None),
        "decision_engine": decision.get("engine"),
        "decision_final_input_mode": decision.get("final_input_mode"),
        "candidate_sidecar_mode": decision.get("candidate_sidecar_mode"),
        "market_provider": market.get("provider"),
        "notification_enabled": notification.get("enabled"),
        "macro_event_provider": macro_event.get("provider"),
        "workflow_execution_mode": workflow.get("execution_mode"),
        "prod_actionable_status": prod_actionable.get("status"),
        "prod_actionable_ready": prod_actionable.get("prod_actionable_ready"),
        "manual_execution_required": manual_execution_required,
        "auto_order_enabled": auto_order_enabled,
        "result_review_status": result_review.get("status"),
        "production_config_required": require_prod_config,
        "production_config_ready": prod_actionable.get("prod_actionable_ready") is True,
        "hosted_runtime_only_not_prod_actionable": True,
    }


def _require_prod_config(
    *,
    decision: dict[str, Any],
    market: dict[str, Any],
    market_readiness: dict[str, Any],
    notification: dict[str, Any],
    macro_event: dict[str, Any],
    workflow: dict[str, Any],
    prod_actionable: dict[str, Any],
) -> None:
    if decision.get("engine") != "openai_compatible":
        raise HostedWorkbenchSmokeError("production config requires decision.engine=openai_compatible")
    if decision.get("final_input_mode") != "legacy_prompt":
        raise HostedWorkbenchSmokeError("production config requires decision.final_input_mode=legacy_prompt")
    if decision.get("candidate_sidecar_mode") != "disabled":
        raise HostedWorkbenchSmokeError("production config requires decision.candidate_sidecar_mode=disabled")
    if market.get("provider") != "okx_public":
        raise HostedWorkbenchSmokeError("production config requires market_data.provider=okx_public")
    okx_base_url = str(market.get("okx_base_url") or "").strip()
    if okx_base_url and okx_base_url != "https://www.okx.com":
        raise HostedWorkbenchSmokeError(
            "production config requires market_data.okx_base_url unset or https://www.okx.com"
        )
    if market_readiness.get("status") == "unsafe":
        raise HostedWorkbenchSmokeError("production config requires readiness.market_data.status!=unsafe")
    if notification.get("enabled") is not True:
        raise HostedWorkbenchSmokeError("production config requires notification.enabled=true")
    if macro_event.get("provider") != "no_active_event":
        raise HostedWorkbenchSmokeError("production config requires macro_event.provider=no_active_event")
    if workflow.get("execution_mode") != "legacy_baseline":
        raise HostedWorkbenchSmokeError("production config requires workflow.execution_mode=legacy_baseline")
    if prod_actionable.get("prod_actionable_ready") is not True or prod_actionable.get("status") != "ready":
        raise HostedWorkbenchSmokeError("production config requires readiness.prod_actionable.status=ready")


def _normalize_base(value: str) -> str:
    return value.rstrip("/")


def _join(base: str, path: str) -> str:
    return urljoin(f"{base}/", path.lstrip("/"))


def _get_json(url: str, *, timeout: float, label: str) -> dict[str, Any]:
    request = Request(url, headers={"accept": "application/json"})
    return _read_json(request, timeout=timeout, label=label)


def _post_json(url: str, payload: dict[str, Any], *, timeout: float, label: str) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=body,
        method="POST",
        headers={"content-type": "application/json", "accept": "application/json"},
    )
    return _read_json(request, timeout=timeout, label=label)


def _read_json(request: Request, *, timeout: float, label: str) -> dict[str, Any]:
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise HostedWorkbenchSmokeError(f"{label} returned HTTP {exc.code}") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise HostedWorkbenchSmokeError(f"{label} request failed: {exc}") from exc
    if not isinstance(payload, dict):
        raise HostedWorkbenchSmokeError(f"{label} returned non-object JSON")
    return payload


def _get_text(url: str, *, timeout: float, label: str) -> str:
    request = Request(url, headers={"accept": "text/html"})
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        raise HostedWorkbenchSmokeError(f"{label} returned HTTP {exc.code}") from exc
    except (URLError, TimeoutError) as exc:
        raise HostedWorkbenchSmokeError(f"{label} request failed: {exc}") from exc


def _require_envelope_ok(payload: dict[str, Any], label: str) -> dict[str, Any]:
    if payload.get("ok") is not True:
        raise HostedWorkbenchSmokeError(f"{label} returned ok=false")
    data = payload.get("data")
    return _require_dict(data, f"{label} data")


def _require_dict(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise HostedWorkbenchSmokeError(f"{label} is missing or not an object")
    return value


def _require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise HostedWorkbenchSmokeError(f"{label} is missing or not a string")
    return value


def _require_html(text: str, label: str) -> None:
    if "<html" not in text.lower():
        raise HostedWorkbenchSmokeError(f"{label} did not return an HTML page")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
