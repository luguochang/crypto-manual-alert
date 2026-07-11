from __future__ import annotations

from dataclasses import replace

from crypto_manual_alert.config import load_config
from crypto_manual_alert.storage.business_summary import build_business_summary


def _production_ready_config(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://llm.example.com")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4.1")
    monkeypatch.setenv("OPENAI_API_KEY", "prod-like-openai-key")
    monkeypatch.setenv("BARK_DEVICE_KEY", "prod-like-bark-key")
    monkeypatch.setenv("MACRO_EVENT_PROVIDER", "no_active_event")
    monkeypatch.setenv("MACRO_EVENT_OPERATOR_REF", "ops:macro-desk")
    monkeypatch.setenv("MACRO_EVENT_CONFIRMED_AT", "2099-07-09T09:30:00+08:00")
    monkeypatch.setenv("MACRO_EVENT_SOURCE_REF", "calendar:forexfactory:2099-07-09:no-high-impact")
    monkeypatch.setenv("MACRO_EVENT_ASSERTION_HORIZON", "6h")
    monkeypatch.setenv("MACRO_EVENT_VALID_UNTIL", "2099-07-09T15:30:00+08:00")
    config = load_config("config/default.yaml", "config/staging.yaml", "config/prod.yaml")
    return replace(config, app=replace(config.app, data_dir=str(tmp_path)))


def _allowed_production_payload(llm_summary: dict | None = None) -> dict:
    payload = {
        "verdict": {"allowed": True, "reasons": [], "rule_hits": []},
        "facts_gate": {
            "passed": True,
            "severity": "ok",
            "missing_execution_facts": [],
            "missing_event_facts": [],
            "reasons": [],
        },
        "production_control_gate": {"allowed": True, "reasons": [], "rule_hits": []},
        "snapshot": {
            "symbol": "ETH-USDT-SWAP",
            "points": {
                "mark": {"source": "okx_public", "value": 3499.0},
                "index": {"source": "okx_public", "value": 3498.0},
                "order_book": {
                    "source": "okx_public",
                    "value": {"asks": [["3501", "10"]], "bids": [["3499", "10"]]},
                },
                "active_event_status": {
                    "source": "event_pool",
                    "value": {
                        "status": "no_active_event",
                        "provider": "no_active_event",
                        "operator_ref": "ops:macro-desk",
                        "confirmed_at": "2099-07-09T09:30:00+08:00",
                        "source_ref": "calendar:forexfactory:2099-07-09:no-high-impact",
                        "horizon": "6h",
                        "valid_until": "2099-07-09T15:30:00+08:00",
                        "metadata_complete": True,
                    },
                },
            },
        },
    }
    if llm_summary is not None:
        payload["llm_summary"] = llm_summary
    return payload


def _base_plan() -> dict:
    return {
        "instrument": "ETH-USDT-SWAP",
        "main_action": "trigger long",
        "horizon": "6h",
        "manual_execution_required": True,
    }


def test_business_summary_labels_mock_llm_path_separately_from_fixture_notification(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "local-mock-key")
    config = load_config("config/default.yaml")
    config = replace(
        config,
        app=replace(config.app, data_dir=str(tmp_path)),
        decision=replace(
            config.decision,
            engine="openai_compatible",
            openai_base_url="http://127.0.0.1:8011",
            openai_model="mock-crypto-plan",
        ),
    )

    summary = build_business_summary(
        plan={
            "instrument": "ETH-USDT-SWAP",
            "main_action": "trigger long",
            "horizon": "6h",
            "manual_execution_required": True,
        },
        verdict={"allowed": False, "reasons": []},
        config=config,
    )

    assert summary["decision_label"] == "模拟 LLM"
    assert "mock LLM" in summary["mode_notice"]
    assert "未调用真实 LLM" not in summary["mode_notice"]
    assert summary["notification"]["status"] == "disabled"


def test_business_summary_uses_persisted_llm_summary_without_runtime_config():
    summary = build_business_summary(
        plan={
            "instrument": "ETH-USDT-SWAP",
            "main_action": "trigger long",
            "horizon": "6h",
            "manual_execution_required": True,
        },
        verdict={"allowed": False, "reasons": []},
        payload={
            "llm_summary": {
                "has_real_llm": True,
                "provider": "openai_compatible",
                "model": "mock-crypto-plan",
                "status": "ok",
            },
            "snapshot": {"symbol": "ETH-USDT-SWAP", "source": "fixture"},
        },
    )

    assert summary["decision_label"] == "模拟 LLM"
    assert "mock LLM" in summary["mode_notice"]
    assert "未调用真实 LLM" not in summary["mode_notice"]
    generation = summary["generation_summary"]
    assert generation["mode_label"] == "模型链路演练"
    assert generation["provider_label"] == "OpenAI-compatible"
    assert generation["model"] == "mock-crypto-plan"
    assert generation["status_label"] == "模型已返回"
    assert generation["response_summary"] == "模型结论：触发做多。"
    rendered = str(generation)
    assert "request_json" not in rendered
    assert "response_json" not in rendered
    assert "choices" not in rendered
    assert "chat.completion" not in rendered


def test_business_summary_generation_summary_marks_fixture_as_local_sample():
    summary = build_business_summary(
        plan={
            "instrument": "ETH-USDT-SWAP",
            "main_action": "trigger long",
            "horizon": "6h",
            "manual_execution_required": True,
        },
        verdict={"allowed": False, "reasons": []},
        payload={"snapshot": {"symbol": "ETH-USDT-SWAP", "source": "fixture"}},
    )

    generation = summary["generation_summary"]
    assert generation["mode_label"] == "本地演练"
    assert generation["status_label"] == "未调用外部模型"
    assert generation["model"] is None
    assert generation["response_summary"] == "使用本地样本计划，未产生真实模型返回。"
    assert any("本地样本" in item for item in generation["detail_bullets"])


def test_business_summary_generation_summary_describes_real_model_with_safe_completion_excerpt():
    summary = build_business_summary(
        plan={
            "instrument": "ETH-USDT-SWAP",
            "main_action": "trigger long",
            "horizon": "6h",
            "manual_execution_required": True,
        },
        verdict={"allowed": True, "reasons": []},
        payload={
            "llm_summary": {
                "has_real_llm": True,
                "provider": "openai_compatible",
                "model": "gpt-4.1",
                "status": "ok",
                "duration_ms": 456,
                "total_tokens": 321,
                "finish_reason": "stop",
                "output_summary": {
                    "choices": [
                        {
                            "message": {
                                "content": "模型原始返回：ETH 当前不追多，等待 3512 触发；跌破 3468 则计划失效。"
                            }
                        }
                    ]
                },
            },
            "snapshot": {
                "symbol": "ETH-USDT-SWAP",
                "points": {
                    "mark": {"source": "okx_public"},
                    "index": {"source": "okx_public"},
                    "order_book": {"source": "okx_public"},
                },
            },
            "production_control_gate": {"allowed": True, "reasons": []},
            "facts_gate": {"missing_execution_facts": [], "missing_event_facts": [], "reasons": []},
        },
    )

    generation = summary["generation_summary"]
    assert generation["mode_label"] == "真实模型链路"
    assert generation["provider_label"] == "OpenAI-compatible"
    assert generation["model"] == "gpt-4.1"
    assert generation["status_label"] == "模型已返回"
    assert generation["duration_text"] == "456 ms"
    assert generation["token_text"] == "321 tokens"
    assert generation["response_summary"] == "模型结论：触发做多。"
    assert generation["raw_completion_label"] == "模型原始返回摘录"
    assert generation["raw_completion_excerpt"] == "模型原始返回：ETH 当前不追多，等待 3512 触发；跌破 3468 则计划失效。"
    rendered = str(generation)
    assert "模型原始返回" in rendered
    assert "choices" not in rendered
    assert "request_json" not in rendered
    assert "response_json" not in rendered


def test_business_summary_projects_okx_market_data_status_without_hiding_failures():
    summary = build_business_summary(
        plan={
            "instrument": "ETH-USDT-SWAP",
            "main_action": "trigger long",
            "horizon": "6h",
            "manual_execution_required": True,
        },
        verdict={"allowed": False, "reasons": ["缺少真实订单簿执行事实"]},
        payload={
            "snapshot": {
                "symbol": "ETH-USDT-SWAP",
                "points": {
                    "last": {"name": "last", "value": 3500.5, "timestamp_ms": 1783666000000, "source": "okx_public"},
                    "mark": {"name": "mark", "value": 3499.8, "timestamp_ms": 1783666000000, "source": "okx_public"},
                    "index": {"name": "index", "value": 3498.7, "timestamp_ms": 1783666000000, "source": "okx_public"},
                },
                "unavailable": [
                    "funding_rate: ConnectError",
                    "open_interest: ConnectTimeout",
                    "order_book: ReadTimeout /Users/chase/secret trace_id=abc token=abc",
                    "candles: HTTPStatusError",
                ],
            },
            "facts_gate": {
                "missing_execution_facts": ["order_book"],
                "missing_event_facts": [],
                "reasons": ["missing execution fact: order_book"],
            },
        },
    )

    status = summary["market_data_status"]
    assert status["provider"] == "okx_public"
    assert status["provider_label"] == "OKX public"
    assert status["execution_facts_ready"] is False
    assert "OKX public 行情" in status["summary"]
    assert "执行事实不完整" in status["summary"]
    items = {item["name"]: item for item in status["items"]}
    assert items["ticker"]["status"] == "ok"
    assert items["ticker"]["value_text"] == "3500.5"
    assert items["mark"]["status"] == "ok"
    assert items["index"]["status"] == "ok"
    assert items["order_book"]["status"] == "failed"
    assert items["order_book"]["can_satisfy_execution_fact"] is True
    assert items["order_book"]["error_type"] == "ReadTimeout"
    assert items["funding_rate"]["status"] == "failed"
    assert items["open_interest"]["status"] == "failed"
    assert items["candles"]["status"] == "failed"
    rendered = str(status)
    assert "/Users/chase" not in rendered
    assert "trace_id" not in rendered
    assert "token=abc" not in rendered


def test_business_summary_does_not_report_empty_execution_fact_as_success():
    summary = build_business_summary(
        plan={
            "instrument": "ETH-USDT-SWAP",
            "main_action": "trigger long",
            "horizon": "6h",
            "manual_execution_required": True,
        },
        verdict={"allowed": False, "reasons": []},
        payload={
            "snapshot": {
                "symbol": "ETH-USDT-SWAP",
                "points": {
                    "mark": {"name": "mark", "value": 3499.8, "source": "okx_public"},
                    "index": {"name": "index", "value": None, "source": "okx_public"},
                    "order_book": {
                        "name": "order_book",
                        "value": {"asks": [["3501", "10"]], "bids": [["3499", "10"]]},
                        "source": "okx_public",
                    },
                },
            },
            "facts_gate": {"missing_execution_facts": [], "missing_event_facts": [], "reasons": []},
        },
    )

    status = summary["market_data_status"]
    items = {item["name"]: item for item in status["items"]}
    assert status["execution_facts_ready"] is False
    assert items["index"]["status"] == "failed"
    assert items["index"]["error_type"] == "InvalidPayload"
    assert "执行事实不完整" in status["summary"]


def test_business_summary_does_not_report_malformed_order_book_as_success():
    payload = _allowed_production_payload()
    payload["snapshot"]["points"]["order_book"] = {
        "name": "order_book",
        "value": {"asks": [[]], "bids": [["3499", "10"]]},
        "source": "okx_public",
    }

    summary = build_business_summary(
        plan=_base_plan(),
        verdict={"allowed": True, "reasons": []},
        payload=payload,
    )

    items = {item["name"]: item for item in summary["market_data_status"]["items"]}
    assert summary["market_data_status"]["execution_facts_ready"] is False
    assert items["order_book"]["status"] == "failed"
    assert items["order_book"]["error_type"] == "InvalidPayload"
    assert summary["decision_label"] != "可人工复核"


def test_business_summary_actionable_label_fails_closed_when_facts_gate_is_not_explicitly_passed():
    payload = _allowed_production_payload()
    payload["facts_gate"]["passed"] = False
    payload["facts_gate"]["severity"] = "hard_fail"

    summary = build_business_summary(
        plan=_base_plan(),
        verdict={"allowed": True, "reasons": []},
        payload=payload,
    )

    assert summary["decision_label"] != "可人工复核"
    assert "可支持本次人工复核" not in summary["mode_notice"]


def test_business_summary_market_status_distinguishes_fixture_points_from_exchange_native_facts():
    summary = build_business_summary(
        plan={
            "instrument": "ETH-USDT-SWAP",
            "main_action": "trigger long",
            "horizon": "6h",
            "manual_execution_required": True,
        },
        verdict={"allowed": False, "reasons": ["执行事实来源不是交易所原生"]},
        payload={
            "snapshot": {
                "symbol": "ETH-USDT-SWAP",
                "source": "fixture",
                "points": {
                    "last": {"name": "last", "value": 3500.5, "timestamp_ms": 1783666000000, "source": "fixture"},
                    "mark": {"name": "mark", "value": 3499.8, "timestamp_ms": 1783666000000, "source": "fixture"},
                    "index": {"name": "index", "value": 3498.7, "timestamp_ms": 1783666000000, "source": "fixture"},
                    "order_book": {
                        "name": "order_book",
                        "value": {"asks": [["3501", "10"]], "bids": [["3499", "10"]]},
                        "timestamp_ms": 1783666000000,
                        "source": "fixture",
                    },
                },
            },
            "facts_gate": {
                "missing_execution_facts": ["index", "mark", "order_book"],
                "missing_event_facts": [],
                "reasons": ["index: source_type fixture is not exchange_native"],
            },
        },
    )

    status = summary["market_data_status"]
    assert status["provider"] == "fixture"
    assert status["success_count"] == 4
    assert status["execution_facts_ready"] is False
    assert "缺少交易所原生 index、mark、order_book" in status["summary"]
    assert "缺少 index、mark、order_book" not in status["summary"]
    items = {item["name"]: item for item in status["items"]}
    assert items["mark"]["status"] == "ok"
    assert items["mark"]["source"] == "fixture"
    assert items["mark"]["can_satisfy_execution_fact"] is True
    assert items["order_book"]["status"] == "ok"
    assert items["order_book"]["source"] == "fixture"


def test_business_summary_generation_summary_uses_safe_llm_output_summary_excerpt():
    summary = build_business_summary(
        plan={
            "instrument": "ETH-USDT-SWAP",
            "main_action": "trigger long",
            "horizon": "6h",
            "probability": 0.61,
            "invalidation": "跌破 3435 后多头计划失效",
            "manual_execution_required": True,
        },
        verdict={"allowed": True, "reasons": []},
        payload={
            "llm_summary": {
                "has_real_llm": True,
                "provider": "openai_compatible",
                "model": "gpt-4.1",
                "status": "ok",
                "output_summary": {
                    "summary": "模型倾向等待 ETH 突破触发后人工追多，跌破 3435 则计划失效。",
                    "main_action": "trigger long",
                    "probability": 0.61,
                },
            },
            "snapshot": {
                "symbol": "ETH-USDT-SWAP",
                "points": {
                    "mark": {"source": "okx_public"},
                    "index": {"source": "okx_public"},
                    "order_book": {"source": "okx_public"},
                },
            },
            "production_control_gate": {"allowed": True, "reasons": []},
            "facts_gate": {"missing_execution_facts": [], "missing_event_facts": [], "reasons": []},
        },
    )

    generation = summary["generation_summary"]
    assert generation["response_summary"] == "模型倾向等待 ETH 突破触发后人工追多，跌破 3435 则计划失效。"
    rendered = str(generation)
    assert "choices" not in rendered
    assert "request_json" not in rendered
    assert "response_json" not in rendered
    assert "api_key" not in rendered


def test_business_summary_generation_summary_uses_safe_string_output_summary_excerpt():
    summary = build_business_summary(
        plan={
            "instrument": "ETH-USDT-SWAP",
            "main_action": "trigger long",
            "horizon": "6h",
            "probability": 0.61,
            "manual_execution_required": True,
        },
        verdict={"allowed": True, "reasons": []},
        payload={
            "llm_summary": {
                "has_real_llm": True,
                "provider": "openai_compatible",
                "model": "gpt-4.1",
                "status": "ok",
                "output_summary": "模型倾向等待 ETH 突破后人工追多，若资金费率重新拥挤则暂停。",
            },
            "snapshot": {
                "symbol": "ETH-USDT-SWAP",
                "points": {
                    "mark": {"source": "okx_public"},
                    "index": {"source": "okx_public"},
                    "order_book": {"source": "okx_public"},
                },
            },
            "production_control_gate": {"allowed": True, "reasons": []},
            "facts_gate": {"missing_execution_facts": [], "missing_event_facts": [], "reasons": []},
        },
    )

    generation = summary["generation_summary"]
    assert generation["response_summary"] == "模型倾向等待 ETH 突破后人工追多，若资金费率重新拥挤则暂停。"


def test_business_summary_generation_summary_rejects_unsafe_output_summary_and_uses_plan_excerpt():
    summary = build_business_summary(
        plan={
            "instrument": "ETH-USDT-SWAP",
            "main_action": "trigger long",
            "horizon": "6h",
            "probability": 0.61,
            "invalidation": "跌破 3435 后多头计划失效",
            "manual_execution_required": True,
        },
        verdict={"allowed": True, "reasons": []},
        payload={
            "llm_summary": {
                "has_real_llm": True,
                "provider": "openai_compatible",
                "model": "gpt-4.1",
                "status": "ok",
                "output_summary": {
                    "summary": (
                        "candidate.confidence_cap_exceeded token=abc "
                        "https://api.day.app/device/body /Users/chase/leak trace_id=abc"
                    ),
                },
            },
            "snapshot": {
                "symbol": "ETH-USDT-SWAP",
                "points": {
                    "mark": {"source": "okx_public"},
                    "index": {"source": "okx_public"},
                    "order_book": {"source": "okx_public"},
                },
            },
            "production_control_gate": {"allowed": True, "reasons": []},
            "facts_gate": {"missing_execution_facts": [], "missing_event_facts": [], "reasons": []},
        },
    )

    generation = summary["generation_summary"]
    assert generation["response_summary"] == "模型结论：触发做多；置信度 61%；失效条件：跌破 3435 后多头计划失效。"
    rendered = str(generation)
    assert "candidate.confidence_cap_exceeded" not in rendered
    assert "token=abc" not in rendered
    assert "api.day.app" not in rendered
    assert "/Users/chase" not in rendered
    assert "trace_id" not in rendered


def test_business_summary_generation_summary_keeps_zero_probability_from_output_summary():
    summary = build_business_summary(
        plan={
            "instrument": "ETH-USDT-SWAP",
            "main_action": "no trade",
            "horizon": "6h",
            "manual_execution_required": True,
        },
        verdict={"allowed": False, "reasons": []},
        payload={
            "llm_summary": {
                "has_real_llm": True,
                "provider": "openai_compatible",
                "model": "gpt-4.1",
                "status": "ok",
                "output_summary": {
                    "main_action": "no trade",
                    "probability": 0,
                },
            },
            "snapshot": {"symbol": "ETH-USDT-SWAP", "source": "fixture"},
        },
    )

    generation = summary["generation_summary"]
    assert generation["response_summary"] == "模型结论：暂不操作；置信度 0%。"


def test_business_summary_generation_summary_keeps_plan_summary_and_safe_raw_completion_excerpt():
    completion = "模型原始返回：等待 ETH 突破 3512 后人工追多，跌破 3435 则计划失效。"
    summary = build_business_summary(
        plan={
            "instrument": "ETH-USDT-SWAP",
            "main_action": "trigger long",
            "horizon": "6h",
            "probability": 0.61,
            "invalidation": "跌破 3435 后多头计划失效",
            "manual_execution_required": True,
        },
        verdict={"allowed": True, "reasons": []},
        payload={
            "llm_summary": {
                "has_real_llm": True,
                "provider": "openai_compatible",
                "model": "gpt-4.1",
                "status": "ok",
                "output_summary": {"choices": [{"message": {"content": completion}}]},
            },
            "snapshot": {
                "symbol": "ETH-USDT-SWAP",
                "points": {
                    "mark": {"source": "okx_public"},
                    "index": {"source": "okx_public"},
                    "order_book": {"source": "okx_public"},
                },
            },
            "production_control_gate": {"allowed": True, "reasons": []},
            "facts_gate": {"missing_execution_facts": [], "missing_event_facts": [], "reasons": []},
        },
    )

    generation = summary["generation_summary"]
    assert generation["response_summary"] == "模型结论：触发做多；置信度 61%；失效条件：跌破 3435 后多头计划失效。"
    assert generation["raw_completion_excerpt"] == completion
    rendered = str(generation)
    assert "choices" not in rendered
    assert "request_json" not in rendered
    assert "response_json" not in rendered


def test_business_summary_generation_summary_converts_json_completion_to_business_excerpt():
    completion = (
        '{"instrument":"ETH-USDT-SWAP","main_action":"trigger long","probability":0.58,'
        '"invalidation":"跌破 3435 后计划失效","manual_execution_required":true}'
    )
    summary = build_business_summary(
        plan={
            "instrument": "ETH-USDT-SWAP",
            "main_action": "trigger long",
            "horizon": "6h",
            "probability": 0.58,
            "invalidation": "跌破 3435 后计划失效",
            "manual_execution_required": True,
        },
        verdict={"allowed": False, "reasons": []},
        payload={
            "llm_summary": {
                "has_real_llm": True,
                "provider": "openai_compatible",
                "model": "mock-crypto-plan",
                "status": "ok",
                "output_summary": {"choices": [{"message": {"content": completion}}]},
            },
            "snapshot": {"symbol": "ETH-USDT-SWAP", "source": "fixture"},
        },
    )

    generation = summary["generation_summary"]
    assert generation["raw_completion_excerpt"] == "模型结论：触发做多；置信度 58%；失效条件：跌破 3435 后计划失效。"
    rendered = str(generation)
    assert '{"instrument"' not in rendered
    assert "manual_execution_required" not in rendered
    assert "choices" not in rendered


def test_business_summary_generation_summary_falls_back_to_plan_excerpt_with_list_invalidation():
    completion = "模型原始返回：资金费率重新拥挤前，仅保留人工触发提醒。"
    summary = build_business_summary(
        plan={
            "instrument": "ETH-USDT-SWAP",
            "main_action": "trigger long",
            "horizon": "6h",
            "probability": 0.61,
            "invalidation": ["跌破 3435 后多头计划失效", "资金费率重新拥挤"],
            "manual_execution_required": True,
        },
        verdict={"allowed": True, "reasons": []},
        payload={
            "llm_summary": {
                "has_real_llm": True,
                "provider": "openai_compatible",
                "model": "gpt-4.1",
                "status": "ok",
                "output_summary": {"choices": [{"message": {"content": completion}}]},
            },
            "snapshot": {"symbol": "ETH-USDT-SWAP", "source": "fixture"},
        },
    )

    generation = summary["generation_summary"]
    assert generation["response_summary"] == "模型结论：触发做多；置信度 61%；失效条件：跌破 3435 后多头计划失效；资金费率重新拥挤。"
    assert generation["raw_completion_excerpt"] == completion


def test_business_summary_generation_summary_never_uses_generic_success_placeholder():
    completion = "模型原始返回：当前证据不足，等待订单簿与事件状态补齐后再人工复核。"
    summary = build_business_summary(
        plan={
            "instrument": "ETH-USDT-SWAP",
            "horizon": "6h",
            "manual_execution_required": True,
        },
        verdict={"allowed": False, "reasons": []},
        payload={
            "llm_summary": {
                "has_real_llm": True,
                "provider": "openai_compatible",
                "model": "gpt-4.1",
                "status": "ok",
                "output_summary": {"choices": [{"message": {"content": completion}}]},
            },
            "snapshot": {"symbol": "ETH-USDT-SWAP", "source": "fixture"},
        },
    )

    generation = summary["generation_summary"]
    assert generation["response_summary"] == (
        "模型返回已记录，但当前摘要缺少可安全展示的模型结论；请以提醒动作、价格和风险面板为准。"
    )
    rendered = str(generation)
    assert "模型已返回结构化提醒。" not in rendered
    assert generation["raw_completion_excerpt"] == completion
    assert "choices" not in rendered


def test_business_summary_does_not_label_prod_ready_config_as_production_without_persisted_llm(
    tmp_path,
    monkeypatch,
):
    config = _production_ready_config(tmp_path, monkeypatch)

    summary = build_business_summary(
        plan=_base_plan(),
        verdict={"allowed": True, "reasons": [], "rule_hits": []},
        config=config,
        payload=_allowed_production_payload(),
        notification={"ok": True, "channel": "bark", "status_code": 200, "error": None},
    )

    assert summary["decision_label"] == "可人工复核"
    assert "本地/预发证明" in summary["mode_notice"]
    assert "不是生产成功" in summary["mode_notice"]
    assert "真实外部模型" in summary["mode_notice"]
    assert "当前已满足人工复核门槛" not in summary["mode_notice"]
    generation = summary["generation_summary"]
    assert generation["mode_label"] == "模型配置已启用"
    assert generation["status_label"] == "本次未记录模型返回"
    assert generation["response_summary"] == "模型配置已启用，但本次运行没有持久化可展示的模型返回；请以提醒动作、价格和风险面板为准。"
    assert generation["status"] is None


def test_business_summary_does_not_label_failed_llm_as_production_success(tmp_path, monkeypatch):
    config = _production_ready_config(tmp_path, monkeypatch)

    summary = build_business_summary(
        plan=_base_plan(),
        verdict={"allowed": True, "reasons": [], "rule_hits": []},
        config=config,
        payload=_allowed_production_payload(
            {
                "has_real_llm": True,
                "provider": "openai_compatible",
                "model": "gpt-4.1",
                "status": "error",
            }
        ),
        notification={"ok": True, "channel": "bark", "status_code": 200, "error": None},
    )

    assert summary["decision_label"] == "可人工复核"
    assert "本地/预发证明" in summary["mode_notice"]
    assert "不是生产成功" in summary["mode_notice"]
    assert "真实外部模型未返回成功" in summary["mode_notice"]
    assert "当前已满足人工复核门槛" not in summary["mode_notice"]


def test_business_summary_calls_out_failed_bark_when_other_production_evidence_is_present(tmp_path, monkeypatch):
    config = _production_ready_config(tmp_path, monkeypatch)

    summary = build_business_summary(
        plan=_base_plan(),
        verdict={"allowed": True, "reasons": [], "rule_hits": []},
        config=config,
        payload=_allowed_production_payload(
            {
                "has_real_llm": True,
                "provider": "openai_compatible",
                "model": "gpt-4.1",
                "status": "ok",
            }
        ),
        notification={"ok": False, "channel": "bark", "status_code": 500, "error": "timeout"},
    )

    assert summary["decision_label"] == "可人工复核"
    assert "本地/预发证明" in summary["mode_notice"]
    assert "通知未证明生产成功" in summary["mode_notice"]
    assert "不是生产成功" in summary["mode_notice"]
    assert "当前已满足人工复核门槛" not in summary["mode_notice"]


def test_business_summary_labels_production_actionable_only_with_persisted_external_evidence_and_sent_bark(
    tmp_path,
    monkeypatch,
):
    config = _production_ready_config(tmp_path, monkeypatch)

    summary = build_business_summary(
        plan=_base_plan(),
        verdict={"allowed": True, "reasons": [], "rule_hits": []},
        config=config,
        payload=_allowed_production_payload(
            {
                "has_real_llm": True,
                "provider": "openai_compatible",
                "model": "gpt-4.1",
                "status": "ok",
            }
        ),
        notification={"ok": True, "channel": "bark", "status_code": 200, "error": None},
    )

    assert summary["decision_label"] == "可人工复核"
    assert "当前已满足人工复核门槛" in summary["mode_notice"]
    assert "不是生产成功" not in summary["mode_notice"]


def test_business_summary_does_not_label_staging_config_as_actionable_without_run_evidence(tmp_path):
    config = load_config("config/default.yaml", "config/staging.yaml")
    config = replace(config, app=replace(config.app, data_dir=str(tmp_path)))

    summary = build_business_summary(
        plan={
            "instrument": "ETH-USDT-SWAP",
            "main_action": "trigger long",
            "horizon": "6h",
            "manual_execution_required": True,
        },
        verdict={"allowed": True, "reasons": [], "rule_hits": []},
        config=config,
    )

    assert summary["decision_label"] != "可人工复核"
    assert "当前已满足" not in summary["mode_notice"]


def test_business_summary_labels_persisted_actionable_result_without_runtime_config():
    summary = build_business_summary(
        plan={
            "instrument": "ETH-USDT-SWAP",
            "main_action": "trigger long",
            "horizon": "6h",
            "manual_execution_required": True,
        },
        verdict={"allowed": True, "reasons": [], "rule_hits": []},
        payload={
            "verdict": {"allowed": True, "reasons": [], "rule_hits": []},
            "facts_gate": {
                "passed": True,
                "severity": "ok",
                "missing_execution_facts": [],
                "missing_event_facts": [],
                "reasons": [],
            },
            "production_control_gate": {"allowed": True, "reasons": [], "rule_hits": []},
            "snapshot": {
                "symbol": "ETH-USDT-SWAP",
                "points": {
                    "mark": {"source": "okx_public", "value": 3499.0},
                    "index": {"source": "okx_public", "value": 3498.0},
                    "order_book": {
                        "source": "okx_public",
                        "value": {"asks": [["3501", "10"]], "bids": [["3499", "10"]]},
                    },
                },
            },
        },
    )

    assert summary["decision_label"] == "可人工复核"
    assert "本地/预发证明" in summary["mode_notice"]
    assert "不是生产成功" in summary["mode_notice"]


def test_business_summary_explains_no_active_event_operator_assertion():
    summary = build_business_summary(
        plan={
            "instrument": "ETH-USDT-SWAP",
            "main_action": "trigger long",
            "horizon": "6h",
            "manual_execution_required": True,
        },
        verdict={"allowed": True, "reasons": [], "rule_hits": []},
        payload={
            "verdict": {"allowed": True, "reasons": [], "rule_hits": []},
            "facts_gate": {
                "missing_execution_facts": [],
                "missing_event_facts": [],
                "reasons": [],
            },
            "production_control_gate": {"allowed": True, "reasons": [], "rule_hits": []},
            "snapshot": {
                "symbol": "ETH-USDT-SWAP",
                "points": {
                    "mark": {"source": "okx_public"},
                    "index": {"source": "okx_public"},
                    "order_book": {"source": "okx_public"},
                    "active_event_status": {
                        "source": "event_pool",
                        "value": {
                            "status": "no_active_event",
                            "provider": "no_active_event",
                            "operator_ref": "ops:macro-desk",
                            "confirmed_at": "2026-07-09T09:30:00+08:00",
                            "source_ref": "calendar:forexfactory:2026-07-09:no-high-impact",
                            "horizon": "6h",
                            "valid_until": "2026-07-09T15:30:00+08:00",
                            "metadata_complete": True,
                        },
                    },
                },
            },
        },
    )

    evidence_text = " ".join(summary["evidence_bullets"])
    assert "人工确认无活跃宏观事件" in evidence_text
    assert "ops:macro-desk" in evidence_text
    assert "calendar:forexfactory:2026-07-09:no-high-impact" in evidence_text
    assert "2026-07-09T15:30:00+08:00" in evidence_text
    assert "自动事件池" not in evidence_text


def test_business_summary_warns_when_no_active_event_metadata_is_incomplete():
    summary = build_business_summary(
        plan={
            "instrument": "ETH-USDT-SWAP",
            "main_action": "trigger long",
            "horizon": "6h",
            "manual_execution_required": True,
        },
        verdict={"allowed": True, "reasons": [], "rule_hits": []},
        payload={
            "verdict": {"allowed": True, "reasons": [], "rule_hits": []},
            "facts_gate": {
                "missing_execution_facts": [],
                "missing_event_facts": [],
                "reasons": [],
            },
            "production_control_gate": {"allowed": True, "reasons": [], "rule_hits": []},
            "snapshot": {
                "symbol": "ETH-USDT-SWAP",
                "points": {
                    "mark": {"source": "okx_public"},
                    "index": {"source": "okx_public"},
                    "order_book": {"source": "okx_public"},
                    "active_event_status": {
                        "source": "event_pool",
                        "value": {
                            "status": "no_active_event",
                            "provider": "no_active_event",
                            "metadata_complete": False,
                        },
                    },
                },
            },
        },
    )

    evidence_text = " ".join(summary["evidence_bullets"])
    assert "无活跃宏观事件人工断言" in evidence_text
    assert "元数据不完整" in evidence_text
    assert "不能作为生产证明" in evidence_text
