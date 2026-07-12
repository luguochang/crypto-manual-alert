"""build_final_result 节点 - 合并最终结果。

设计文档 7.3 节节点 8：合并分析结果、证据裁决、风控裁决为最终产物。
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from crypto_alert_v2.graph.state import AnalysisState


def build_final_result(state: AnalysisState) -> dict[str, Any]:
    """合并最终结果节点。

    将以下数据合并为 final_result：
    - decision_draft（MarketAnalysis 结构化输出）
    - evidence_verdict（证据门禁结果）
    - risk_verdict（风控规则结果）

    同时生成 notification_plan（通知计划）。

    如果证据门禁设置了 confidence_cap，应用到 final_result.probability。
    """
    decision_draft = state.get("decision_draft") or {}
    evidence_verdict = state.get("evidence_verdict") or {}
    risk_verdict = state.get("risk_verdict") or {}

    # 应用置信度上限
    probability = decision_draft.get("probability", 0.0)
    confidence_cap = evidence_verdict.get("confidence_cap", 1.0)
    if probability > confidence_cap:
        probability = confidence_cap

    # 计算过期时间
    now = datetime.now(timezone.utc)
    expires_in = decision_draft.get("expires_in_seconds", 90)
    expires_at = (now + timedelta(seconds=expires_in)).isoformat()

    # 合并最终结果
    final_result: dict[str, Any] = {
        # 分析结果
        "regime": decision_draft.get("regime"),
        "factor_scores": decision_draft.get("factor_scores", {}),
        "total_score": decision_draft.get("total_score", 0),
        "main_action": decision_draft.get("main_action"),
        "instrument": decision_draft.get("instrument"),
        "horizon": decision_draft.get("horizon"),
        "reference_price": decision_draft.get("reference_price"),
        "entry_trigger": decision_draft.get("entry_trigger"),
        "stop_price": decision_draft.get("stop_price"),
        "target_1": decision_draft.get("target_1"),
        "target_2": decision_draft.get("target_2"),
        "probability": probability,
        "position_size_class": decision_draft.get("position_size_class"),
        "max_leverage": decision_draft.get("max_leverage"),
        "risk_pct": decision_draft.get("risk_pct"),
        "root_cause_chain": decision_draft.get("root_cause_chain", []),
        "why_not_opposite": decision_draft.get("why_not_opposite", ""),
        "invalidation": decision_draft.get("invalidation", ""),
        "unavailable_data": decision_draft.get("unavailable_data", []),
        "manual_execution_required": decision_draft.get("manual_execution_required", True),
        "expires_at": expires_at,

        # 证据和风控状态
        "evidence_sufficient": evidence_verdict.get("sufficient", False),
        "evidence_confidence_cap": confidence_cap,
        "evidence_missing_required": evidence_verdict.get("missing_required", []),
        "evidence_missing_optional": evidence_verdict.get("missing_optional", []),
        "risk_allowed": risk_verdict.get("allowed", False),
        "risk_blocked_reasons": risk_verdict.get("blocked_reasons", []),
        "risk_warnings": risk_verdict.get("warnings", []),

        # 元数据
        "generated_at": now.isoformat(),
        "status": "pending_approval" if risk_verdict.get("allowed", False) else "blocked",
    }

    # 构建通知计划
    notification_plan = {
        "channel": "bark",
        "should_send": state.get("request", {}).get("notify", True),
        "title_parts": {
            "symbol": final_result["instrument"],
            "action": final_result["main_action"],
            "probability": final_result["probability"],
        },
        "body_parts": {
            "entry_trigger": final_result["entry_trigger"],
            "stop_price": final_result["stop_price"],
            "target_1": final_result["target_1"],
            "target_2": final_result["target_2"],
            "risk_pct": final_result["risk_pct"],
            "max_leverage": final_result["max_leverage"],
            "why_not_opposite": final_result["why_not_opposite"],
            "expires_in_seconds": expires_in,
            "risk_allowed": final_result["risk_allowed"],
            "blocked_reasons": final_result["risk_blocked_reasons"],
            "warnings": final_result["risk_warnings"],
            "unavailable_data": final_result["unavailable_data"],
        },
    }

    return {
        "final_result": final_result,
        "notification_plan": notification_plan,
        "progress_events": [
            {
                "stage": "build_final_result",
                "status": "completed",
                "main_action": final_result["main_action"],
                "risk_allowed": final_result["risk_allowed"],
                "probability": probability,
            },
        ],
    }
