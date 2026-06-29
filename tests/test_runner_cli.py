import json
from datetime import datetime, timezone

from crypto_manual_alert.cli import main
from crypto_manual_alert.config import load_config
from crypto_manual_alert.domain import MarketSnapshot, NotificationResult
from crypto_manual_alert.journal import Journal
from crypto_manual_alert.runner import PlanRunner
from crypto_manual_alert.research import FixtureSearchAdapter


def test_runner_fixture_flow(tmp_path):
    config = load_config("config/default.yaml")
    journal = Journal(tmp_path / "journal.db")
    runner = PlanRunner(config, journal)

    plan, verdict = runner.run_once("ETH-USDT-SWAP")

    assert plan.instrument == "ETH-USDT-SWAP"
    assert plan.manual_execution_required is True
    assert verdict.allowed is True
    with journal.connect() as conn:
        plan_row = conn.execute("SELECT payload_json FROM plan_runs").fetchone()
        trace_rows = conn.execute("SELECT span_name, status FROM trace_spans ORDER BY started_at").fetchall()
    payload = json.loads(plan_row["payload_json"])
    assert payload["trace_id"]
    assert any(row["span_name"] == "market.fetch" and row["status"] == "ok" for row in trace_rows)
    assert any(row["span_name"] == "decision.final" and row["status"] == "ok" for row in trace_rows)


def test_runner_records_failure_when_decision_engine_raises(tmp_path):
    config = load_config("config/default.yaml")
    journal = Journal(tmp_path / "journal.db")

    class BadEngine:
        def run(self, prompt_packet):
            raise RuntimeError("model down")

    runner = PlanRunner(config, journal, decision_engine=BadEngine())

    plan, verdict = runner.run_once("ETH-USDT-SWAP")

    assert verdict.allowed is False
    assert plan.main_action == "no trade"
    with journal.connect() as conn:
        rows = conn.execute("SELECT status, payload_json FROM plan_runs").fetchall()
    assert rows
    assert rows[0]["status"] == "blocked"
    assert "model down" in rows[0]["payload_json"]


def test_runner_records_notification_failure_without_changing_verdict(tmp_path):
    config = load_config("config/default.yaml")
    notification = config.notification.__class__(**{**config.notification.__dict__, "enabled": True})
    config = config.__class__(
        app=config.app,
        trading=config.trading,
        market_data=config.market_data,
        decision=config.decision,
        notification=notification,
        scheduler=config.scheduler,
        research=config.research,
        security=config.security,
    )
    journal = Journal(tmp_path / "journal.db")

    class FailingNotifier:
        def send(self, plan, verdict):
            return NotificationResult(ok=False, error="push failed")

    runner = PlanRunner(config, journal, notifier=FailingNotifier())

    plan, verdict = runner.run_once("ETH-USDT-SWAP")

    assert verdict.allowed is True
    with journal.connect() as conn:
        row = conn.execute("SELECT ok, error FROM notifications").fetchone()
    assert row["ok"] == 0
    assert row["error"] == "push failed"


def test_runner_records_notification_exception_without_changing_verdict(tmp_path):
    config = load_config("config/default.yaml")
    notification = config.notification.__class__(**{**config.notification.__dict__, "enabled": True})
    config = config.__class__(
        app=config.app,
        trading=config.trading,
        market_data=config.market_data,
        decision=config.decision,
        notification=notification,
        scheduler=config.scheduler,
        research=config.research,
        security=config.security,
    )
    journal = Journal(tmp_path / "journal.db")

    class ExplodingNotifier:
        def send(self, plan, verdict):
            raise RuntimeError("push crashed")

    runner = PlanRunner(config, journal, notifier=ExplodingNotifier())

    plan, verdict = runner.run_once("ETH-USDT-SWAP")

    assert verdict.allowed is True
    with journal.connect() as conn:
        row = conn.execute("SELECT ok, error FROM notifications").fetchone()
    assert row["ok"] == 0
    assert "push crashed" in row["error"]


def test_runner_sends_failure_alert_when_pipeline_fails_and_failure_alerts_enabled(tmp_path):
    config = load_config("config/default.yaml")
    notification = config.notification.__class__(
        **{**config.notification.__dict__, "enabled": True, "send_failure_alerts": True}
    )
    config = config.__class__(
        app=config.app,
        trading=config.trading,
        market_data=config.market_data,
        decision=config.decision,
        notification=notification,
        scheduler=config.scheduler,
        research=config.research,
        security=config.security,
    )
    journal = Journal(tmp_path / "journal.db")

    class BadEngine:
        def run(self, prompt_packet):
            raise RuntimeError("model down")

    class CapturingNotifier:
        def __init__(self):
            self.sent = []

        def send(self, plan, verdict):
            self.sent.append((plan, verdict))
            return NotificationResult(ok=True, status_code=200)

    notifier = CapturingNotifier()
    runner = PlanRunner(config, journal, decision_engine=BadEngine(), notifier=notifier)

    plan, verdict = runner.run_once("ETH-USDT-SWAP")

    assert verdict.allowed is False
    assert notifier.sent
    assert notifier.sent[0][0].plan_id == plan.plan_id
    with journal.connect() as conn:
        row = conn.execute("SELECT ok, status_code FROM notifications").fetchone()
    assert row["ok"] == 1
    assert row["status_code"] == 200


def test_runner_research_fallback_enriches_prompt_and_journal(tmp_path):
    config = load_config("config/default.yaml")
    research = config.research.__class__(**{**config.research.__dict__, "enabled": True, "search_provider": "fixture"})
    config = config.__class__(
        app=config.app,
        trading=config.trading,
        market_data=config.market_data,
        decision=config.decision,
        notification=config.notification,
        scheduler=config.scheduler,
        security=config.security,
        research=research,
    )
    journal = Journal(tmp_path / "journal.db")

    class TimeoutMarketProvider:
        def fetch_snapshot(self, symbol):
            return MarketSnapshot(
                symbol=symbol,
                fetched_at=datetime.now(timezone.utc),
                points={},
                unavailable=["mark: ConnectTimeout", "order_book: ConnectTimeout"],
            )

    class CapturingEngine:
        def __init__(self):
            self.prompt_packet = None

        def run(self, prompt_packet):
            self.prompt_packet = prompt_packet
            return """
{
  "instrument": "ETH-USDT-SWAP",
  "main_action": "no trade",
  "horizon": "6h",
  "reference_price": null,
  "entry_trigger": null,
  "stop_price": null,
  "target_1": null,
  "target_2": null,
  "probability": null,
  "position_size_class": "none",
  "max_leverage": 0,
  "risk_pct": 0,
  "expires_in_seconds": 90,
  "why_not_opposite": "Core exchange-native execution data remains unavailable.",
  "invalidation": "Recheck after mark and order book recover.",
  "unavailable_data": ["mark", "order_book"],
  "manual_execution_required": true
}
"""

    engine = CapturingEngine()
    adapter = FixtureSearchAdapter(
        {
            "eth_price_context": [
                {
                    "title": "ETH search context",
                    "url": "https://example.test/eth",
                    "snippet": "ETH fallback context from search.",
                }
            ]
        }
    )

    runner = PlanRunner(
        config,
        journal,
        market_provider=TimeoutMarketProvider(),
        decision_engine=engine,
        search_adapter=adapter,
    )

    plan, verdict = runner.run_once("ETH-USDT-SWAP")

    assert plan.main_action == "no trade"
    assert verdict.allowed is True
    assert "research" in engine.prompt_packet
    assert engine.prompt_packet["research"]["leader_summary"]
    assert "web_eth_price_context" in engine.prompt_packet["market_snapshot"]["points"]
    with journal.connect() as conn:
        row = conn.execute("SELECT payload_json FROM plan_runs").fetchone()
    payload = json.loads(row["payload_json"])
    assert "research" in payload
    assert payload["research"]["plan"]["queries"]
    assert payload["research"]["leader_summary"]
    assert payload["raw_decision"]
    assert payload["parsed_plan"]["main_action"] == "no trade"
    assert payload["evidence_snapshot"]["points"]["web_eth_price_context"]


def test_cli_show_config_redacts(capsys):
    exit_code = main(["show-config"])

    assert exit_code == 0
    output = capsys.readouterr().out
    data = json.loads(output)
    assert data["trading"]["auto_order_enabled"] is False
    assert data["notification"]["bark_device_key_value"] in {"<unset>", "<redacted>"}


def test_cli_trace_query_and_badcase_flow(tmp_path, capsys):
    config_path = tmp_path / "config.yaml"
    data_dir = tmp_path / "data"
    config_path.write_text(
        f"""
app:
  data_dir: {str(data_dir).replace("\\", "/")}
""",
        encoding="utf-8",
    )

    run_code = main(["--config", str(config_path), "run-once", "--symbol", "ETH-USDT-SWAP"])
    assert run_code == 0
    capsys.readouterr()

    list_code = main(["--config", str(config_path), "trace-list", "--limit", "5"])
    list_output = capsys.readouterr().out
    assert list_code == 0
    traces = json.loads(list_output)
    trace_id = traces[0]["trace_id"]
    plan_id = traces[0]["final_plan_id"]
    assert traces[0]["final_action"] == "trigger long"
    assert traces[0]["span_count"] >= 1

    show_code = main(["--config", str(config_path), "trace-show", "--trace-id", trace_id])
    show_output = capsys.readouterr().out
    assert show_code == 0
    detail = json.loads(show_output)
    assert detail["trace"]["trace_id"] == trace_id
    assert detail["plan_run"]["plan_id"] == plan_id
    assert "raw_decision" not in detail["plan_run"]
    assert detail["spans"]
    assert all("request_json" not in item for item in detail["llm_interactions"])

    badcase_code = main(
        [
            "--config",
            str(config_path),
            "record-badcase",
            "--plan-id",
            plan_id,
            "--category",
            "execution_plan_unclear",
            "--severity",
            "medium",
            "--summary",
            "用于回归评估",
            "--source",
            "developer",
            "--eval-dataset",
            "failure_cases",
        ]
    )
    assert badcase_code == 0
    capsys.readouterr()

    badcase_list_code = main(["--config", str(config_path), "badcase-list", "--limit", "5"])
    badcase_output = capsys.readouterr().out
    assert badcase_list_code == 0
    badcases = json.loads(badcase_output)
    assert badcases[0]["trace_id"] == trace_id
    assert badcases[0]["plan_id"] == plan_id
    assert badcases[0]["category"] == "execution_plan_unclear"
    assert badcases[0]["summary"] == "用于回归评估"
    assert badcases[0]["eval_dataset_name"] == "failure_cases"
