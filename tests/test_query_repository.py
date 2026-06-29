from __future__ import annotations

from jiami_crypto_alert.config import load_config
from jiami_crypto_alert.journal import Journal
from jiami_crypto_alert.runner import PlanRunner
from jiami_crypto_alert.storage.query_repository import JournalQueryRepository


def test_query_repository_lists_runs_for_ui_without_raw_payloads(tmp_path):
    """UI 查询层只暴露可展示摘要，不能把 raw_decision 或 LLM 原始 payload 带出去。"""
    config = load_config("config/default.yaml")
    journal = Journal(tmp_path / "journal.db")
    PlanRunner(config, journal).run_once("ETH-USDT-SWAP")
    repository = JournalQueryRepository(journal)

    runs = repository.list_runs(limit=5)
    detail = repository.get_run_detail(runs[0]["trace_id"])

    assert runs[0]["symbol"] == "ETH-USDT-SWAP"
    assert runs[0]["final_action"] == "trigger long"
    assert detail is not None
    assert detail["trace"]["trace_id"] == runs[0]["trace_id"]
    assert "raw_decision" not in detail["plan_run"]
    assert all("request_json" not in item for item in detail["llm_interactions"])
    assert all("response_json" not in item for item in detail["llm_interactions"])


def test_query_repository_caps_list_limit(tmp_path):
    """查询层统一限制列表长度，避免前端误传大 limit 造成 SQLite 查询压力。"""
    repository = JournalQueryRepository(Journal(tmp_path / "journal.db"))

    assert repository.normalize_limit(0) == 1
    assert repository.normalize_limit(500) == 100
    assert repository.normalize_limit(20) == 20
