from __future__ import annotations

from typing import Any

from crypto_manual_alert.eval.outcomes import DecisionOutcome


EVALUATION_TARGET_LABELS = {
    "legacy_final": "最终建议链路",
    "swarm_candidate_final": "候选建议链路",
    "hold_no_trade": "不操作对照",
    "no_trade": "不操作对照",
}

SOURCE_LABELS = {
    "exchange_native": "交易所原生样本",
    "mocked_outcome": "本地展示样本",
}

UNSCORED_LABELS = {
    "pending_outcome": "等待观察窗口成熟",
    "window_not_matured": "等待观察窗口成熟",
    "price_source_not_exchange_native": "本地展示样本，不计入真实金融质量",
    "price_window_incomplete": "观察窗口数据不完整，暂不可评分",
    "no_trade_action": "不操作对照，不计入交易命中评分",
    "missing_trade_levels": "缺少交易价位，暂不可评分",
    "unsupported_action": "动作不适用于交易命中评分",
}


def build_result_review(detail: dict[str, Any], outcome_store: Any | None) -> dict[str, Any]:
    """Project eval sidecar outcomes into a per-run product status.

    The result is intentionally a product projection, not a raw OutcomeStore dump:
    mock/local outcomes stay visibility-only and exchange-native samples are the
    only source that can make the row scorable.
    """

    refs = _decision_refs(detail)
    outcomes = outcome_store.list_outcomes_by_decision_refs(refs) if outcome_store is not None else []
    return result_review_from_outcomes(outcomes)


def result_review_from_outcomes(outcomes: list[DecisionOutcome]) -> dict[str, Any]:
    if not outcomes:
        return {
            "status": "not_collected",
            "label": "尚未产生复盘结果",
            "message": "结果尚未生成。观察窗口成熟并完成采集后，会在这里显示复盘状态。",
            "quality_scope": "none",
            "sample_count": 0,
            "scored_count": 0,
            "pending_count": 0,
            "unscored_count": 0,
            "can_score": False,
            "items": [],
        }

    items = [_result_review_item(outcome) for outcome in outcomes]
    scored_count = sum(1 for outcome in outcomes if _is_exchange_scorable(outcome))
    pending_count = sum(1 for outcome in outcomes if _is_pending(outcome))
    unscored_count = len(outcomes) - scored_count - pending_count
    has_mock = any(outcome.window.source_type == "mocked_outcome" for outcome in outcomes)
    has_exchange_scorable = scored_count > 0

    if has_exchange_scorable and scored_count < len(outcomes):
        status = "mixed_quality_scope"
        label = "部分可评分"
        message = f"{scored_count} 条交易所原生成熟样本可用于质量复盘；其余样本不计入真实金融质量。"
        quality_scope = "mixed_exchange_native_and_visibility_only" if has_mock else "mixed_exchange_native_and_unscored"
    elif has_exchange_scorable:
        status = "scorable"
        label = "可评分"
        message = "已收集交易所原生成熟结果样本，可用于后续金融质量复盘。"
        quality_scope = "exchange_native_financial_quality"
    elif has_mock:
        status = "mock_visibility_only"
        label = "本地展示样本"
        message = "本地展示样本，不计入真实金融质量。"
        quality_scope = "visibility_only_not_financial_quality"
    elif pending_count:
        status = "pending"
        label = "等待窗口成熟"
        message = "观察窗口尚未成熟，暂不判断后续结果。"
        quality_scope = "pending_not_financial_quality"
    else:
        status = "unscorable"
        label = "不可评分"
        message = "已有后续记录，但样本不满足真实金融质量评分条件。"
        quality_scope = "not_financial_quality"

    return {
        "status": status,
        "label": label,
        "message": message,
        "quality_scope": quality_scope,
        "sample_count": len(outcomes),
        "scored_count": scored_count,
        "pending_count": pending_count,
        "unscored_count": unscored_count,
        "can_score": has_exchange_scorable,
        "items": items,
    }


def _decision_refs(detail: dict[str, Any]) -> list[str]:
    trace = _mapping(detail.get("trace"))
    plan_run = _mapping(detail.get("plan_run"))
    plan_id = str(plan_run.get("plan_id") or trace.get("final_plan_id") or "").strip()
    if not plan_id:
        return []
    return [
        f"{plan_id}:legacy_final",
        f"{plan_id}:swarm_candidate_final",
        f"{plan_id}:hold_no_trade",
    ]


def _result_review_item(outcome: DecisionOutcome) -> dict[str, Any]:
    return {
        "target_label": EVALUATION_TARGET_LABELS.get(outcome.evaluation_target, "结果样本"),
        "source_label": SOURCE_LABELS.get(outcome.window.source_type, "结果样本"),
        "window_name": outcome.window.name or "观察窗口",
        "window_text": _window_text(outcome),
        "matured": outcome.window.matured,
        "can_score": outcome.can_score and outcome.window.source_type == "exchange_native",
        "unscored_label": _unscored_label(outcome),
        "price_result_text": _price_result_text(outcome),
        "collected_at": outcome.window.collected_at or None,
    }


def _window_text(outcome: DecisionOutcome) -> str:
    name = outcome.window.name or "观察窗口"
    if outcome.window.window_start and outcome.window.window_end:
        return f"{name} 已记录"
    return name


def _unscored_label(outcome: DecisionOutcome) -> str:
    if outcome.can_score and outcome.window.source_type == "exchange_native":
        return "-"
    reason = outcome.unscored_reason or outcome.window.unscored_reason
    return UNSCORED_LABELS.get(str(reason), "暂不可评分")


def _price_result_text(outcome: DecisionOutcome) -> str:
    if not outcome.window.matured:
        return "仍在观察"
    if _is_exchange_scorable(outcome):
        return "已形成可评分结果样本"
    return _unscored_label(outcome)


def _is_exchange_scorable(outcome: DecisionOutcome) -> bool:
    return outcome.can_score and outcome.window.source_type == "exchange_native"


def _is_pending(outcome: DecisionOutcome) -> bool:
    return not outcome.window.matured or outcome.unscored_reason in {"pending_outcome", "window_not_matured"}


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
