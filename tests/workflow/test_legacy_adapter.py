from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from crypto_manual_alert.config import load_config
from crypto_manual_alert.context.request import DecisionRequest
from crypto_manual_alert.context.run_context import DecisionRunContext
from crypto_manual_alert.domain import DecisionPlan, RiskVerdict
from crypto_manual_alert.storage.journal import Journal
from crypto_manual_alert.workflow.legacy_adapter import LegacyPlanRunnerAdapter
from crypto_manual_alert.workflow.results import DecisionStepResult


def test_legacy_plan_runner_adapter_passes_full_context_to_plan_runner(tmp_path, monkeypatch):
    """legacy adapter 交易行为仍按 symbol，但必须把完整 context 交给下一层编排。"""
    received_calls: list[tuple[str, DecisionRunContext | None, dict | None]] = []

    class FakePlanRunner:
        def __init__(self, config, journal):  # noqa: ANN001 - 测试替身只关心构造契约。
            self.config = config
            self.journal = journal

        def run_once(self, symbol, *, run_context=None, run_context_summary=None):
            received_calls.append((symbol, run_context, run_context_summary))
            now = datetime.now(timezone.utc)
            return DecisionStepResult(
                trace_id="fake-legacy-trace",
                plan=DecisionPlan(
                    plan_id="legacy-plan",
                    instrument=symbol,
                    main_action="no trade",
                    horizon="legacy",
                    manual_execution_required=True,
                    generated_at=now,
                    expires_at=now + timedelta(minutes=5),
                ),
                verdict=RiskVerdict(allowed=False, reasons=["legacy fixture"]),
            )

    monkeypatch.setattr("crypto_manual_alert.workflow.legacy_adapter.PlanRunner", FakePlanRunner)
    config = load_config("config/default.yaml")
    config = replace(config, app=replace(config.app, data_dir=str(tmp_path)))
    context = DecisionRunContext.create(
        DecisionRequest(
            symbol="ETH-USDT-SWAP",
            query_text="这个文本不应影响 legacy adapter",
            horizon="6h",
            session_id="session-x",
        )
    )

    plan, verdict = LegacyPlanRunnerAdapter(config, Journal(tmp_path / "journal.db")).run(context)

    assert received_calls == [("ETH-USDT-SWAP", context, None)]
    assert plan.instrument == "ETH-USDT-SWAP"
    assert verdict.allowed is False
