"""validate_evidence 节点 - 证据门禁。

设计文档 7.3 节节点 6：检查证据是否充足。
调用 domain/evidence_policy.py 的 check_evidence_sufficiency 函数。
"""

from typing import Any

from crypto_alert_v2.domain.evidence_policy import check_evidence_sufficiency
from crypto_alert_v2.domain.models import MarketAnalysis
from crypto_alert_v2.graph.state import AnalysisState


def validate_evidence(state: AnalysisState) -> dict[str, Any]:
    """证据门禁节点。

    检查必需证据是否齐全：
    - 核心执行数据（ticker/mark/index/order_book/candles）
    - 数据新鲜度（< 90s）
    - 宏观事件状态（仅开仓类动作）

    可选证据缺失时降级 confidence_cap。

    输出 evidence_verdict 到 state。
    """
    decision_draft = state.get("decision_draft") or {}
    market_snapshot = state.get("market_snapshot")
    research_bundle = state.get("research_bundle")

    # 从 decision_draft 提取 main_action
    main_action = decision_draft.get("main_action", "no_trade")
    instrument = decision_draft.get("instrument", "BTC-USDT-SWAP")

    # 调用证据门禁纯函数
    verdict = check_evidence_sufficiency(
        market_snapshot=market_snapshot,
        research_bundle=research_bundle,
        main_action=main_action,
        instrument=instrument,
    )

    return {
        "evidence_verdict": verdict.model_dump(),
        "progress_events": [
            {
                "stage": "validate_evidence",
                "status": "completed" if verdict.sufficient else "blocked",
                "sufficient": verdict.sufficient,
                "confidence_cap": verdict.confidence_cap,
                "missing_required": verdict.missing_required,
                "missing_optional": verdict.missing_optional,
            },
        ],
        "warnings": [
            {"stage": "validate_evidence", "code": "evidence_warning", "message": w}
            for w in verdict.warnings
        ] if verdict.warnings else [],
    }
