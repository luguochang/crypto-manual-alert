from __future__ import annotations

import importlib.util
import json
import subprocess
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "deployment" / "smoke_hosted_real_outcome_collection.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("smoke_hosted_real_outcome_collection", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _prod_outcome_config() -> dict[str, object]:
    return {
        "trading": {"manual_execution_required": True, "auto_order_enabled": False},
        "decision": {
            "engine": "openai_compatible",
            "final_input_mode": "legacy_prompt",
            "candidate_sidecar_mode": "disabled",
        },
        "market_data": {"provider": "okx_public", "okx_base_url": "https://www.okx.com"},
        "workflow": {"execution_mode": "legacy_baseline"},
        "readiness": {
            "market_data": {"status": "ready", "provider": "okx_public"},
            "trading_safety": {"status": "ready"},
        },
    }


def _run_smoke(module, *, runner, api_config: dict[str, object] | None = None, **kwargs):
    return module.run_smoke(
        api_base="http://127.0.0.1:8010",
        same_host_data_dir_confirmed=True,
        api_config=api_config or _prod_outcome_config(),
        runner=runner,
        **kwargs,
    )


class _Handler(BaseHTTPRequestHandler):
    routes: dict[tuple[str, str], tuple[int, str, Any]] = {}
    calls: list[tuple[str, str]] = []

    def do_GET(self) -> None:
        self.calls.append(("GET", self.path))
        status, content_type, body = self.routes.get(
            ("GET", self.path),
            (404, "application/json", {"ok": False, "error": {"code": "not_found"}}),
        )
        encoded = body.encode("utf-8") if isinstance(body, str) else json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: object) -> None:
        return


def _start_server(routes: dict[tuple[str, str], tuple[int, str, Any]]):
    class Handler(_Handler):
        pass

    Handler.routes = routes
    Handler.calls = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, Handler


def _base_url(server: ThreadingHTTPServer) -> str:
    host, port = server.server_address
    return f"http://{host}:{port}"


class _FakeRunner:
    def __init__(
        self,
        *,
        collect_returncode: int = 0,
        collect_stdout: str = (
            '{"collected": 1, "skipped": 0, "limit": 50, '
            '"collected_refs": [{"decision_ref": "trace-real-1:legacy_final", '
            '"evaluation_target": "legacy_final", "symbol": "ETH-USDT-SWAP", '
            '"window_name": "ETH-USDT-SWAP:21600s", '
            '"collected_at": "2026-07-09T00:05:00+00:00"}]}'
        ),
        collect_stderr: str = "",
        pre_evidence_returncode: int = 1,
        pre_evidence_stdout: str = (
            '{"ok": false, "smoke_profile": "real_outcome_evidence", '
            '"real_exchange_native_matured_outcome_proven": false, '
            '"prod_actionable_alert_proven": false}'
        ),
        evidence_returncode: int = 0,
        evidence_stdout: str | None = None,
        evidence_stderr: str = "",
    ) -> None:
        self.commands: list[list[str]] = []
        self.collect_returncode = collect_returncode
        self.collect_stdout = collect_stdout
        self.collect_stderr = collect_stderr
        self.pre_evidence_returncode = pre_evidence_returncode
        self.pre_evidence_stdout = pre_evidence_stdout
        self.evidence_returncode = evidence_returncode
        collected_at = (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()
        self.evidence_stdout = evidence_stdout or json.dumps(
            {
                "ok": True,
                "smoke_profile": "real_outcome_evidence",
                "matched_count": 1,
                "matched": [
                    {
                        "decision_ref": "trace-real-1:legacy_final",
                        "evaluation_target": "legacy_final",
                        "symbol": "ETH-USDT-SWAP",
                        "window_name": "ETH-USDT-SWAP:21600s",
                        "collected_at": collected_at,
                    }
                ],
                "real_exchange_native_matured_outcome_proven": True,
                "prod_actionable_alert_proven": False,
            }
        )
        self.evidence_stderr = evidence_stderr
        self._evidence_calls = 0

    def __call__(self, command, **kwargs):
        cmd = list(command)
        self.commands.append(cmd)
        joined = " ".join(cmd)
        if "collect-outcomes" in joined:
            return subprocess.CompletedProcess(
                cmd,
                self.collect_returncode,
                stdout=self.collect_stdout,
                stderr=self.collect_stderr,
            )
        if "smoke_real_outcome_evidence.py" in joined:
            self._evidence_calls += 1
            if self._evidence_calls == 1:
                return subprocess.CompletedProcess(
                    cmd,
                    self.pre_evidence_returncode,
                    stdout=self.pre_evidence_stdout,
                    stderr="",
                )
            return subprocess.CompletedProcess(
                cmd,
                self.evidence_returncode,
                stdout=self.evidence_stdout,
                stderr=self.evidence_stderr,
            )
        raise AssertionError(f"unexpected command: {cmd}")


def test_hosted_real_outcome_collection_runs_compose_collector_then_evidence_gate():
    module = _load_module()
    runner = _FakeRunner()

    result = _run_smoke(
        module,
        runner=runner,
        symbol="ETH-USDT-SWAP",
        limit=50,
        min_count=1,
    )

    assert result["ok"] is True
    assert result["smoke_profile"] == "hosted_real_outcome_collection"
    assert result["proof_level"] == "real-outcome"
    assert result["real_exchange_native_matured_outcome_proven"] is True
    assert result["prod_actionable_alert_proven"] is False

    collect_command = runner.commands[1]
    assert collect_command[:7] == [
        "docker",
        "compose",
        "-p",
        "crypto-alert-prod",
        "run",
        "--rm",
        "manual-alert",
    ]
    assert collect_command[7:13] == [
        "crypto-alert",
        "--config",
        "config/default.yaml",
        "--config",
        "config/prod.yaml",
        "--config",
    ]
    assert "config/staging.yaml" in collect_command
    assert collect_command[-5:] == ["collect-outcomes", "--limit", "50", "--symbol", "ETH-USDT-SWAP"]

    evidence_command = runner.commands[2]
    assert "tools/deployment/smoke_real_outcome_evidence.py" in " ".join(evidence_command)
    assert "--api-base" in evidence_command
    assert "http://127.0.0.1:8010" in evidence_command
    assert "--symbol" in evidence_command
    assert "ETH-USDT-SWAP" in evidence_command
    assert "--collected-after" in evidence_command
    collected_after_index = evidence_command.index("--collected-after") + 1
    assert datetime.fromisoformat(evidence_command[collected_after_index])
    assert "--min-count" in evidence_command
    assert "1" in evidence_command
    assert result["new_refs_verified"] is True
    assert result["new_or_updated_refs"] == ["trace-real-1:legacy_final"]
    assert result["new_or_updated_ref_details"] == [
        {
            "decision_ref": "trace-real-1:legacy_final",
            "evaluation_target": "legacy_final",
            "symbol": "ETH-USDT-SWAP",
            "window_name": "ETH-USDT-SWAP:21600s",
            "collected_at": json.loads(runner.evidence_stdout)["matched"][0]["collected_at"],
        }
    ]


def test_hosted_real_outcome_collection_can_write_proof_manifest(tmp_path):
    module = _load_module()
    runner = _FakeRunner()
    proof_path = tmp_path / "hosted-real-outcome-proof.json"

    result = _run_smoke(
        module,
        runner=runner,
        symbol="ETH-USDT-SWAP",
        proof_output=proof_path,
    )

    assert result["ok"] is True
    manifest = json.loads(proof_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "2026-07-09.hosted-real-outcome-proof.v1"
    assert manifest["smoke_profile"] == "hosted_real_outcome_collection"
    assert manifest["proof_level"] == "real-outcome"
    assert manifest["api_base_url"] == "http://127.0.0.1:8010"
    assert manifest["real_exchange_native_matured_outcome_proven"] is True
    assert manifest["prod_actionable_alert_proven"] is False
    assert manifest["does_not_prove"] == "hosted_prod_actionable"
    assert manifest["new_refs_verified"] is True
    assert manifest["new_or_updated_refs"] == ["trace-real-1:legacy_final"]
    assert manifest["new_or_updated_ref_details"] == [
        {
            "decision_ref": "trace-real-1:legacy_final",
            "evaluation_target": "legacy_final",
            "symbol": "ETH-USDT-SWAP",
            "window_name": "ETH-USDT-SWAP:21600s",
            "collected_at": json.loads(runner.evidence_stdout)["matched"][0]["collected_at"],
        }
    ]
    assert manifest["config_digest"]
    assert manifest["collect_outcomes_digest"]
    assert manifest["real_outcome_evidence_digest"]
    assert manifest["outcome_summary"]["matched_count"] == 1
    assert manifest["outcome_summary"]["matched_refs"] == ["trace-real-1:legacy_final"]


def test_hosted_real_outcome_collection_requires_same_host_data_dir_confirmation():
    module = _load_module()
    runner = _FakeRunner()

    result = module.run_smoke(api_base="https://example.invalid", same_host_data_dir_confirmed=False, runner=runner)

    assert result["ok"] is False
    assert result["stage"] == "operator_confirmation"
    assert result["proof_level"] == "real-outcome"
    assert result["real_exchange_native_matured_outcome_proven"] is False
    assert result["prod_actionable_alert_proven"] is False
    assert runner.commands == []


def test_hosted_real_outcome_collection_fetches_api_config_and_rejects_fixture_before_collecting():
    module = _load_module()
    runner = _FakeRunner()
    config = _prod_outcome_config()
    config["market_data"] = {"provider": "fixture"}
    config["readiness"] = {"market_data": {"status": "fixture_only"}}
    server, handler = _start_server(
        {("GET", "/api/system/config"): (200, "application/json", {"ok": True, "data": config})}
    )

    try:
        result = module.run_smoke(
            api_base=_base_url(server),
            same_host_data_dir_confirmed=True,
            runner=runner,
            timeout=2.0,
        )
    finally:
        server.shutdown()

    assert result["ok"] is False
    assert result["stage"] == "api_config_preflight"
    assert result["api_config_preflight"] == "failed"
    assert result["error"] == "production outcome config requires market_data.provider=okx_public"
    assert result["real_exchange_native_matured_outcome_proven"] is False
    assert ("GET", "/api/system/config") in handler.calls
    assert runner.commands == []


def test_hosted_real_outcome_collection_reports_api_config_http_error_before_collecting():
    module = _load_module()
    runner = _FakeRunner()
    server, handler = _start_server({})

    try:
        result = module.run_smoke(
            api_base=_base_url(server),
            same_host_data_dir_confirmed=True,
            runner=runner,
            timeout=2.0,
        )
    finally:
        server.shutdown()

    assert result["ok"] is False
    assert result["stage"] == "api_config_preflight"
    assert result["api_config_preflight"] == "failed"
    assert result["error"] == "API config returned HTTP 404"
    assert result["real_exchange_native_matured_outcome_proven"] is False
    assert ("GET", "/api/system/config") in handler.calls
    assert runner.commands == []


def test_hosted_real_outcome_collection_fails_fast_when_collector_command_fails():
    module = _load_module()
    runner = _FakeRunner(
        collect_returncode=1,
        collect_stdout='{"collected": 0, "skipped": 0, "errors": [{"error_type": "TimeoutError"}]}',
        collect_stderr="collector failed",
    )

    result = _run_smoke(module, runner=runner)

    assert result["ok"] is False
    assert result["stage"] == "collect_outcomes"
    assert result["real_exchange_native_matured_outcome_proven"] is False
    assert len(runner.commands) == 2


def test_hosted_real_outcome_collection_fails_on_collection_errors_by_default():
    module = _load_module()
    runner = _FakeRunner(
        collect_stdout=(
            '{"collected": 1, "skipped": 1, "limit": 50, '
            '"collected_refs": [{"decision_ref": "trace-real-1:legacy_final", '
            '"evaluation_target": "legacy_final", "symbol": "ETH-USDT-SWAP", '
            '"window_name": "ETH-USDT-SWAP:21600s", '
            '"collected_at": "2026-07-09T00:05:00+00:00"}], '
            '"errors": [{"trace_id": "trace-bad", "error_type": "TimeoutError"}]}'
        )
    )

    result = _run_smoke(module, runner=runner)

    assert result["ok"] is False
    assert result["stage"] == "collect_outcomes_errors"
    assert result["collection_errors_allowed"] is False
    assert result["real_exchange_native_matured_outcome_proven"] is False
    assert len(runner.commands) == 2


def test_hosted_real_outcome_collection_rejects_non_json_collector_stdout():
    module = _load_module()
    runner = _FakeRunner(collect_stdout="not json")

    result = _run_smoke(module, runner=runner)

    assert result["ok"] is False
    assert result["stage"] == "collect_outcomes_invalid_contract"
    assert result["error"] == "collect_outcomes_stdout_must_be_json_object"
    assert len(runner.commands) == 2


def test_hosted_real_outcome_collection_rejects_missing_collected_count():
    module = _load_module()
    runner = _FakeRunner(collect_stdout='{"skipped": 1, "limit": 50}')

    result = _run_smoke(module, runner=runner)

    assert result["ok"] is False
    assert result["stage"] == "collect_outcomes_invalid_contract"
    assert result["error"] == "collect_outcomes_collected_must_be_integer"
    assert len(runner.commands) == 2


def test_hosted_real_outcome_collection_rejects_string_collected_count():
    module = _load_module()
    runner = _FakeRunner(collect_stdout='{"collected": "1", "skipped": 0, "limit": 50}')

    result = _run_smoke(module, runner=runner)

    assert result["ok"] is False
    assert result["stage"] == "collect_outcomes_invalid_contract"
    assert result["error"] == "collect_outcomes_collected_must_be_integer"
    assert len(runner.commands) == 2


def test_hosted_real_outcome_collection_requires_collected_refs_when_collected_positive():
    module = _load_module()
    runner = _FakeRunner(collect_stdout='{"collected": 1, "skipped": 0, "limit": 50}')

    result = _run_smoke(module, runner=runner)

    assert result["ok"] is False
    assert result["stage"] == "collect_outcomes_invalid_contract"
    assert result["error"] == "collect_outcomes_collected_refs_must_be_non_empty_list"
    assert result["real_exchange_native_matured_outcome_proven"] is False
    assert len(runner.commands) == 2


def test_hosted_real_outcome_collection_fails_when_no_new_outcome_was_collected():
    module = _load_module()
    runner = _FakeRunner(collect_stdout='{"collected": 0, "skipped": 8, "limit": 50}')

    result = _run_smoke(module, runner=runner)

    assert result["ok"] is False
    assert result["stage"] == "no_new_outcome_collected"
    assert result["collect_outcomes"]["collected"] == 0
    assert result["real_exchange_native_matured_outcome_proven"] is False
    assert len(runner.commands) == 2


def test_hosted_real_outcome_collection_fails_when_evidence_gate_fails():
    module = _load_module()
    runner = _FakeRunner(
        evidence_returncode=1,
        evidence_stdout=(
            '{"ok": false, "smoke_profile": "real_outcome_evidence", '
            '"real_exchange_native_matured_outcome_proven": false, '
            '"prod_actionable_alert_proven": false, '
            '"error": "no_real_exchange_native_matured_outcome"}'
        ),
    )

    result = _run_smoke(module, runner=runner)

    assert result["ok"] is False
    assert result["stage"] == "real_outcome_evidence"
    assert result["real_exchange_native_matured_outcome_proven"] is False
    assert len(runner.commands) == 3


def test_hosted_real_outcome_collection_rejects_invalid_success_evidence_contract():
    module = _load_module()
    runner = _FakeRunner(
        evidence_returncode=0,
        evidence_stdout=(
            '{"ok": true, "smoke_profile": "real_outcome_evidence", '
            '"real_exchange_native_matured_outcome_proven": false, '
            '"prod_actionable_alert_proven": false}'
        ),
    )

    result = _run_smoke(module, runner=runner)

    assert result["ok"] is False
    assert result["stage"] == "real_outcome_evidence_invalid_contract"
    assert result["real_exchange_native_matured_outcome_proven"] is False
    assert len(runner.commands) == 3


def test_hosted_real_outcome_collection_rejects_naive_evidence_collected_at_contract():
    module = _load_module()
    runner = _FakeRunner(
        evidence_stdout=json.dumps(
            {
                "ok": True,
                "smoke_profile": "real_outcome_evidence",
                "matched_count": 1,
                "matched": [
                    {
                        "decision_ref": "trace-real-1:legacy_final",
                        "evaluation_target": "legacy_final",
                        "symbol": "ETH-USDT-SWAP",
                        "window_name": "ETH-USDT-SWAP:21600s",
                        "collected_at": "2026-07-09T00:05:00",
                    }
                ],
                "real_exchange_native_matured_outcome_proven": True,
                "prod_actionable_alert_proven": False,
            }
        ),
    )

    result = _run_smoke(module, runner=runner)

    assert result["ok"] is False
    assert result["stage"] == "real_outcome_evidence_invalid_contract"
    assert result["error"] == "real_outcome_evidence_matched_collected_at_must_be_timezone_aware"
    assert result["real_exchange_native_matured_outcome_proven"] is False
    assert len(runner.commands) == 3


def test_hosted_real_outcome_collection_rejects_concurrent_same_symbol_evidence_not_collected_by_this_run():
    module = _load_module()
    concurrent_evidence = {
        "ok": True,
        "smoke_profile": "real_outcome_evidence",
        "matched_count": 1,
        "matched": [
            {
                "decision_ref": "trace-concurrent:legacy_final",
                "evaluation_target": "legacy_final",
                "symbol": "ETH-USDT-SWAP",
                "window_name": "ETH-USDT-SWAP:21600s",
                "collected_at": (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat(),
            }
        ],
        "real_exchange_native_matured_outcome_proven": True,
        "prod_actionable_alert_proven": False,
    }
    runner = _FakeRunner(evidence_stdout=json.dumps(concurrent_evidence))

    result = _run_smoke(module, runner=runner)

    assert result["ok"] is False
    assert result["stage"] == "real_outcome_evidence_not_linked_to_collection"
    assert result["new_refs_verified"] is False
    assert result["error"] == "post_collection_evidence_did_not_add_or_update_refs_collected_by_this_run"
    assert result["real_exchange_native_matured_outcome_proven"] is False
    assert len(runner.commands) == 3


def test_hosted_real_outcome_collection_rejects_same_decision_ref_with_uncollected_target():
    module = _load_module()
    concurrent_evidence = {
        "ok": True,
        "smoke_profile": "real_outcome_evidence",
        "matched_count": 1,
        "matched": [
            {
                "decision_ref": "trace-real-1:legacy_final",
                "evaluation_target": "swarm_candidate_final",
                "symbol": "ETH-USDT-SWAP",
                "window_name": "ETH-USDT-SWAP:21600s",
                "collected_at": (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat(),
            }
        ],
        "real_exchange_native_matured_outcome_proven": True,
        "prod_actionable_alert_proven": False,
    }
    runner = _FakeRunner(evidence_stdout=json.dumps(concurrent_evidence))

    result = _run_smoke(module, runner=runner)

    assert result["ok"] is False
    assert result["stage"] == "real_outcome_evidence_not_linked_to_collection"
    assert result["new_refs_verified"] is False
    assert result["error"] == "post_collection_evidence_did_not_add_or_update_refs_collected_by_this_run"
    assert result["real_exchange_native_matured_outcome_proven"] is False
    assert len(runner.commands) == 3


def test_hosted_real_outcome_collection_rejects_same_decision_ref_with_uncollected_window():
    module = _load_module()
    concurrent_evidence = {
        "ok": True,
        "smoke_profile": "real_outcome_evidence",
        "matched_count": 1,
        "matched": [
            {
                "decision_ref": "trace-real-1:legacy_final",
                "evaluation_target": "legacy_final",
                "symbol": "ETH-USDT-SWAP",
                "window_name": "ETH-USDT-SWAP:43200s",
                "collected_at": (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat(),
            }
        ],
        "real_exchange_native_matured_outcome_proven": True,
        "prod_actionable_alert_proven": False,
    }
    runner = _FakeRunner(evidence_stdout=json.dumps(concurrent_evidence))

    result = _run_smoke(module, runner=runner)

    assert result["ok"] is False
    assert result["stage"] == "real_outcome_evidence_not_linked_to_collection"
    assert result["new_refs_verified"] is False
    assert result["error"] == "post_collection_evidence_did_not_add_or_update_refs_collected_by_this_run"
    assert result["real_exchange_native_matured_outcome_proven"] is False
    assert len(runner.commands) == 3


def test_hosted_real_outcome_collection_rejects_unlinked_existing_evidence():
    module = _load_module()
    existing = {
        "ok": True,
        "smoke_profile": "real_outcome_evidence",
        "matched_count": 1,
        "matched": [
            {
                "decision_ref": "trace-old:legacy_final",
                "evaluation_target": "legacy_final",
                "symbol": "ETH-USDT-SWAP",
                "window_name": "ETH-USDT-SWAP:21600s",
                "collected_at": "2026-07-09T08:00:00+00:00",
            }
        ],
        "real_exchange_native_matured_outcome_proven": True,
        "prod_actionable_alert_proven": False,
    }
    runner = _FakeRunner(
        pre_evidence_returncode=0,
        pre_evidence_stdout=json.dumps(existing),
        evidence_stdout=json.dumps(existing),
    )

    result = _run_smoke(module, runner=runner)

    assert result["ok"] is False
    assert result["stage"] == "real_outcome_evidence_not_linked_to_collection"
    assert result["new_refs_verified"] is False
    assert result["real_exchange_native_matured_outcome_proven"] is False
    assert len(runner.commands) == 3


def test_hosted_real_outcome_collection_rejects_old_ref_when_before_evidence_fails():
    module = _load_module()
    old_after_evidence = {
        "ok": True,
        "smoke_profile": "real_outcome_evidence",
        "matched_count": 1,
        "matched": [
            {
                "decision_ref": "trace-old-before-failed:legacy_final",
                "evaluation_target": "legacy_final",
                "symbol": "ETH-USDT-SWAP",
                "window_name": "ETH-USDT-SWAP:21600s",
                "collected_at": "2000-01-01T00:00:00+00:00",
            }
        ],
        "real_exchange_native_matured_outcome_proven": True,
        "prod_actionable_alert_proven": False,
    }
    runner = _FakeRunner(
        pre_evidence_returncode=1,
        pre_evidence_stdout=(
            '{"ok": false, "smoke_profile": "real_outcome_evidence", '
            '"real_exchange_native_matured_outcome_proven": false, '
            '"prod_actionable_alert_proven": false, '
            '"error": "temporarily_unavailable"}'
        ),
        evidence_stdout=json.dumps(old_after_evidence),
    )

    result = _run_smoke(module, runner=runner)

    assert result["ok"] is False
    assert result["stage"] == "real_outcome_evidence_not_linked_to_collection"
    assert result["new_refs_verified"] is False
    assert result["real_exchange_native_matured_outcome_proven"] is False
    assert len(runner.commands) == 3


def test_hosted_real_outcome_collection_rejects_fixture_api_config_before_collecting():
    module = _load_module()
    runner = _FakeRunner()
    config = _prod_outcome_config()
    config["market_data"] = {"provider": "fixture"}
    config["readiness"] = {"market_data": {"status": "fixture_only"}}

    result = _run_smoke(module, runner=runner, api_config=config)

    assert result["ok"] is False
    assert result["stage"] == "api_config_preflight"
    assert result["error"] == "production outcome config requires market_data.provider=okx_public"
    assert result["real_exchange_native_matured_outcome_proven"] is False
    assert runner.commands == []


def test_hosted_real_outcome_collection_rejects_unsafe_market_readiness_before_collecting():
    module = _load_module()
    runner = _FakeRunner()
    config = _prod_outcome_config()
    config["readiness"] = {
        "market_data": {
            "status": "unsafe",
            "provider": "okx_public",
            "unsafe": ["MARKET_DATA_OKX_BASE_URL must be unset or https://www.okx.com"],
        }
    }

    result = _run_smoke(module, runner=runner, api_config=config)

    assert result["ok"] is False
    assert result["stage"] == "api_config_preflight"
    assert result["error"] == "production outcome config requires readiness.market_data.status!=unsafe"
    assert result["real_exchange_native_matured_outcome_proven"] is False
    assert runner.commands == []
