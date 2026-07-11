from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import re
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlparse
from urllib.request import Request, urlopen


DEFAULT_API_BASE = "http://127.0.0.1:8010"
DEFAULT_SYMBOL = "ETH-USDT-SWAP"
DEFAULT_QUERY = "Hosted prod-actionable smoke：验证真实人工提醒证据链。"
DEFAULT_HORIZON = "6h"


class HostedProdActionableSmokeError(RuntimeError):
    pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Smoke-test a hosted API for one real prod-actionable manual alert. "
            "Requires production config, allowed=true, real LLM evidence, exchange-native "
            "execution evidence, and Bark sent. This script never places orders."
        )
    )
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL)
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--horizon", default=DEFAULT_HORIZON)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument(
        "--proof-output",
        help=(
            "Optional path for a machine-readable hosted prod-actionable proof manifest. "
            "Written only after all strict production evidence predicates pass."
        ),
    )
    args = parser.parse_args(argv)

    try:
        result = run_smoke(
            api_base=args.api_base,
            symbol=args.symbol,
            query=args.query,
            horizon=args.horizon,
            timeout=args.timeout,
            proof_output=args.proof_output,
        )
    except HostedProdActionableSmokeError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "smoke_profile": "hosted_prod_actionable",
                    "proof_level": "prod-actionable",
                    "error": str(exc),
                    "api": _normalize_base(args.api_base),
                    "manual_execution_required": True,
                    "auto_order_enabled": False,
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
    symbol: str,
    query: str,
    horizon: str,
    timeout: float,
    allow_local_api_base: bool = False,
    proof_output: str | Path | None = None,
) -> dict[str, Any]:
    api = _normalize_base(api_base)
    _assert_public_https_api_base(api, allow_local_api_base=allow_local_api_base)
    _require_envelope_ok(_get_json(_join(api, "/api/system/health"), timeout=timeout, label="API health"), "API health")
    config = _require_envelope_ok(
        _get_json(_join(api, "/api/system/config"), timeout=timeout, label="API config"),
        "API config",
    )
    _assert_prod_config(config)

    run_started_at = datetime.now(timezone.utc)
    manual = _require_envelope_ok(
        _post_json(
            _join(api, "/api/runs/manual"),
            {"symbol": symbol, "query": query, "horizon": horizon, "alert_channel": "bark"},
            timeout=timeout,
            label="manual run",
        ),
        "manual run",
    )
    trace_id = _require_string(manual.get("trace_id"), "manual run trace_id")
    plan = _require_dict(manual.get("plan"), "manual run plan")
    if plan.get("manual_execution_required") is not True:
        raise HostedProdActionableSmokeError("manual run plan must keep manual_execution_required=true")

    detail = _require_envelope_ok(
        _get_json(_join(api, f"/api/runs/{quote(trace_id, safe='')}"), timeout=timeout, label="run detail"),
        "run detail",
    )
    _assert_run_level_evidence(detail, run_started_at=run_started_at)

    result = {
        "ok": True,
        "smoke_profile": "hosted_prod_actionable",
        "proof_level": "prod-actionable",
        "api": api,
        "trace_id": trace_id,
        "allowed": True,
        "decision_engine": "openai_compatible",
        "decision_final_input_mode": "legacy_prompt",
        "candidate_sidecar_mode": "disabled",
        "market_provider": "okx_public",
        "macro_event_provider": "no_active_event",
        "workflow_execution_mode": "legacy_baseline",
        "manual_execution_required": True,
        "auto_order_enabled": False,
        "notification_status": "sent",
        "llm_interaction_status": "ok",
        "market_evidence": "exchange_native_fresh_execution_fact",
        "hosted_runtime_only_not_prod_actionable": False,
    }
    if proof_output is not None:
        _write_proof_manifest(
            proof_output,
            api_base=api,
            config=config,
            detail=detail,
            horizon=horizon,
            query=query,
            result=result,
            run_started_at=run_started_at,
            symbol=symbol,
            trace_id=trace_id,
        )
    return result


def _assert_prod_config(config: dict[str, Any]) -> None:
    trading = _require_dict(config.get("trading"), "API config trading")
    if trading.get("manual_execution_required") is not True:
        raise HostedProdActionableSmokeError("production config requires manual_execution_required=true")
    if trading.get("auto_order_enabled") is not False:
        raise HostedProdActionableSmokeError("production config requires auto_order_enabled=false")

    decision = _dict(config.get("decision"))
    market = _dict(config.get("market_data"))
    notification = _dict(config.get("notification"))
    macro_event = _dict(config.get("macro_event"))
    workflow = _dict(config.get("workflow"))
    readiness = _dict(config.get("readiness"))
    prod_actionable = _dict(readiness.get("prod_actionable"))
    market_readiness = _dict(readiness.get("market_data"))

    expected = (
        (decision.get("engine"), "openai_compatible", "decision.engine"),
        (decision.get("final_input_mode"), "legacy_prompt", "decision.final_input_mode"),
        (decision.get("candidate_sidecar_mode"), "disabled", "decision.candidate_sidecar_mode"),
        (market.get("provider"), "okx_public", "market_data.provider"),
        (macro_event.get("provider"), "no_active_event", "macro_event.provider"),
        (workflow.get("execution_mode"), "legacy_baseline", "workflow.execution_mode"),
    )
    for actual, wanted, name in expected:
        if actual != wanted:
            raise HostedProdActionableSmokeError(f"production config requires {name}={wanted}")
    okx_base_url = str(market.get("okx_base_url") or "").strip()
    if okx_base_url and okx_base_url != "https://www.okx.com":
        raise HostedProdActionableSmokeError(
            "production config requires market_data.okx_base_url unset or https://www.okx.com"
        )
    if market_readiness.get("status") == "unsafe":
        raise HostedProdActionableSmokeError("production config requires readiness.market_data.status!=unsafe")
    if notification.get("enabled") is not True:
        raise HostedProdActionableSmokeError("production config requires notification.enabled=true")
    _assert_macro_event_metadata(macro_event, prod_actionable)
    if prod_actionable.get("status") != "ready" or prod_actionable.get("prod_actionable_ready") is not True:
        raise HostedProdActionableSmokeError("production config requires readiness.prod_actionable.status=ready")
    if prod_actionable.get("production_main_path_ready") is not True or _list(prod_actionable.get("main_path_blockers")):
        raise HostedProdActionableSmokeError(
            "production config requires production main path readiness with no blockers"
        )


def _assert_run_level_evidence(detail: dict[str, Any], *, run_started_at: datetime) -> None:
    trace = _require_dict(detail.get("trace"), "run detail trace")
    if trace.get("allowed") is not True:
        raise HostedProdActionableSmokeError("prod-actionable run requires trace.allowed=true")

    plan_run = _require_dict(detail.get("plan_run"), "run detail plan_run")
    parsed_plan = _dict(plan_run.get("parsed_plan"))
    if parsed_plan.get("manual_execution_required") is not True:
        raise HostedProdActionableSmokeError("prod-actionable run requires parsed_plan.manual_execution_required=true")
    verdict = _dict(plan_run.get("verdict"))
    if verdict.get("allowed") is not True:
        raise HostedProdActionableSmokeError("prod-actionable run requires verdict.allowed=true")

    audit = _dict(plan_run.get("agent_audit_view"))
    lineage = _dict(audit.get("input_lineage"))
    if lineage.get("production_final_input_mode") != "legacy_prompt":
        raise HostedProdActionableSmokeError("prod-actionable run requires production_final_input_mode=legacy_prompt")
    query_semantics = _dict(audit.get("query_semantics"))
    if query_semantics.get("drives_final_input") is not False:
        raise HostedProdActionableSmokeError("query_text must remain audit_note and not drive final input")

    llm_error = _real_llm_interaction_error(detail.get("llm_interactions"))
    if llm_error:
        raise HostedProdActionableSmokeError(llm_error)
    if not _has_exchange_native_execution_evidence(audit):
        raise HostedProdActionableSmokeError("prod-actionable run requires exchange-native fresh execution evidence")
    if not _has_sent_notification(detail, run_started_at=run_started_at):
        raise HostedProdActionableSmokeError("Bark notification must be sent for prod-actionable proof")


def _write_proof_manifest(
    path: str | Path,
    *,
    api_base: str,
    config: dict[str, Any],
    detail: dict[str, Any],
    horizon: str,
    query: str,
    result: dict[str, Any],
    run_started_at: datetime,
    symbol: str,
    trace_id: str,
) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": "2026-07-09.hosted-prod-actionable-proof.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_started_at": run_started_at.isoformat(),
        "smoke_profile": "hosted_prod_actionable",
        "proof_level": "prod-actionable",
        "api_base_url": api_base,
        "trace_id": trace_id,
        "symbol": symbol,
        "horizon": horizon,
        "query": query,
        "config_digest": _stable_digest(config),
        "run_detail_digest": _stable_digest(detail),
        "prod_actionable_proven": True,
        "real_outcome_proven": False,
        "does_not_prove": "hosted_real_outcome",
        "result_summary": result,
        "run_detail_summary": _run_detail_summary(detail, run_started_at=run_started_at),
    }
    output_path.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _stable_digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _run_detail_summary(detail: dict[str, Any], *, run_started_at: datetime) -> dict[str, Any]:
    trace = _dict(detail.get("trace"))
    plan_run = _dict(detail.get("plan_run"))
    parsed_plan = _dict(plan_run.get("parsed_plan"))
    verdict = _dict(plan_run.get("verdict"))
    audit = _dict(plan_run.get("agent_audit_view"))
    lineage = _dict(audit.get("input_lineage"))
    final_interaction = _final_real_llm_interaction(detail.get("llm_interactions"))
    bark_evidence = _sent_notification_evidence(detail, run_started_at=run_started_at)
    return {
        "allowed": trace.get("allowed") is True and verdict.get("allowed") is True,
        "trace_allowed": trace.get("allowed"),
        "verdict_allowed": verdict.get("allowed"),
        "manual_execution_required": parsed_plan.get("manual_execution_required"),
        "production_final_input_mode": lineage.get("production_final_input_mode"),
        "query_drives_final_input": _dict(audit.get("query_semantics")).get("drives_final_input"),
        "decision_final_provider": final_interaction.get("provider"),
        "decision_final_model": final_interaction.get("model"),
        "decision_final_status": final_interaction.get("status"),
        "exchange_native_fresh_evidence": _has_exchange_native_execution_evidence(audit),
        "bark_sent": bool(bark_evidence),
        "bark_evidence": bark_evidence,
    }


def _final_real_llm_interaction(value: Any) -> dict[str, Any]:
    for item in _list(value):
        interaction = _dict(item)
        if (
            interaction.get("component") == "decision.final"
            and interaction.get("provider") == "openai_compatible"
            and interaction.get("status") == "ok"
            and not _is_non_prod_model_name(str(interaction.get("model") or ""))
        ):
            return {
                "provider": interaction.get("provider"),
                "model": interaction.get("model"),
                "status": interaction.get("status"),
                "component": interaction.get("component"),
            }
    return {}


def _sent_notification_evidence(detail: dict[str, Any], *, run_started_at: datetime) -> dict[str, Any]:
    for item in _list(detail.get("notification_history")):
        row = _dict(item)
        timestamp = _parse_iso_datetime(str(row.get("sent_at") or row.get("created_at") or ""))
        status_code = row.get("status_code")
        if (
            row.get("channel") == "bark"
            and row.get("status") == "sent"
            and row.get("ok") is True
            and isinstance(status_code, int)
            and 200 <= status_code < 300
            and timestamp is not None
            and timestamp >= run_started_at
        ):
            return {
                "channel": row.get("channel"),
                "status": row.get("status"),
                "ok": row.get("ok"),
                "status_code": status_code,
                "created_at": row.get("created_at"),
                "sent_at": row.get("sent_at"),
            }
    return {}


def _assert_macro_event_metadata(macro_event: dict[str, Any], prod_actionable: dict[str, Any]) -> None:
    required = (
        (("operator_ref", "no_active_event_operator_ref"), "MACRO_EVENT_OPERATOR_REF"),
        (("confirmed_at", "no_active_event_confirmed_at"), "MACRO_EVENT_CONFIRMED_AT"),
        (("source_ref", "no_active_event_source_ref"), "MACRO_EVENT_SOURCE_REF"),
        (("assertion_horizon", "no_active_event_horizon"), "MACRO_EVENT_ASSERTION_HORIZON"),
        (("valid_until", "no_active_event_valid_until"), "MACRO_EVENT_VALID_UNTIL"),
    )
    missing = [env_name for keys, env_name in required if not _first_present_string(macro_event, keys)]
    readiness_missing = [str(item) for item in _list(prod_actionable.get("missing_event_assertion_metadata")) if str(item)]
    if missing or readiness_missing:
        combined = sorted(set(missing + readiness_missing))
        raise HostedProdActionableSmokeError(
            "production config requires complete macro_event metadata: " + ", ".join(combined)
        )
    if (
        "event_assertion_metadata_complete" in prod_actionable
        and prod_actionable.get("event_assertion_metadata_complete") is not True
    ):
        raise HostedProdActionableSmokeError("production config requires complete macro_event metadata")
    _assert_unexpired_macro_event_valid_until(_first_present_string(macro_event, ("valid_until", "no_active_event_valid_until")))


def _assert_unexpired_macro_event_valid_until(value: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HostedProdActionableSmokeError(
            "production config requires unexpired macro_event valid_until with timezone"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise HostedProdActionableSmokeError(
            "production config requires unexpired macro_event valid_until with timezone"
        )
    if parsed <= datetime.now(timezone.utc):
        raise HostedProdActionableSmokeError("production config requires unexpired macro_event valid_until")


def _real_llm_interaction_error(value: Any) -> str | None:
    saw_final_openai = False
    mock_models: list[str] = []
    for item in _list(value):
        interaction = _dict(item)
        if interaction.get("component") != "decision.final" or interaction.get("provider") != "openai_compatible":
            continue
        saw_final_openai = True
        if interaction.get("status") != "ok":
            continue
        model = str(interaction.get("model") or "")
        if _is_non_prod_model_name(model):
            mock_models.append(model)
            continue
        return None
    if mock_models:
        return "prod-actionable run requires decision.final real non-mock model"
    if saw_final_openai:
        return "prod-actionable run requires decision.final OpenAI-compatible LLM status=ok"
    return "prod-actionable run requires decision.final OpenAI-compatible LLM evidence"


def _is_non_prod_model_name(model: str) -> bool:
    normalized = model.strip().lower()
    if not normalized:
        return True
    tokens = ("mock", "fixture", "fake", "stub", "test", "local")
    return any(
        normalized.startswith(token) or re.search(rf"(^|[^a-z0-9]){re.escape(token)}([^a-z0-9]|$)", normalized)
        for token in tokens
    )


def _has_exchange_native_execution_evidence(audit: dict[str, Any]) -> bool:
    for source in _list(audit.get("evidence_sources")):
        item = _dict(source)
        if (
            item.get("source_type") == "exchange_native"
            and item.get("freshness_status") == "fresh"
            and item.get("can_satisfy_execution_fact") is True
        ):
            return True
    for row in _list(audit.get("source_freshness")):
        item = _dict(row)
        if (
            item.get("source_type") == "exchange_native"
            and item.get("freshness_status") == "fresh"
            and int(item.get("can_satisfy_execution_fact_count") or 0) > 0
        ):
            return True
    return False


def _has_sent_notification(detail: dict[str, Any], *, run_started_at: datetime) -> bool:
    for item in _list(detail.get("notification_history")):
        row = _dict(item)
        timestamp = _parse_iso_datetime(str(row.get("sent_at") or row.get("created_at") or ""))
        status_code = row.get("status_code")
        if (
            row.get("channel") == "bark"
            and row.get("status") == "sent"
            and row.get("ok") is True
            and isinstance(status_code, int)
            and 200 <= status_code < 300
            and timestamp is not None
            and timestamp >= run_started_at
        ):
            return True
    return False


def _parse_iso_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _normalize_base(value: str) -> str:
    return value.rstrip("/")


def _assert_public_https_api_base(api_base: str, *, allow_local_api_base: bool) -> None:
    if allow_local_api_base:
        return
    parsed = urlparse(api_base)
    hostname = parsed.hostname or ""
    if parsed.scheme != "https" or not hostname or _is_local_or_private_hostname(hostname):
        raise HostedProdActionableSmokeError(
            "hosted prod-actionable proof requires a public HTTPS API base"
        )
    if _is_ip_literal(hostname):
        return
    addresses = _hostname_addresses(hostname)
    if not addresses or any(_is_local_or_private_hostname(address) for address in addresses):
        raise HostedProdActionableSmokeError(
            "hosted prod-actionable proof requires a public HTTPS API base"
        )


def _is_local_or_private_hostname(hostname: str) -> bool:
    normalized = hostname.strip().lower().rstrip(".")
    if normalized in {"localhost", "0.0.0.0"} or normalized.endswith(".localhost"):
        return True
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return False
    return (
        address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_reserved
        or address.is_unspecified
    )


def _is_ip_literal(hostname: str) -> bool:
    try:
        ipaddress.ip_address(hostname.strip().lower().rstrip("."))
    except ValueError:
        return False
    return True


def _hostname_addresses(hostname: str) -> list[str]:
    try:
        return sorted({info[4][0] for info in socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)})
    except OSError as exc:
        raise HostedProdActionableSmokeError(
            "hosted prod-actionable proof requires a resolvable public HTTPS API base"
        ) from exc


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
        raise HostedProdActionableSmokeError(f"{label} returned HTTP {exc.code}") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise HostedProdActionableSmokeError(f"{label} request failed: {exc}") from exc
    if not isinstance(payload, dict):
        raise HostedProdActionableSmokeError(f"{label} returned non-object JSON")
    return payload


def _require_envelope_ok(payload: dict[str, Any], label: str) -> dict[str, Any]:
    if payload.get("ok") is not True:
        raise HostedProdActionableSmokeError(f"{label} returned ok=false")
    return _require_dict(payload.get("data"), f"{label} data")


def _require_dict(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise HostedProdActionableSmokeError(f"{label} missing object")
    return value


def _require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise HostedProdActionableSmokeError(f"{label} missing string")
    return value


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _first_present_string(mapping: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
