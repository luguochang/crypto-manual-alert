from __future__ import annotations

from crypto_manual_alert.config import load_config
from crypto_manual_alert.context.request import build_manual_decision_request
from crypto_manual_alert.storage.journal import Journal
from crypto_manual_alert.storage.query_repository import JournalQueryRepository
from crypto_manual_alert.workflow.executor import RunExecutor


def test_query_repository_lists_runs_for_ui_without_raw_payloads(tmp_path):
    """UI 查询层只暴露可展示摘要，不能把 raw_decision 或 LLM 原始 payload 带出去。"""
    config = load_config("config/default.yaml")
    journal = Journal(tmp_path / "journal.db")
    RunExecutor(config=config, journal=journal).submit(
        build_manual_decision_request({"symbol": "ETH-USDT-SWAP"})
    )
    repository = JournalQueryRepository(journal)

    runs = repository.list_runs(limit=5)
    detail = repository.get_run_detail(runs[0]["trace_id"])

    assert runs[0]["symbol"] == "ETH-USDT-SWAP"
    assert runs[0]["final_action"] == "trigger long"
    assert detail is not None
    assert detail["trace"]["trace_id"] == runs[0]["trace_id"]
    audit = detail["plan_run"]["agent_audit_view"]
    assert audit["available"] is True
    assert len(audit["workers"]) == 7
    assert any(worker["agent_name"] == "ExecutionRiskAgent" for worker in audit["workers"])
    assert audit["decision_input"]["mode"] == "pre_final_candidate"
    assert audit["gates"]["production_control_gate"]["allowed"] is False
    assert "raw_decision" not in str(audit)
    assert "frozen_input" not in str(audit)
    assert "raw_decision" not in detail["plan_run"]
    assert all("request_json" not in item for item in detail["llm_interactions"])
    assert all("response_json" not in item for item in detail["llm_interactions"])


def test_query_repository_caps_list_limit(tmp_path):
    """查询层统一限制列表长度，避免前端误传大 limit 造成 SQLite 查询压力。"""
    repository = JournalQueryRepository(Journal(tmp_path / "journal.db"))

    assert repository.normalize_limit(0) == 1
    assert repository.normalize_limit(500) == 100
    assert repository.normalize_limit(20) == 20
