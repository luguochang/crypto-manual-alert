"""pytest 公共 fixtures。"""

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage


@pytest.fixture
def sample_state():
    """基本测试状态，包含 AnalysisState 所有字段。"""
    return {
        "messages": [],
        "identity": None,
        "request": None,
        "run_context": None,
        "market_snapshot": None,
        "research_bundle": None,
        "specialist_findings": [],
        "decision_draft": None,
        "evidence_verdict": None,
        "risk_verdict": None,
        "final_result": None,
        "notification_plan": None,
        "approval_result": None,
        "progress_events": [],
        "warnings": [],
        "errors": [],
    }


@pytest.fixture
def mock_llm():
    """FakeChatModel，用于 Agent Contract 测试。"""
    return FakeMessagesListChatModel(responses=[
        AIMessage(content="测试分析结果"),
    ])


@pytest.fixture
def sample_market_snapshot():
    """模拟市场数据快照，结构与 mock_market tool 返回一致。"""
    return {
        "symbol": "BTC-USDT-SWAP",
        "ticker": {
            "last": "65000.5",
            "bid": "64995.0",
            "ask": "65005.0",
            "vol24h": "1234.56",
        },
        "mark_price": "65010.0",
        "index_price": "64990.0",
        "funding_rate": "0.0001",
        "open_interest": "1000.5",
        "data_fetched_at": "2026-07-12T00:00:00Z",
        "source_level": "exchange_native",
        "unavailable_fields": [],
    }
