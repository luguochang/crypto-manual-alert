from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_API_BASE = "http://127.0.0.1:8010"
DEFAULT_COMPOSE_PROJECT = "crypto-alert-prod"
DEFAULT_CONFIGS = ("config/default.yaml", "config/prod.yaml", "config/staging.yaml")
DEFAULT_LIMIT = 50

Runner = Callable[..., subprocess.CompletedProcess[str]]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run collect-outcomes for a hosted/manual-alert environment, then verify the "
            "hosted API exposes at least one real exchange-native matured scorable outcome. "
            "This proves real-outcome evidence only; it is not prod-actionable alert proof."
        )
    )
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--collector-mode", choices=("docker-compose", "local-cli"), default="docker-compose")
    parser.add_argument("--compose-project", default=DEFAULT_COMPOSE_PROJECT)
    parser.add_argument("--config", action="append", dest="configs", default=None)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--evaluation-target", default=None)
    parser.add_argument("--min-count", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--python-bin", default=sys.executable)
    parser.add_argument(
        "--same-host-data-dir-confirmed",
        action="store_true",
        help=(
            "Required. Confirms the collector command writes to the same DATA_DIR/OutcomeStore "
            "that the hosted API reads. Without this, local collection could be mistaken for "
            "hosted production evidence."
        ),
    )
    parser.add_argument(
        "--allow-collection-errors",
        action="store_true",
        help="Allow collect-outcomes JSON to include an errors list and still continue to evidence verification.",
    )
    parser.add_argument(
        "--proof-output",
        help=(
            "Optional path for a machine-readable hosted real-outcome proof manifest. "
            "Written only after collection and post-collection evidence linkage pass."
        ),
    )
    args = parser.parse_args(argv)

    result = run_smoke(
        api_base=args.api_base,
        collector_mode=args.collector_mode,
        compose_project=args.compose_project,
        configs=args.configs,
        limit=args.limit,
        symbol=args.symbol,
        evaluation_target=args.evaluation_target,
        min_count=args.min_count,
        timeout=args.timeout,
        python_bin=args.python_bin,
        same_host_data_dir_confirmed=args.same_host_data_dir_confirmed,
        allow_collection_errors=args.allow_collection_errors,
        proof_output=args.proof_output,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    if result.get("ok") is True:
        return 0
    if result.get("stage") == "operator_confirmation":
        return 2
    return 1


def run_smoke(
    *,
    api_base: str,
    collector_mode: str = "docker-compose",
    compose_project: str = DEFAULT_COMPOSE_PROJECT,
    configs: Sequence[str] | None = None,
    limit: int = DEFAULT_LIMIT,
    symbol: str | None = None,
    evaluation_target: str | None = None,
    min_count: int = 1,
    timeout: float = 10.0,
    python_bin: str = sys.executable,
    same_host_data_dir_confirmed: bool = False,
    allow_collection_errors: bool = False,
    api_config: dict[str, Any] | None = None,
    runner: Runner = subprocess.run,
    proof_output: str | Path | None = None,
) -> dict[str, Any]:
    api = _normalize_base(api_base)
    if not same_host_data_dir_confirmed:
        return {
            "ok": False,
            "stage": "operator_confirmation",
            "smoke_profile": "hosted_real_outcome_collection",
            "proof_level": "real-outcome",
            "api": api,
            "error": "same_host_data_dir_confirmation_required",
            "exit_semantics": "operator_confirmation_required",
            "real_exchange_native_matured_outcome_proven": False,
            "prod_actionable_alert_proven": False,
        }
    if limit < 1:
        return _static_failure(api=api, stage="argument_validation", error="limit_must_be_positive")
    if min_count < 1:
        return _static_failure(api=api, stage="argument_validation", error="min_count_must_be_positive")

    config = api_config
    if config is None:
        try:
            config = _fetch_api_config(api, timeout=timeout)
        except RuntimeError as exc:
            result = _static_failure(api=api, stage="api_config_preflight", error=str(exc))
            result["api_config_preflight"] = "failed"
            return result
    config_error = _outcome_config_error(config)
    if config_error:
        return {
            "ok": False,
            "stage": "api_config_preflight",
            "smoke_profile": "hosted_real_outcome_collection",
            "proof_level": "real-outcome",
            "api": api,
            "error": config_error,
            "api_config_preflight": "failed",
            "real_exchange_native_matured_outcome_proven": False,
            "prod_actionable_alert_proven": False,
        }

    gate_started_at = _utc_now()
    evidence_command = _evidence_command(
        api_base=api,
        evaluation_target=evaluation_target,
        symbol=symbol,
        collected_after=gate_started_at,
        min_count=min_count,
        timeout=timeout,
        python_bin=python_bin,
    )
    before_evidence = _run_command(evidence_command, runner=runner, stage="real_outcome_evidence_before")
    before_payload = _json_or_text(before_evidence.stdout)
    before_refs: dict[tuple[str, str, str, str], tuple[str, str | None]] = {}
    if before_evidence.returncode == 0:
        before_contract_error = _evidence_contract_error(before_payload)
        if before_contract_error:
            return _invalid_contract_failure(
                api=api,
                stage="real_outcome_evidence_before_invalid_contract",
                error=before_contract_error,
                payload=before_payload,
                allow_collection_errors=allow_collection_errors,
            )
        before_refs = _matched_ref_map(before_payload)

    config_paths = tuple(configs or DEFAULT_CONFIGS)
    collect_command = _collect_command(
        collector_mode=collector_mode,
        compose_project=compose_project,
        configs=config_paths,
        limit=limit,
        symbol=symbol,
        python_bin=python_bin,
    )
    collect = _run_command(collect_command, runner=runner, stage="collect_outcomes")
    collect_payload = _json_or_text(collect.stdout)
    if collect.returncode != 0:
        return _command_failure(
            api=api,
            stage="collect_outcomes",
            completed=collect,
            parsed_stdout=collect_payload,
        )
    collect_contract_error = _collect_contract_error(collect_payload)
    if collect_contract_error:
        return _invalid_contract_failure(
            api=api,
            stage="collect_outcomes_invalid_contract",
            error=collect_contract_error,
            payload=collect_payload,
            allow_collection_errors=allow_collection_errors,
        )
    collected_ref_keys = _collected_ref_keys(collect_payload)
    collection_errors = _collection_errors(collect_payload)
    if collection_errors and not allow_collection_errors:
        return {
            "ok": False,
            "stage": "collect_outcomes_errors",
            "smoke_profile": "hosted_real_outcome_collection",
            "proof_level": "real-outcome",
            "api": api,
            "collect_outcomes": collect_payload,
            "collection_errors": collection_errors,
            "collection_errors_allowed": False,
            "error": "collect_outcomes_reported_errors",
            "real_exchange_native_matured_outcome_proven": False,
            "prod_actionable_alert_proven": False,
        }
    collected_count = _collected_count(collect_payload)
    if collected_count < 1:
        return {
            "ok": False,
            "stage": "no_new_outcome_collected",
            "smoke_profile": "hosted_real_outcome_collection",
            "proof_level": "real-outcome",
            "api": api,
            "collect_outcomes": collect_payload,
            "collection_errors_allowed": allow_collection_errors,
            "error": "collect_outcomes_reported_collected_zero",
            "real_exchange_native_matured_outcome_proven": False,
            "prod_actionable_alert_proven": False,
        }

    evidence = _run_command(evidence_command, runner=runner, stage="real_outcome_evidence")
    evidence_payload = _json_or_text(evidence.stdout)
    if evidence.returncode != 0:
        return _command_failure(
            api=api,
            stage="real_outcome_evidence",
            completed=evidence,
            parsed_stdout=evidence_payload,
            collect_payload=collect_payload,
            allow_collection_errors=allow_collection_errors,
        )
    evidence_contract_error = _evidence_contract_error(evidence_payload)
    if evidence_contract_error:
        return _invalid_contract_failure(
            api=api,
            stage="real_outcome_evidence_invalid_contract",
            error=evidence_contract_error,
            payload=evidence_payload,
            collect_payload=collect_payload,
            allow_collection_errors=allow_collection_errors,
        )

    new_or_updated_ref_details = _new_or_updated_ref_details(
        before_refs,
        _matched_ref_map(evidence_payload),
        gate_started_at,
        allowed_keys=collected_ref_keys,
    )
    if not new_or_updated_ref_details:
        return {
            "ok": False,
            "stage": "real_outcome_evidence_not_linked_to_collection",
            "smoke_profile": "hosted_real_outcome_collection",
            "proof_level": "real-outcome",
            "api": api,
            "gate_started_at": gate_started_at.isoformat(),
            "collect_outcomes": collect_payload,
            "real_outcome_evidence_before": before_payload,
            "real_outcome_evidence": evidence_payload,
            "collection_errors_allowed": allow_collection_errors,
            "new_refs_verified": False,
            "error": "post_collection_evidence_did_not_add_or_update_refs_collected_by_this_run",
            "real_exchange_native_matured_outcome_proven": False,
            "prod_actionable_alert_proven": False,
        }
    new_or_updated_refs = sorted({item["decision_ref"] for item in new_or_updated_ref_details})

    result = {
        "ok": True,
        "stage": "complete",
        "smoke_profile": "hosted_real_outcome_collection",
        "proof_level": "real-outcome",
        "api": api,
        "collector_mode": collector_mode,
        "same_host_data_dir_confirmed": True,
        "api_config_preflight": "production_outcome_config_ready",
        "gate_started_at": gate_started_at.isoformat(),
        "collect_outcomes": collect_payload,
        "real_outcome_evidence_before": before_payload,
        "real_outcome_evidence": evidence_payload,
        "collection_errors_allowed": allow_collection_errors,
        "new_refs_verified": True,
        "new_or_updated_refs": new_or_updated_refs,
        "new_or_updated_ref_details": new_or_updated_ref_details,
        "real_exchange_native_matured_outcome_proven": True,
        "prod_actionable_alert_proven": False,
    }
    if proof_output is not None:
        _write_proof_manifest(
            proof_output,
            api_base=api,
            collect_payload=collect_payload,
            config=config,
            evidence_payload=evidence_payload,
            gate_started_at=gate_started_at,
            result=result,
        )
    return result


def _collect_command(
    *,
    collector_mode: str,
    compose_project: str,
    configs: Sequence[str],
    limit: int,
    symbol: str | None,
    python_bin: str,
) -> list[str]:
    config_args = _config_args(configs)
    collect_args = ["collect-outcomes", "--limit", str(limit)]
    if symbol:
        collect_args.extend(["--symbol", symbol])
    if collector_mode == "docker-compose":
        return [
            "docker",
            "compose",
            "-p",
            compose_project,
            "run",
            "--rm",
            "manual-alert",
            "crypto-alert",
            *config_args,
            *collect_args,
        ]
    if collector_mode == "local-cli":
        return [python_bin, "-m", "crypto_manual_alert.cli", *config_args, *collect_args]
    raise ValueError(f"unsupported collector_mode: {collector_mode}")


def _write_proof_manifest(
    path: str | Path,
    *,
    api_base: str,
    collect_payload: Any,
    config: dict[str, Any],
    evidence_payload: Any,
    gate_started_at: datetime,
    result: dict[str, Any],
) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": "2026-07-09.hosted-real-outcome-proof.v1",
        "generated_at": _utc_now().isoformat(),
        "gate_started_at": gate_started_at.isoformat(),
        "smoke_profile": "hosted_real_outcome_collection",
        "proof_level": "real-outcome",
        "api_base_url": api_base,
        "config_digest": _stable_digest(config),
        "collect_outcomes_digest": _stable_digest(collect_payload),
        "real_outcome_evidence_digest": _stable_digest(evidence_payload),
        "real_exchange_native_matured_outcome_proven": True,
        "prod_actionable_alert_proven": False,
        "does_not_prove": "hosted_prod_actionable",
        "same_host_data_dir_confirmed": result.get("same_host_data_dir_confirmed"),
        "collection_errors_allowed": result.get("collection_errors_allowed"),
        "new_refs_verified": result.get("new_refs_verified"),
        "new_or_updated_refs": result.get("new_or_updated_refs"),
        "new_or_updated_ref_details": result.get("new_or_updated_ref_details"),
        "outcome_summary": _outcome_summary(evidence_payload),
    }
    output_path.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _stable_digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _outcome_summary(evidence_payload: Any) -> dict[str, Any]:
    matched_value = _dict(evidence_payload).get("matched")
    matched = matched_value if isinstance(matched_value, list) else []
    refs = sorted(
        str(item.get("decision_ref"))
        for item in matched
        if isinstance(item, dict) and isinstance(item.get("decision_ref"), str) and item.get("decision_ref")
    )
    return {
        "matched_count": int(_dict(evidence_payload).get("matched_count") or len(refs)),
        "matched_refs": refs,
        "real_exchange_native_matured_outcome_proven": _dict(evidence_payload).get(
            "real_exchange_native_matured_outcome_proven"
        ),
        "prod_actionable_alert_proven": _dict(evidence_payload).get("prod_actionable_alert_proven"),
    }


def _evidence_command(
    *,
    api_base: str,
    evaluation_target: str | None,
    symbol: str | None,
    collected_after: datetime,
    min_count: int,
    timeout: float,
    python_bin: str,
) -> list[str]:
    command = [
        python_bin,
        str(ROOT / "tools" / "deployment" / "smoke_real_outcome_evidence.py"),
        "--api-base",
        api_base,
        "--min-count",
        str(min_count),
        "--timeout",
        str(timeout),
        "--collected-after",
        collected_after.isoformat(),
    ]
    if symbol:
        command.extend(["--symbol", symbol])
    if evaluation_target:
        command.extend(["--evaluation-target", evaluation_target])
    return command


def _config_args(configs: Sequence[str]) -> list[str]:
    args: list[str] = []
    for path in configs:
        args.extend(["--config", path])
    return args


def _run_command(command: Sequence[str], *, runner: Runner, stage: str) -> subprocess.CompletedProcess[str]:
    try:
        return runner(command, capture_output=True, text=True, check=False)
    except OSError as exc:
        return subprocess.CompletedProcess(list(command), 1, stdout="", stderr=f"{stage}: {exc}")


def _fetch_api_config(api: str, *, timeout: float) -> dict[str, Any]:
    request = Request(_join(api, "/api/system/config"), headers={"accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"API config returned HTTP {exc.code}") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"API config request failed: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        raise RuntimeError("API config returned ok=false")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("API config data is missing or not an object")
    return data


def _outcome_config_error(config: dict[str, Any]) -> str | None:
    trading = _dict(config.get("trading"))
    if trading.get("manual_execution_required") is not True:
        return "production outcome config requires manual_execution_required=true"
    if trading.get("auto_order_enabled") is not False:
        return "production outcome config requires auto_order_enabled=false"

    decision = _dict(config.get("decision"))
    expected = (
        (decision.get("engine"), "openai_compatible", "decision.engine"),
        (decision.get("final_input_mode"), "legacy_prompt", "decision.final_input_mode"),
        (decision.get("candidate_sidecar_mode"), "disabled", "decision.candidate_sidecar_mode"),
        (_dict(config.get("market_data")).get("provider"), "okx_public", "market_data.provider"),
        (_dict(config.get("workflow")).get("execution_mode"), "legacy_baseline", "workflow.execution_mode"),
    )
    for actual, wanted, name in expected:
        if actual != wanted:
            return f"production outcome config requires {name}={wanted}"

    market = _dict(config.get("market_data"))
    okx_base = str(market.get("okx_base_url") or "").strip()
    if okx_base and okx_base != "https://www.okx.com":
        return "production outcome config requires market_data.okx_base_url unset or https://www.okx.com"

    readiness = _dict(config.get("readiness"))
    market_readiness = _dict(readiness.get("market_data"))
    if market_readiness.get("status") == "unsafe":
        return "production outcome config requires readiness.market_data.status!=unsafe"
    return None


def _command_failure(
    *,
    api: str,
    stage: str,
    completed: subprocess.CompletedProcess[str],
    parsed_stdout: Any,
    collect_payload: Any | None = None,
    allow_collection_errors: bool = False,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": False,
        "stage": stage,
        "smoke_profile": "hosted_real_outcome_collection",
        "proof_level": "real-outcome",
        "api": api,
        "returncode": completed.returncode,
        "stdout": parsed_stdout,
        "stderr": completed.stderr,
        "collection_errors_allowed": allow_collection_errors,
        "real_exchange_native_matured_outcome_proven": False,
        "prod_actionable_alert_proven": False,
    }
    if collect_payload is not None:
        result["collect_outcomes"] = collect_payload
    return result


def _static_failure(*, api: str, stage: str, error: str) -> dict[str, Any]:
    return {
        "ok": False,
        "stage": stage,
        "smoke_profile": "hosted_real_outcome_collection",
        "proof_level": "real-outcome",
        "api": api,
        "error": error,
        "real_exchange_native_matured_outcome_proven": False,
        "prod_actionable_alert_proven": False,
    }


def _invalid_contract_failure(
    *,
    api: str,
    stage: str,
    error: str,
    payload: Any,
    collect_payload: Any | None = None,
    allow_collection_errors: bool,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": False,
        "stage": stage,
        "smoke_profile": "hosted_real_outcome_collection",
        "proof_level": "real-outcome",
        "api": api,
        "error": error,
        "stdout": payload,
        "collection_errors_allowed": allow_collection_errors,
        "real_exchange_native_matured_outcome_proven": False,
        "prod_actionable_alert_proven": False,
    }
    if collect_payload is not None:
        result["collect_outcomes"] = collect_payload
    return result


def _collect_contract_error(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return "collect_outcomes_stdout_must_be_json_object"
    if not isinstance(payload.get("collected"), int):
        return "collect_outcomes_collected_must_be_integer"
    if int(payload.get("collected") or 0) > 0:
        refs = payload.get("collected_refs")
        if not isinstance(refs, list) or not refs:
            return "collect_outcomes_collected_refs_must_be_non_empty_list"
        for item in refs:
            error = _ref_contract_error(item, prefix="collect_outcomes_collected_refs")
            if error:
                return error
    return None


def _evidence_contract_error(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return "real_outcome_evidence_stdout_must_be_json_object"
    expected = {
        "ok": True,
        "smoke_profile": "real_outcome_evidence",
        "real_exchange_native_matured_outcome_proven": True,
        "prod_actionable_alert_proven": False,
    }
    for key, wanted in expected.items():
        if payload.get(key) != wanted:
            return f"real_outcome_evidence_requires_{key}={wanted!r}"
    matched = payload.get("matched")
    if not isinstance(matched, list) or not matched:
        return "real_outcome_evidence_matched_must_be_non_empty_list"
    if int(payload.get("matched_count") or 0) < 1:
        return "real_outcome_evidence_matched_count_must_be_positive"
    for item in matched:
        error = _ref_contract_error(item, prefix="real_outcome_evidence_matched")
        if error:
            return error
    return None


def _ref_contract_error(item: Any, *, prefix: str) -> str | None:
    if not isinstance(item, dict):
        return f"{prefix}_must_contain_objects"
    for key in ("decision_ref", "evaluation_target", "symbol", "window_name"):
        value = item.get(key)
        if not isinstance(value, str) or not value.strip():
            return f"{prefix}_{key}_must_be_non_empty_string"
    collected_at = item.get("collected_at")
    if not isinstance(collected_at, str) or not collected_at.strip():
        return f"{prefix}_collected_at_must_be_timezone_aware"
    if _parse_datetime(collected_at) is None:
        return f"{prefix}_collected_at_must_be_timezone_aware"
    return None


def _collection_errors(payload: Any) -> list[Any]:
    if not isinstance(payload, dict):
        return []
    errors = payload.get("errors")
    return errors if isinstance(errors, list) and errors else []


def _collected_count(payload: dict[str, Any]) -> int:
    return int(payload["collected"])


def _collected_ref_keys(payload: Any) -> set[tuple[str, str, str, str]]:
    if not isinstance(payload, dict):
        return set()
    return {
        key
        for item in payload.get("collected_refs") or []
        if isinstance(item, dict)
        for key in [_ref_key(item)]
        if key is not None
    }


def _matched_ref_map(payload: Any) -> dict[tuple[str, str, str, str], tuple[str, str | None]]:
    if not isinstance(payload, dict):
        return {}
    refs: dict[tuple[str, str, str, str], tuple[str, str | None]] = {}
    for item in payload.get("matched") or []:
        if not isinstance(item, dict):
            continue
        key = _ref_key(item)
        if key is not None:
            collected_at = item.get("collected_at")
            decision_ref = str(item.get("decision_ref"))
            refs[key] = (decision_ref, collected_at if isinstance(collected_at, str) and collected_at else None)
    return refs


def _ref_key(item: dict[str, Any]) -> tuple[str, str, str, str] | None:
    parts = (
        item.get("decision_ref"),
        item.get("evaluation_target"),
        item.get("symbol"),
        item.get("window_name"),
    )
    if not all(isinstance(part, str) and part.strip() for part in parts):
        return None
    return tuple(str(part).strip() for part in parts)  # type: ignore[return-value]


def _new_or_updated_ref_details(
    before_refs: dict[tuple[str, str, str, str], tuple[str, str | None]],
    after_refs: dict[tuple[str, str, str, str], tuple[str, str | None]],
    gate_started_at: datetime,
    *,
    allowed_keys: set[tuple[str, str, str, str]],
) -> list[dict[str, str]]:
    verified: list[dict[str, str]] = []
    for key, (decision_ref, collected_at) in after_refs.items():
        if key not in allowed_keys:
            continue
        after_dt = _parse_datetime(collected_at)
        if key not in before_refs:
            if after_dt is not None and after_dt >= gate_started_at:
                verified.append(_ref_detail(key, collected_at=collected_at))
            continue
        before_dt = _parse_datetime(before_refs.get(key, ("", None))[1])
        if after_dt is not None and after_dt >= gate_started_at and (before_dt is None or after_dt > before_dt):
            verified.append(_ref_detail(key, collected_at=collected_at))
    return sorted(
        verified,
        key=lambda item: (
            item["decision_ref"],
            item["evaluation_target"],
            item["symbol"],
            item["window_name"],
            item.get("collected_at", ""),
        ),
    )


def _ref_detail(key: tuple[str, str, str, str], *, collected_at: str | None) -> dict[str, str]:
    detail = {
        "decision_ref": key[0],
        "evaluation_target": key[1],
        "symbol": key[2],
        "window_name": key[3],
    }
    if collected_at:
        detail["collected_at"] = collected_at
    return detail


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _json_or_text(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _normalize_base(value: str) -> str:
    return value.rstrip("/")


def _join(base: str, path: str) -> str:
    return urljoin(f"{base}/", path.lstrip("/"))


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
