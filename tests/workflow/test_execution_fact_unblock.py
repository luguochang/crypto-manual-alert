from __future__ import annotations

import time
from dataclasses import replace

from crypto_manual_alert.config import load_config
from crypto_manual_alert.context.request import DecisionRequest
from crypto_manual_alert.context.run_context import DecisionRunContext
from crypto_manual_alert.market.providers import OkxPublicMarketDataProvider
from crypto_manual_alert.storage.journal import Journal
from crypto_manual_alert.workflow.legacy_plan_runner import PlanRunner


def _fresh_ts() -> int:
    return int(time.time() * 1000)


def _okx_http_get(path: str, params: dict[str, str]) -> dict:
    """Deterministic stand-in for OKX public HTTP responses.

    Returns fresh-timestamped payloads so the snapshot's execution facts pass the
    source_freshness check (stale_market_data_seconds). mark/index come from
    /public/mark-price; order_book from /market/books — both source=okx_public
    which maps to source_type=exchange_native and satisfies facts_gate.
    """
    ts = _fresh_ts()
    if path == "/api/v5/market/ticker":
        return {"code": "0", "data": [{"last": "3500", "bidPx": "3499", "askPx": "3501", "ts": str(ts)}]}
    if path == "/api/v5/public/mark-price":
        return {"code": "0", "data": [{"markPx": "3499", "idxPx": "3498", "ts": str(ts)}]}
    if path == "/api/v5/public/funding-rate":
        return {"code": "0", "data": [{"fundingRate": "0.0001", "fundingTime": str(ts)}]}
    if path == "/api/v5/public/open-interest":
        return {"code": "0", "data": [{"oi": "100000", "ts": str(ts)}]}
    if path == "/api/v5/market/books":
        return {"code": "0", "data": [{"asks": [["3501", "10"]], "bids": [["3499", "10"]], "ts": str(ts)}]}
    if path == "/api/v5/market/candles":
        return {"code": "0", "data": [[str(ts), "3490", "3510", "3480", "3500", "100"]]}
    raise AssertionError(f"unexpected OKX path: {path}")


def test_okx_public_market_data_unblocks_opening_action_gate(tmp_path):
    """Exchange-native OKX market data + operator-asserted event status satisfy
    facts_gate so opening actions pass.

    Delivery lifeline: facts_gate needs both (a) mark/index/order_book from an
    exchange_native source and (b) an active_event_status point from an event_pool
    /official source. With market_data.provider=okx_public the market snapshot
    supplies (a); with macro_event.provider=no_active_event the operator asserts
    no scheduled macro event, supplying (b). Together they unblock
    production_control_gate for opening actions. Under the safe defaults
    (fixture market + macro_event disabled) the same opening action stays blocked.
    """
    config = load_config("config/default.yaml")
    config = replace(config, app=replace(config.app, data_dir=str(tmp_path)))
    config = replace(config, macro_event=replace(config.macro_event, provider="no_active_event"))
    journal = Journal(tmp_path / "journal.db")
    market_provider = OkxPublicMarketDataProvider(config, http_get=_okx_http_get)
    runner = PlanRunner(config, journal, market_provider=market_provider)

    context = DecisionRunContext.create(
        DecisionRequest(symbol="ETH-USDT-SWAP", query_text="assess ETH manual operation", horizon="6h")
    )
    result = runner.run_once("ETH-USDT-SWAP", run_context=context)

    # fixture decision engine returns an opening action for ETH-USDT-SWAP
    assert result.plan.main_action == "trigger long"
    assert result.plan.instrument == "ETH-USDT-SWAP"
    # exchange-native execution facts + event status present -> opening action allowed
    assert result.verdict.allowed is True
    assert not any(
        hit.rule_id == "production_control.candidate.action_not_allowed"
        for hit in result.verdict.rule_hits
    )

    detail = journal.get_trace_detail(result.trace_id)
    assert detail is not None
    audit = detail["plan_run"]["agent_audit_view"]
    # effective_allowed_actions must include the opening action; blocked_actions must not
    decision_input = audit["decision_input"]
    assert "trigger long" in decision_input["effective_allowed_actions"]
    assert "trigger long" not in decision_input["blocked_actions"]
    # facts_gate (top-level projection) has no missing execution or event facts
    facts_gate = audit["facts_gate"]
    missing = set(facts_gate.get("missing_execution_facts") or [])
    assert {"mark", "index", "order_book"}.isdisjoint(missing)
    missing_event = set(facts_gate.get("missing_event_facts") or [])
    assert {"active_event_status"}.isdisjoint(missing_event)
    # production_control_gate now allows the opening action
    assert audit["gates"]["production_control_gate"]["allowed"] is True


def test_fixture_market_data_blocks_opening_action_by_default(tmp_path):
    """Default fixture market data has source_type=fixture, which cannot satisfy
    execution facts — so the same opening action stays blocked. This documents the
    intentional safe default and contrasts it with the okx_public unblock above.
    """
    from crypto_manual_alert.market.providers import FixtureMarketDataProvider

    config = load_config("config/default.yaml")
    config = replace(config, app=replace(config.app, data_dir=str(tmp_path)))
    journal = Journal(tmp_path / "journal.db")
    runner = PlanRunner(config, journal, market_provider=FixtureMarketDataProvider())

    context = DecisionRunContext.create(
        DecisionRequest(symbol="ETH-USDT-SWAP", query_text="assess ETH manual operation", horizon="6h")
    )
    result = runner.run_once("ETH-USDT-SWAP", run_context=context)

    assert result.plan.main_action == "trigger long"
    assert result.verdict.allowed is False
    assert any(
        hit.rule_id == "production_control.candidate.action_not_allowed"
        for hit in result.verdict.rule_hits
    )


def test_staging_config_loads_and_unblocks_gate(tmp_path):
    """The staging overlay (default + staging.yaml) configures the actionable-alert
    path: okx_public market data + no_active_event operator assertion. With mocked
    OKX HTTP it produces an allowed opening action end-to-end via PlanRunner.
    """
    config = load_config("config/default.yaml", "config/staging.yaml")
    assert config.market_data.provider == "okx_public"
    assert config.macro_event.provider == "no_active_event"
    config = replace(config, app=replace(config.app, data_dir=str(tmp_path)))

    journal = Journal(tmp_path / "journal.db")
    market_provider = OkxPublicMarketDataProvider(config, http_get=_okx_http_get)
    runner = PlanRunner(config, journal, market_provider=market_provider)
    context = DecisionRunContext.create(
        DecisionRequest(symbol="ETH-USDT-SWAP", query_text="assess ETH manual operation", horizon="6h")
    )
    result = runner.run_once("ETH-USDT-SWAP", run_context=context)

    assert result.plan.main_action == "trigger long"
    assert result.verdict.allowed is True
    detail = journal.get_trace_detail(result.trace_id)
    audit = detail["plan_run"]["agent_audit_view"]
    assert audit["gates"]["production_control_gate"]["allowed"] is True
