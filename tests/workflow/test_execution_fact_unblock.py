from __future__ import annotations

import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json

from crypto_manual_alert.config import load_config
from crypto_manual_alert.context.request import DecisionRequest
from crypto_manual_alert.context.run_context import DecisionRunContext
import crypto_manual_alert.market.providers as market_providers
from crypto_manual_alert.market.providers import OkxPublicMarketDataProvider
from crypto_manual_alert.storage.journal import Journal
from crypto_manual_alert.workflow.legacy_plan_runner import PlanRunner


class CountingDecisionEngine:
    def __init__(self):
        self.calls: list[dict] = []

    def run(self, input_payload):
        self.calls.append(input_payload)
        return json.dumps(
            {
                "instrument": "ETH-USDT-SWAP",
                "main_action": "trigger long",
                "horizon": "6h",
                "reference_price": 3500,
                "entry_trigger": 3510,
                "stop_price": 3435,
                "target_1": 3580,
                "target_2": 3660,
                "probability": 0.58,
                "position_size_class": "light",
                "max_leverage": 2,
                "risk_pct": 0.25,
                "expires_in_seconds": 90,
                "why_not_opposite": "BTC structure is not confirming downside.",
                "invalidation": "Invalid if ETH loses 3435 on fresh OKX mark price.",
                "unavailable_data": [],
                "manual_execution_required": True,
                "notes": "counting engine",
            },
            ensure_ascii=False,
        )


def _fresh_ts() -> int:
    return int(time.time() * 1000)


def _with_complete_no_active_event_assertion(config):
    confirmed_at = datetime.now(timezone.utc)
    valid_until = confirmed_at + timedelta(hours=6)
    return replace(
        config,
        macro_event=replace(
            config.macro_event,
            provider="no_active_event",
            no_active_event_operator_ref="ops:macro-desk",
            no_active_event_confirmed_at=confirmed_at.isoformat(),
            no_active_event_source_ref="calendar:operator-verified:no-high-impact",
            no_active_event_horizon="6h",
            no_active_event_valid_until=valid_until.isoformat(),
        ),
    )


def _okx_http_get(path: str, params: dict[str, str]) -> dict:
    """Deterministic stand-in for OKX public HTTP responses.

    Returns fresh-timestamped payloads so the snapshot's execution facts pass the
    source_freshness check (stale_market_data_seconds). mark comes from
    /public/mark-price, index from /market/index-tickers, and order_book from
    /market/books; all carry source=okx_public and satisfy facts_gate.
    """
    ts = _fresh_ts()
    if path == "/api/v5/market/ticker":
        return {"code": "0", "data": [{"last": "3500", "bidPx": "3499", "askPx": "3501", "ts": str(ts)}]}
    if path == "/api/v5/public/mark-price":
        return {"code": "0", "data": [{"markPx": "3499", "ts": str(ts)}]}
    if path == "/api/v5/market/index-tickers":
        assert params == {"instId": "ETH-USDT"}
        return {"code": "0", "data": [{"instId": "ETH-USDT", "idxPx": "3498", "ts": str(ts)}]}
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
    config = _with_complete_no_active_event_assertion(config)
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


def test_okx_public_provider_disables_environment_proxy_for_default_client(monkeypatch):
    """Local/mock OKX verification must not be hijacked by system proxy env vars."""
    config = load_config("config/default.yaml", "config/staging.yaml")
    calls: list[dict[str, object]] = []

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"code": "0", "data": [{"markPx": "3499", "ts": str(_fresh_ts())}]}

    class Client:
        def __init__(self, **kwargs):
            calls.append(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, path, params):
            return Response()

    monkeypatch.setattr(market_providers.httpx, "Client", Client)

    provider = OkxPublicMarketDataProvider(config)
    provider._get("/api/v5/public/mark-price", {"instId": "ETH-USDT-SWAP"})

    assert calls
    assert calls[0]["trust_env"] is False
    assert "proxy" not in calls[0]


def test_okx_public_provider_can_enable_environment_proxy_for_prod_network(monkeypatch):
    config = load_config("config/default.yaml", "config/staging.yaml")
    config = replace(
        config,
        market_data=replace(config.market_data, http_trust_env=True),
    )
    calls: list[dict[str, object]] = []

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"code": "0", "data": [{"markPx": "3499", "ts": str(_fresh_ts())}]}

    class Client:
        def __init__(self, **kwargs):
            calls.append(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, path, params):
            return Response()

    monkeypatch.setattr(market_providers.httpx, "Client", Client)

    provider = OkxPublicMarketDataProvider(config)
    provider._get("/api/v5/public/mark-price", {"instId": "ETH-USDT-SWAP"})

    assert calls
    assert calls[0]["trust_env"] is True
    assert "proxy" not in calls[0]


def test_okx_public_provider_uses_explicit_http_proxy(monkeypatch):
    config = load_config("config/default.yaml", "config/staging.yaml")
    config = replace(
        config,
        market_data=replace(
            config.market_data,
            http_trust_env=False,
            http_proxy="http://127.0.0.1:8888",
        ),
    )
    calls: list[dict[str, object]] = []

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"code": "0", "data": [{"markPx": "3499", "ts": str(_fresh_ts())}]}

    class Client:
        def __init__(self, **kwargs):
            calls.append(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, path, params):
            return Response()

    monkeypatch.setattr(market_providers.httpx, "Client", Client)

    provider = OkxPublicMarketDataProvider(config)
    provider._get("/api/v5/public/mark-price", {"instId": "ETH-USDT-SWAP"})

    assert calls
    assert calls[0]["trust_env"] is False
    assert calls[0]["proxy"] == "http://127.0.0.1:8888"


def test_staging_config_loads_and_unblocks_gate(tmp_path):
    """The staging overlay (default + staging.yaml) configures the actionable-alert
    path: okx_public market data + no_active_event operator assertion. With mocked
    OKX HTTP it produces an allowed opening action end-to-end via PlanRunner.
    """
    config = load_config("config/default.yaml", "config/staging.yaml")
    assert config.market_data.provider == "okx_public"
    assert config.macro_event.provider == "no_active_event"
    config = _with_complete_no_active_event_assertion(config)
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


def test_no_active_event_assertion_metadata_is_persisted_in_snapshot(tmp_path):
    """The no-active-event assertion must be an auditable run artifact, not just a config switch."""

    config = load_config("config/default.yaml", "config/staging.yaml")
    config = replace(
        config,
        app=replace(config.app, data_dir=str(tmp_path)),
        macro_event=replace(
            config.macro_event,
            no_active_event_operator_ref="ops:macro-desk",
            no_active_event_confirmed_at="2026-07-09T09:30:00+08:00",
            no_active_event_source_ref="calendar:forexfactory:2026-07-09:no-high-impact",
            no_active_event_horizon="6h",
            no_active_event_valid_until="2026-07-09T15:30:00+08:00",
        ),
    )
    journal = Journal(tmp_path / "journal.db")
    market_provider = OkxPublicMarketDataProvider(config, http_get=_okx_http_get)
    runner = PlanRunner(config, journal, market_provider=market_provider)
    context = DecisionRunContext.create(
        DecisionRequest(symbol="ETH-USDT-SWAP", query_text="assess ETH manual operation", horizon="6h")
    )

    result = runner.run_once("ETH-USDT-SWAP", run_context=context)

    payload = journal.get_plan_run_payload(result.plan.plan_id)
    event_point = payload["snapshot"]["points"]["active_event_status"]
    event_value = event_point["value"]
    assert event_point["source"] == "event_pool"
    assert event_value["status"] == "no_active_event"
    assert event_value["provider"] == "no_active_event"
    assert event_value["operator_ref"] == "ops:macro-desk"
    assert event_value["confirmed_at"] == "2026-07-09T09:30:00+08:00"
    assert event_value["source_ref"] == "calendar:forexfactory:2026-07-09:no-high-impact"
    assert event_value["horizon"] == "6h"
    assert event_value["valid_until"] == "2026-07-09T15:30:00+08:00"
    assert event_value["metadata_complete"] is True


def test_staging_actionable_can_disable_candidate_sidecar_without_changing_final_verdict(tmp_path):
    config = load_config("config/default.yaml", "config/staging.yaml")
    config = _with_complete_no_active_event_assertion(config)
    config = replace(
        config,
        app=replace(config.app, data_dir=str(tmp_path)),
        decision=replace(config.decision, candidate_sidecar_mode="disabled"),
    )
    engine = CountingDecisionEngine()
    journal = Journal(tmp_path / "journal.db")
    market_provider = OkxPublicMarketDataProvider(config, http_get=_okx_http_get)
    runner = PlanRunner(config, journal, market_provider=market_provider, decision_engine=engine)
    context = DecisionRunContext.create(
        DecisionRequest(symbol="ETH-USDT-SWAP", query_text="assess ETH manual operation", horizon="6h")
    )

    result = runner.run_once("ETH-USDT-SWAP", run_context=context)

    assert len(engine.calls) == 1
    assert engine.calls[0].get("mode") != "candidate_final_input"
    assert result.plan.main_action == "trigger long"
    assert result.plan.manual_execution_required is True
    assert result.verdict.allowed is True
    detail = journal.get_trace_detail(result.trace_id)
    audit = detail["plan_run"]["agent_audit_view"]
    assert audit["gates"]["production_control_gate"]["allowed"] is True
    payload = journal.get_plan_run_payload(result.plan.plan_id)
    assert payload["final_input_selection"]["mode"] == "legacy_prompt"
    assert payload.get("candidate_final_decision") is None
    assert payload["audit_only"]["candidate_final_decision"] is None
