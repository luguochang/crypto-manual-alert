from __future__ import annotations

import pytest

from crypto_manual_alert.context.request import DecisionRequest, build_manual_decision_request


def test_decision_request_defaults_to_manual_btc_and_manual_only():
    """手动请求缺省值必须保守：默认 BTC，且永远要求人工执行。"""
    request = DecisionRequest()

    assert request.run_type == "manual"
    assert request.symbol == "BTC-USDT-SWAP"
    assert request.query_text == ""
    assert request.manual_only is True
    assert request.alert_channel == "bark"


def test_decision_request_rejects_unknown_run_type():
    """运行类型必须可枚举，避免 eval/replay/manual 的副作用边界被字符串绕过。"""
    with pytest.raises(ValueError, match="run_type"):
        DecisionRequest(run_type="live")


def test_build_manual_decision_request_accepts_legacy_query_alias():
    """API 首版兼容历史 query 字段，但内部统一为 query_text。"""
    request = build_manual_decision_request(
        {
            "symbol": "ETH-USDT-SWAP",
            "query": "评估 ETH 手动操作计划",
            "horizon": "6h",
            "session_id": "session-a",
        }
    )

    assert request.run_type == "manual"
    assert request.symbol == "ETH-USDT-SWAP"
    assert request.query_text == "评估 ETH 手动操作计划"
    assert request.horizon == "6h"
    assert request.session_id == "session-a"
    assert request.manual_only is True


def test_build_manual_decision_request_preserves_frontend_position_and_risk_mode():
    """manual-run 前端字段必须进入后端请求语义，不能被入口层静默丢弃。"""
    request = build_manual_decision_request(
        {
            "symbol": "ETH-USDT-SWAP",
            "position": {"side": "long", "size": "0.5", "entry_price": 3200},
            "risk_mode": "conservative",
        }
    )

    assert request.position == {"side": "long", "size": "0.5", "entry_price": 3200}
    assert request.risk_mode == "conservative"


def test_manual_request_cannot_disable_manual_only():
    """用户输入不能关闭 manual_only，这是手动提醒系统的硬边界。"""
    request = build_manual_decision_request({"manual_only": False})

    assert request.manual_only is True
