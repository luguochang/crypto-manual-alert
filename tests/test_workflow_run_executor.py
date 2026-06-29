from __future__ import annotations

from dataclasses import replace

from crypto_manual_alert.config import load_config
from crypto_manual_alert.context.request import DecisionRequest
from crypto_manual_alert.journal import Journal
from crypto_manual_alert.workflow.executor import RunExecutor


def test_run_executor_submits_manual_request_through_legacy_runner(tmp_path):
    """RunExecutor 首版是受控 facade：统一请求语义，但复用已验证的 PlanRunner。"""
    config = load_config("config/default.yaml")
    config = replace(config, app=replace(config.app, data_dir=str(tmp_path)))
    journal = Journal(tmp_path / "journal.db")
    executor = RunExecutor(config=config, journal=journal)

    result = executor.submit(DecisionRequest(symbol="ETH-USDT-SWAP", query_text="评估 ETH", horizon="6h"))

    assert result.trace_id
    assert result.plan["instrument"] == "ETH-USDT-SWAP"
    assert result.plan["main_action"] == "trigger long"
    assert result.verdict["allowed"] is True
    assert journal.list_traces(limit=1)[0]["trace_id"] == result.trace_id


def test_run_executor_rejects_eval_and_replay_side_effect_runs(tmp_path):
    """eval/replay 不应从首版执行入口误触发生产 plan 或 Bark。"""
    config = load_config("config/default.yaml")
    config = replace(config, app=replace(config.app, data_dir=str(tmp_path)))
    executor = RunExecutor(config=config, journal=Journal(tmp_path / "journal.db"))

    for run_type in ("eval", "replay"):
        try:
            executor.submit(DecisionRequest(run_type=run_type, symbol="ETH-USDT-SWAP"))
        except ValueError as exc:
            assert "manual or scheduled" in str(exc)
        else:
            raise AssertionError(f"{run_type} should be rejected by the live executor")
