"""apply_risk_policy 节点 - 风控规则。

设计文档 7.3 节节点 7：执行 14 条确定性风控规则。
调用 domain/risk_policy.py 的 check_plan 函数。

风控规则是纯函数，无网络/DB/LLM 依赖。
blocking 规则阻断，warn 规则只警告。
"""

from typing import Any

from crypto_alert_v2.domain.models import MarketAnalysis
from crypto_alert_v2.domain.risk_policy import check_plan
from crypto_alert_v2.graph.state import AnalysisState


def apply_risk_policy(state: AnalysisState) -> dict[str, Any]:
    """风控规则节点。

    执行 14 条确定性风控规则：
    1. 必须人工执行
    2. 交易品种白名单
    3. 计划未过期
    4-6. 开仓必须有止损/入场/失效条件
    7. 核心执行数据完整
    8-9. 风险占比和杠杆不超限
    10. 置信度不超上限
    11. 数据新鲜度
    12. 禁止自动下单
    13. 应用模式检查
    14. 数据缺失警告

    输出 risk_verdict 到 state。
    route_after_risk 根据 risk_verdict.allowed 决定路由。
    """
    decision_draft = state.get("decision_draft") or {}
    market_snapshot = state.get("market_snapshot")

    # 将 decision_draft dict 转为 MarketAnalysis 模型
    try:
        analysis = MarketAnalysis(**decision_draft)
    except Exception as exc:
        # 模型校验失败，直接阻断
        return {
            "risk_verdict": {
                "allowed": False,
                "blocked_reasons": [f"MarketAnalysis 校验失败：{exc}"],
                "warnings": [],
                "confidence_cap": 0.0,
            },
            "errors": [{
                "stage": "apply_risk_policy",
                "code": "model_validation_failed",
                "message": str(exc),
            }],
            "progress_events": [
                {
                    "stage": "apply_risk_policy",
                    "status": "failed",
                    "reason": "model_validation_failed",
                },
            ],
        }

    # 调用 14 条风控规则纯函数
    verdict = check_plan(
        analysis=analysis,
        config=None,  # 使用默认配置
        market_snapshot=market_snapshot,
    )

    return {
        "risk_verdict": verdict.model_dump(),
        "progress_events": [
            {
                "stage": "apply_risk_policy",
                "status": "completed" if verdict.allowed else "blocked",
                "allowed": verdict.allowed,
                "blocked_reasons": verdict.blocked_reasons,
                "warnings_count": len(verdict.warnings),
            },
        ],
        "warnings": [
            {"stage": "apply_risk_policy", "code": "risk_warning", "message": w}
            for w in verdict.warnings
        ] if verdict.warnings else [],
    }
