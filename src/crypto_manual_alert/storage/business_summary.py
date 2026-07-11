from __future__ import annotations

from datetime import datetime, timezone
import json
import math
import re
from typing import Any

from crypto_manual_alert.config import Config


UNSAFE_MODEL_EXCERPT_PATTERN = re.compile(
    r"SQLITE|Traceback|stack trace|/(?:Users|var|private|opt|etc|home|srv|app|tmp|Volumes)/|"
    r"[A-Za-z]:\\|\.db\b|trace_id|request_json|response_json|parsed_plan|payload|"
    r"BARK_DEVICE_KEY|device_key|https://api\.day\.app|Authorization\s*:\s*(?:Basic|Bearer)|Bearer\s+|"
    r"(?:api[_-]?key|secret|access[_-]?token|refresh[_-]?token|token)\s*[:=]|"
    r"candidate\.[a-z0-9_.-]+|production_control\.[a-z0-9_.-]+|choices|chat\.completion|"
    r"passphrase|invalid if|fresh okx mark price",
    re.IGNORECASE,
)


def build_business_summary(
    *,
    plan: dict[str, Any],
    verdict: dict[str, Any],
    config: Config | None = None,
    payload: dict[str, Any] | None = None,
    notification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the user-facing manual alert summary.

    This is a projection of already-computed decision artifacts. It must not
    call providers, mutate journal state, or change gate decisions.
    """

    payload = payload or {}
    instrument = str(plan.get("instrument") or payload.get("trace_symbol") or "UNKNOWN")
    allowed = verdict.get("allowed") is True
    mode_payload = {**payload}
    mode_payload.setdefault("verdict", verdict)
    mode_payload.setdefault("plan", plan)
    actionable_proof_gaps = _actionable_proof_gaps(config=config, payload=mode_payload, notification=notification)
    mode = _run_mode(config=config, payload=mode_payload, actionable_proof_gaps=actionable_proof_gaps)
    fixture_like = mode in {"fixture", "fixture_actionable"}
    reasons = _string_list(verdict.get("reasons"))
    warnings = _string_list(verdict.get("warnings"))
    rule_hits = _rule_hit_messages(verdict.get("rule_hits"))
    facts_gate = _mapping(payload.get("facts_gate"))
    production_gate = _mapping(payload.get("production_control_gate"))
    analysis = _mapping(payload.get("analysis"))

    risk_bullets = _dedupe(
        [
            *_string_list(facts_gate.get("reasons")),
            *_string_list(production_gate.get("reasons")),
            *reasons,
            *rule_hits,
            *warnings,
        ]
    )
    data_gap_bullets = _dedupe(
        [
            *_string_list(analysis.get("data_gaps")),
            *_string_list(facts_gate.get("missing_execution_facts")),
            *_string_list(plan.get("unavailable_data")),
        ]
    )
    reason_bullets = _dedupe(
        [
            str(plan.get("notes") or "").strip(),
            str(plan.get("why_not_opposite") or "").strip(),
            *_string_list(plan.get("invalidation")),
        ]
    )
    evidence_bullets = _evidence_bullets(payload)
    notification_summary = _notification_summary(config=config, notification=notification)
    generation_summary = _generation_summary(config=config, mode=mode, payload=mode_payload)

    return {
        "title": f"{instrument} 手动提醒计划",
        "mode_notice": _mode_notice(config=config, mode=mode, actionable_proof_gaps=actionable_proof_gaps),
        "decision_label": _decision_label(allowed=allowed, mode=mode),
        "action_text": str(plan.get("main_action") or "未明确"),
        "confidence_text": _confidence_text(plan.get("probability")),
        "price_levels": {
            "reference_price": _optional_number(plan.get("reference_price")),
            "entry_trigger": _optional_number(plan.get("entry_trigger")),
            "stop_price": _optional_number(plan.get("stop_price")),
            "target_1": _optional_number(plan.get("target_1")),
            "target_2": _optional_number(plan.get("target_2")),
            "expires_at": plan.get("expires_at"),
        },
        "reason_bullets": reason_bullets or ["本次运行没有生成额外业务理由；请查看工程详情核对 trace。"],
        "risk_bullets": risk_bullets or ["未记录额外阻断理由；仍需人工复核价格、仓位和事件状态。"],
        "evidence_bullets": evidence_bullets or ["未记录可展示证据摘要；默认本地链路不能证明真实市场判断。"],
        "data_gap_bullets": data_gap_bullets,
        "next_steps": _next_steps(allowed=allowed, fixture_like=fixture_like),
        "safety_notice": "系统只生成提醒与审计记录，不自动下单；manual_execution_required 必须保持为 true。",
        "generation_summary": generation_summary,
        "market_data_status": _market_data_status(payload=mode_payload),
        "notification": notification_summary,
    }


def _run_mode(*, config: Config | None, payload: dict[str, Any], actionable_proof_gaps: list[str]) -> str:
    llm_summary = _mapping(payload.get("llm_summary"))
    if _is_mock_llm_summary(llm_summary):
        return "mock_llm"
    if config is not None:
        if _is_mock_llm_config(config):
            return "mock_llm"
        if _is_actionable_gate_ready(config=config, payload=payload):
            return "actionable_local_proof" if actionable_proof_gaps else "actionable_manual_review"
        if llm_summary.get("has_real_llm"):
            return "llm_with_fixture_market" if config.market_data.provider == "fixture" else "real_external"
        if config.decision.engine == "fixture":
            return "fixture"
        if config.market_data.provider == "fixture":
            return "llm_with_fixture_market"
        return "real_external"
    if _is_actionable_gate_ready(config=None, payload=payload):
        return "actionable_local_proof" if actionable_proof_gaps else "actionable_manual_review"
    if llm_summary.get("has_real_llm"):
        return "llm_with_fixture_market" if _payload_has_fixture_market(payload) else "real_external"
    evidence = payload.get("evidence_snapshot")
    if isinstance(evidence, dict) and evidence.get("source") == "fixture":
        return "fixture"
    return "real_external" if _mapping(payload.get("llm_summary")).get("has_real_llm") else "fixture"


def _is_mock_llm_config(config: Config) -> bool:
    return (
        config.decision.engine == "openai_compatible"
        and (
            config.decision.openai_model.startswith("mock-")
            or "127.0.0.1" in config.decision.openai_base_url
            or "localhost" in config.decision.openai_base_url
        )
    )


def _is_mock_llm_summary(summary: dict[str, Any]) -> bool:
    model = str(summary.get("model") or "")
    base_url = str(summary.get("base_url") or "")
    return model.startswith("mock-") or "127.0.0.1" in base_url or "localhost" in base_url


def _payload_has_fixture_market(payload: dict[str, Any]) -> bool:
    snapshot = _mapping(payload.get("snapshot") or payload.get("evidence_snapshot"))
    if snapshot.get("source") == "fixture":
        return True
    points = _mapping(snapshot.get("points"))
    return any(isinstance(point, dict) and point.get("source") == "fixture" for point in points.values())


def _is_actionable_gate_ready(*, config: Config | None, payload: dict[str, Any]) -> bool:
    verdict = _mapping(payload.get("verdict"))
    facts_gate = _mapping(payload.get("facts_gate"))
    production_gate = _mapping(payload.get("production_control_gate"))
    plan = _mapping(payload.get("plan") or payload.get("parsed_plan"))
    if verdict.get("allowed") is not True:
        return False
    if facts_gate.get("passed") is not True or facts_gate.get("severity") == "hard_fail":
        return False
    if facts_gate.get("missing_execution_facts") or facts_gate.get("missing_event_facts"):
        return False
    if production_gate.get("allowed") is not True:
        return False
    if not _snapshot_execution_facts_ready(payload):
        return False
    if plan.get("manual_execution_required") is False:
        return False
    if config is not None:
        return (
            config.trading.manual_execution_required is True
            and config.trading.auto_order_enabled is False
            and config.market_data.provider != "fixture"
        )
    return not _payload_has_fixture_market(payload)


def _actionable_proof_gaps(
    *,
    config: Config | None,
    payload: dict[str, Any],
    notification: dict[str, Any] | None,
) -> list[str]:
    if not _is_actionable_gate_ready(config=config, payload=payload):
        return []
    gaps: list[str] = []
    llm_summary = _mapping(payload.get("llm_summary"))
    if not _has_successful_real_llm(llm_summary):
        if llm_summary.get("has_real_llm"):
            gaps.append("真实外部模型未返回成功")
        else:
            gaps.append("真实外部模型成功返回")
    if not _payload_has_real_okx_market(payload):
        gaps.append("真实 OKX public 行情证据")
    if not _payload_has_complete_no_active_event_assertion(payload):
        gaps.append("完整且未过期的 no_active_event 人工断言")
    if notification is None or notification.get("ok") is not True:
        gaps.append("通知未证明生产成功")
    if config is None:
        gaps.append("运行配置投影")
    else:
        if not _config_prod_actionable_ready(config):
            gaps.append("严格生产 readiness")
        if config.decision.final_input_mode != "legacy_prompt":
            gaps.append("decision.final_input_mode=legacy_prompt")
        if config.decision.candidate_sidecar_mode != "disabled":
            gaps.append("candidate_sidecar_mode=disabled")
        if config.workflow.execution_mode != "legacy_baseline":
            gaps.append("workflow.execution_mode=legacy_baseline")
        if config.trading.manual_execution_required is not True:
            gaps.append("manual_execution_required=true")
        if config.trading.auto_order_enabled is not False:
            gaps.append("auto_order_enabled=false")
    return _dedupe(gaps)


def _has_successful_real_llm(llm_summary: dict[str, Any]) -> bool:
    return (
        llm_summary.get("has_real_llm") is True
        and str(llm_summary.get("status") or "").strip() == "ok"
        and not _is_mock_llm_summary(llm_summary)
    )


def _payload_has_real_okx_market(payload: dict[str, Any]) -> bool:
    return _snapshot_execution_facts_ready(payload)


def _snapshot_execution_facts_ready(payload: dict[str, Any]) -> bool:
    snapshot = _mapping(payload.get("snapshot") or payload.get("evidence_snapshot"))
    points = _mapping(snapshot.get("points"))
    for name in ("mark", "index", "order_book"):
        point = _mapping(points.get(name))
        if point.get("source") != "okx_public":
            return False
        if not _market_item_value_is_usable(name=name, value=point.get("value")):
            return False
    return True


def _payload_has_complete_no_active_event_assertion(payload: dict[str, Any]) -> bool:
    snapshot = _mapping(payload.get("snapshot") or payload.get("evidence_snapshot"))
    points = _mapping(snapshot.get("points"))
    event_point = _mapping(points.get("active_event_status"))
    event_value = _mapping(event_point.get("value"))
    valid_until = str(event_value.get("valid_until") or "").strip()
    return (
        event_value.get("status") == "no_active_event"
        and event_value.get("provider") == "no_active_event"
        and event_value.get("metadata_complete") is True
        and _future_iso_datetime(valid_until)
    )


def _future_iso_datetime(value: str) -> bool:
    if not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    if parsed.tzinfo is None:
        return False
    return parsed > datetime.now(timezone.utc)


def _config_prod_actionable_ready(config: Config) -> bool:
    readiness = config.safe_dict().get("readiness")
    if not isinstance(readiness, dict):
        return False
    prod_actionable = readiness.get("prod_actionable")
    return isinstance(prod_actionable, dict) and prod_actionable.get("prod_actionable_ready") is True


def _mode_notice(*, config: Config | None, mode: str, actionable_proof_gaps: list[str]) -> str:
    if mode == "mock_llm":
        return "当前为 mock LLM 路径：本地模拟 OpenAI-compatible 接口，已验证 LLM 调用/解析/记录链路，但不是真实外部模型结论。"
    if mode == "actionable_local_proof":
        gap_text = "；".join(actionable_proof_gaps) if actionable_proof_gaps else "生产证据未完整持久化"
        return (
            "当前为本地/预发证明（人工复核门槛）：行情执行事实与事件状态可支持本次人工复核；"
            "系统只生成提醒，不会自动下单。该结果不是生产成功；"
            f"仍需补齐或核对：{gap_text}。"
        )
    if mode == "actionable_manual_review":
        if config is not None and _has_incomplete_no_active_event_assertion(config):
            return (
                "当前已满足本地/预发人工复核门槛：行情执行事实与事件状态已通过检查；"
                "系统只生成提醒，不会自动下单。该结果是本地/预发证明，不是生产成功；"
                "生产门禁仍需真实外部模型、真实 OKX、Bark 发送成功和完整未过期事件断言。"
            )
        return "当前已满足人工复核门槛：真实外部模型、真实 OKX、事件断言和 Bark 发送证据均已记录；系统只生成提醒，不会自动下单。"
    if mode == "llm_with_fixture_market" and config is not None:
        return f"当前配置使用 {config.decision.engine} 决策引擎，但行情仍为 fixture；本次只证明模型调用链路，不证明真实市场判断。"
    if config is not None and config.decision.engine != "fixture":
        return f"当前配置使用 {config.decision.engine} 决策引擎；请在工程详情核对 LLM 与 provider 记录。"
    if mode == "fixture":
        return "当前为本地样本/规则模式，本次未调用真实 LLM；结果仅用于流程验证。"
    return "本次运行记录了非 fixture provider；仍需人工核对证据与风控结果。"


def _has_incomplete_no_active_event_assertion(config: Config) -> bool:
    return config.macro_event.provider == "no_active_event" and bool(
        config.macro_event.missing_no_active_event_metadata_envs()
    )


def _decision_label(*, allowed: bool, mode: str) -> str:
    if mode in {"actionable_manual_review", "actionable_local_proof"}:
        return "可人工复核" if allowed else "已阻断"
    if mode == "fixture":
        return "本地样本"
    if mode == "mock_llm":
        return "模拟 LLM"
    if mode == "llm_with_fixture_market":
        return "模型链路验证"
    return "可人工复核" if allowed else "已阻断"


def _confidence_text(value: Any) -> str:
    number = _optional_number(value)
    if number is None:
        return "未给出概率"
    if number >= 0.65:
        label = "高"
    elif number >= 0.55:
        label = "中"
    else:
        label = "低"
    return f"{label}（{number * 100:.0f}%）"


def _notification_summary(*, config: Config | None, notification: dict[str, Any] | None) -> dict[str, Any]:
    if notification:
        ok = notification.get("ok") is True
        return {
            "enabled": True,
            "channel": notification.get("channel") or (config.notification.provider if config else None),
            "status": "sent" if ok else "failed",
            "status_code": notification.get("status_code"),
            "sent_at": notification.get("created_at"),
            "error": notification.get("error"),
            "message": "Bark 已发送。" if ok else f"发送失败：{notification.get('error') or '未知错误'}",
        }
    if config is None or not config.notification.enabled:
        return {
            "enabled": False,
            "channel": config.notification.provider if config else None,
            "status": "disabled",
            "message": "通知未启用；本次只写入运行记录。",
        }
    return {
        "enabled": True,
        "channel": config.notification.provider,
        "status": "not_recorded",
        "message": "通知已启用；请在通知记录中确认是否发送成功。",
    }


def _generation_summary(*, config: Config | None, mode: str, payload: dict[str, Any]) -> dict[str, Any]:
    llm_summary = _mapping(payload.get("llm_summary"))
    llm_return_recorded = _llm_return_recorded(llm_summary)
    provider = str(llm_summary.get("provider") or "").strip()
    model = llm_summary.get("model")
    if config is not None and config.decision.engine != "fixture":
        provider = provider or config.decision.engine
        model = model or config.decision.openai_model
    model_text = str(model).strip() if model not in (None, "") else None
    provider_label = _provider_label(provider)
    status = str(llm_summary.get("status") or "").strip()
    duration_ms = _optional_number(llm_summary.get("duration_ms"))
    total_tokens = _optional_number(llm_summary.get("total_tokens"))
    status_label = _generation_status_label(
        mode=mode,
        status=status,
        model=model_text,
        provider=provider,
        llm_return_recorded=llm_return_recorded,
    )
    response_summary = _generation_response_summary(
        mode=mode,
        status=status,
        model=model_text,
        provider=provider,
        llm_summary=llm_summary,
        plan=_mapping(payload.get("plan") or payload.get("parsed_plan")),
        llm_return_recorded=llm_return_recorded,
    )
    raw_completion_excerpt = safe_llm_completion_excerpt(
        llm_summary.get("completion_excerpt") or llm_summary.get("output_summary")
    )
    detail_bullets = _generation_detail_bullets(
        mode=mode,
        provider_label=provider_label,
        model=model_text,
        status_label=status_label,
        duration_text=_duration_text(duration_ms),
        token_text=_token_text(total_tokens),
    )
    return {
        "mode_label": _generation_mode_label(
            mode=mode,
            provider=provider,
            model=model_text,
            llm_return_recorded=llm_return_recorded,
        ),
        "provider": provider or None,
        "provider_label": provider_label,
        "model": model_text,
        "status": status or None,
        "status_label": status_label,
        "duration_text": _duration_text(duration_ms),
        "token_text": _token_text(total_tokens),
        "finish_reason": str(llm_summary.get("finish_reason") or "").strip() or None,
        "response_summary": response_summary,
        "raw_completion_label": "模型原始返回摘录",
        "raw_completion_excerpt": raw_completion_excerpt,
        "detail_bullets": detail_bullets,
    }


def _llm_return_recorded(llm_summary: dict[str, Any]) -> bool:
    return any(
        key in llm_summary and llm_summary.get(key) not in (None, "", {})
        for key in ("status", "output_summary", "duration_ms", "total_tokens", "finish_reason")
    )


def _generation_mode_label(*, mode: str, provider: str, model: str | None, llm_return_recorded: bool) -> str:
    if mode == "fixture":
        return "本地演练"
    if mode == "mock_llm":
        return "模型链路演练"
    if mode == "llm_with_fixture_market":
        return "模型链路验证"
    if (provider or model) and not llm_return_recorded:
        return "模型配置已启用"
    if provider or model:
        return "真实模型链路"
    if mode in {"actionable_manual_review", "actionable_local_proof"}:
        return "人工复核链路"
    return "真实模型链路"


def _generation_status_label(
    *,
    mode: str,
    status: str,
    model: str | None,
    provider: str,
    llm_return_recorded: bool,
) -> str:
    if mode == "fixture" and not model and not provider:
        return "未调用外部模型"
    if status == "ok":
        return "模型已返回"
    if status in {"error", "failed"}:
        return "模型调用失败"
    if (model or provider) and not llm_return_recorded:
        return "本次未记录模型返回"
    if model or provider:
        return "模型状态已记录"
    return "未调用外部模型"


def _generation_response_summary(
    *,
    mode: str,
    status: str,
    model: str | None,
    provider: str,
    llm_summary: dict[str, Any],
    plan: dict[str, Any],
    llm_return_recorded: bool,
) -> str:
    if mode == "fixture" and not model and not provider:
        return "使用本地样本计划，未产生真实模型返回。"
    if (model or provider) and not llm_return_recorded:
        return "模型配置已启用，但本次运行没有持久化可展示的模型返回；请以提醒动作、价格和风险面板为准。"
    if status == "ok":
        output_excerpt = _safe_llm_output_excerpt(llm_summary.get("output_summary"))
        if output_excerpt:
            return output_excerpt
        plan_excerpt = _safe_plan_excerpt(plan)
        if plan_excerpt:
            return plan_excerpt
        return "模型返回已记录，但当前摘要缺少可安全展示的模型结论；请以提醒动作、价格和风险面板为准。"
    if status in {"error", "failed"}:
        return "模型调用失败，已记录错误摘要；不能作为成功提醒。"
    return "生成链路状态已记录，但本次没有可安全展示的模型结论；请以提醒动作、价格和风险面板为准。"


def _safe_llm_output_excerpt(output_summary: Any) -> str | None:
    if isinstance(output_summary, str):
        return _safe_business_excerpt(output_summary)
    if not isinstance(output_summary, dict):
        return None
    for key in ("summary", "response_summary", "model_summary", "decision_summary", "conclusion", "rationale"):
        text = _safe_business_excerpt(output_summary.get(key))
        if text:
            return text

    action = _safe_business_excerpt(output_summary.get("main_action") or output_summary.get("action"))
    probability = _optional_number(_first_present(output_summary, "probability", "confidence"))
    invalidation = _safe_business_excerpt(output_summary.get("invalidation") or output_summary.get("invalid_if"))
    if action:
        return _join_model_excerpt(action=action, probability=probability, invalidation=invalidation)
    return None


def safe_llm_completion_excerpt(output_summary: Any) -> str | None:
    if isinstance(output_summary, str):
        return _safe_completion_text(output_summary)
    if not isinstance(output_summary, dict):
        return None
    direct = _safe_llm_output_excerpt(output_summary)
    if direct:
        return direct

    choices = output_summary.get("choices")
    if isinstance(choices, list):
        for choice in choices:
            choice_mapping = _mapping(choice)
            message = _mapping(choice_mapping.get("message"))
            text = _safe_completion_text(message.get("content"))
            if text:
                return text
            delta = _mapping(choice_mapping.get("delta"))
            text = _safe_completion_text(delta.get("content"))
            if text:
                return text

    output = output_summary.get("output")
    if isinstance(output, list):
        for item in output:
            item_mapping = _mapping(item)
            text = _safe_completion_text(item_mapping.get("output_text") or item_mapping.get("text"))
            if text:
                return text
            content = item_mapping.get("content")
            if isinstance(content, list):
                for content_item in content:
                    content_mapping = _mapping(content_item)
                    text = _safe_completion_text(content_mapping.get("text") or content_mapping.get("output_text"))
                    if text:
                        return text

    return _safe_completion_text(output_summary.get("output_text"))


def _safe_completion_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.strip().split())
    if not text:
        return None
    parsed = _parse_json_completion(text)
    if isinstance(parsed, dict):
        parsed_excerpt = _safe_llm_output_excerpt(parsed)
        if parsed_excerpt:
            return parsed_excerpt
        return None
    return _safe_business_excerpt(text)


def _parse_json_completion(text: str) -> Any | None:
    if not ((text.startswith("{") and text.endswith("}")) or (text.startswith("[") and text.endswith("]"))):
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _safe_plan_excerpt(plan: dict[str, Any]) -> str | None:
    action = _safe_business_excerpt(plan.get("main_action") or plan.get("action"))
    probability = _optional_number(plan.get("probability"))
    invalidation = _safe_business_excerpt(plan.get("invalidation"))
    if action:
        return _join_model_excerpt(
            action=action,
            probability=probability,
            invalidation=invalidation,
        )
    return None


def _join_model_excerpt(
    *,
    action: str,
    probability: float | None,
    invalidation: str | None,
    reason: str | None = None,
) -> str:
    parts = [f"模型结论：{_action_label(action)}"]
    if probability is not None:
        parts.append(f"置信度 {probability * 100:.0f}%")
    if invalidation:
        parts.append(f"失效条件：{_trim_clause_punctuation(invalidation)}")
    elif reason:
        parts.append(f"关键理由：{_trim_clause_punctuation(reason)}")
    return "；".join(parts) + "。"


def _action_label(value: str) -> str:
    labels = {
        "trigger long": "触发做多",
        "trigger short": "触发做空",
        "open long": "开多",
        "open short": "开空",
        "hold long": "持有多单",
        "hold short": "持有空单",
        "close long": "平多",
        "close short": "平空",
        "flip long to short": "多翻空",
        "flip short to long": "空翻多",
        "no trade": "暂不操作",
    }
    return labels.get(value.strip().lower(), value)


def _trim_clause_punctuation(value: str) -> str:
    return value.rstrip("。.;； ")


def _safe_business_excerpt(value: Any) -> str | None:
    if isinstance(value, list):
        parts = [_safe_business_excerpt(item) for item in value]
        text = "；".join(part for part in parts if part)
        return text or None
    if not isinstance(value, str):
        return None
    text = " ".join(value.strip().split())
    if not text:
        return None
    if UNSAFE_MODEL_EXCERPT_PATTERN.search(text):
        return None
    if len(text) > 180:
        return text[:177].rstrip() + "..."
    return text


def _generation_detail_bullets(
    *,
    mode: str,
    provider_label: str | None,
    model: str | None,
    status_label: str,
    duration_text: str | None,
    token_text: str | None,
) -> list[str]:
    bullets: list[str] = []
    if mode == "fixture":
        bullets.append("本次使用本地样本计划，适合验证流程与页面，不代表真实模型结论。")
    elif mode == "mock_llm":
        bullets.append("本次调用本地模拟模型接口，只证明模型调用、解析和记录链路。")
    elif mode == "llm_with_fixture_market":
        bullets.append("本次有模型链路记录，但行情仍包含本地样本，不能证明真实市场判断。")
    elif mode == "actionable_local_proof":
        bullets.append("本次为本地/预发人工复核证明，不能当作生产成功证明。")
    else:
        bullets.append("本次生成链路记录了模型调用摘要；仍需人工核对事实、风险和通知状态。")
    if provider_label:
        bullets.append(f"模型接口：{provider_label}。")
    if model:
        bullets.append(f"模型：{model}。")
    bullets.append(f"状态：{status_label}。")
    if duration_text:
        bullets.append(f"耗时：{duration_text}。")
    if token_text:
        bullets.append(f"Token：{token_text}。")
    bullets.append("产品页不展示原始请求、原始返回或密钥字段。")
    return bullets


def _provider_label(provider: str) -> str | None:
    if not provider:
        return None
    if provider == "openai_compatible":
        return "OpenAI-compatible"
    if provider == "fixture":
        return None
    return provider.replace("_", " ")


MARKET_STATUS_SPECS = (
    ("ticker", "最新成交", ("last", "bid", "ask"), False),
    ("mark", "标记价", ("mark",), True),
    ("index", "指数价", ("index",), True),
    ("funding_rate", "资金费率", ("funding_rate",), False),
    ("open_interest", "未平仓量", ("open_interest",), False),
    ("order_book", "订单簿", ("order_book",), True),
    ("candles", "K 线", ("candles",), False),
)


def _market_data_status(*, payload: dict[str, Any]) -> dict[str, Any]:
    snapshot = _mapping(payload.get("snapshot") or payload.get("evidence_snapshot"))
    points = _mapping(snapshot.get("points"))
    unavailable = _unavailable_by_name(snapshot.get("unavailable"))
    provider = _market_provider(snapshot=snapshot, points=points)
    items = [
        _market_status_item(
            name=name,
            label=label,
            point_names=point_names,
            can_satisfy_execution_fact=can_satisfy_execution_fact,
            points=points,
            unavailable=unavailable,
        )
        for name, label, point_names, can_satisfy_execution_fact in MARKET_STATUS_SPECS
    ]
    failed = [item for item in items if item["status"] == "failed"]
    ok = [item for item in items if item["status"] == "ok"]
    missing = [item for item in items if item["status"] == "missing"]
    execution_facts_ready = _execution_facts_ready(items=items, payload=payload)
    return {
        "provider": provider,
        "provider_label": _market_provider_label(provider),
        "symbol": _safe_business_excerpt(snapshot.get("symbol")),
        "summary": _market_status_summary(
            provider=provider,
            ok_count=len(ok),
            failed_count=len(failed),
            missing_count=len(missing),
            execution_facts_ready=execution_facts_ready,
            payload=payload,
        ),
        "execution_facts_ready": execution_facts_ready,
        "success_count": len(ok),
        "failed_count": len(failed),
        "missing_count": len(missing),
        "items": items,
        "failures": [
            {
                "name": item["name"],
                "label": item["label"],
                "error_type": item.get("error_type"),
                "reason": item.get("failure_reason"),
            }
            for item in failed
        ],
    }


def _market_status_item(
    *,
    name: str,
    label: str,
    point_names: tuple[str, ...],
    can_satisfy_execution_fact: bool,
    points: dict[str, Any],
    unavailable: dict[str, str],
) -> dict[str, Any]:
    selected = [_mapping(points.get(point_name)) for point_name in point_names if isinstance(points.get(point_name), dict)]
    point = selected[0] if selected else {}
    source = str(point.get("source") or "").strip() or None
    value = _first_market_value(points=points, point_names=point_names)
    error_type = unavailable.get(name)
    if error_type:
        status = "failed"
    elif selected and not _market_item_value_is_usable(name=name, value=value):
        status = "failed"
        error_type = "InvalidPayload"
    elif selected:
        status = "ok"
    else:
        status = "missing"
    return {
        "name": name,
        "label": label,
        "status": status,
        "status_label": _market_item_status_label(status),
        "source": source,
        "source_label": _market_provider_label(source),
        "can_satisfy_execution_fact": can_satisfy_execution_fact,
        "value_text": _market_value_text(value),
        "error_type": error_type,
        "failure_reason": f"{label} 获取失败：{error_type}" if error_type else None,
    }


def _market_item_value_is_usable(*, name: str, value: Any) -> bool:
    if name in {"mark", "index"}:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))
    if name == "order_book":
        if not isinstance(value, dict):
            return False
        asks = value.get("asks")
        bids = value.get("bids")
        return _book_side_is_usable(asks) and _book_side_is_usable(bids)
    if isinstance(value, (list, dict, tuple, set)):
        return bool(value)
    return value is not None


def _book_side_is_usable(value: Any) -> bool:
    if not isinstance(value, list) or not value:
        return False
    return all(
        isinstance(level, (list, tuple))
        and len(level) >= 2
        and _is_positive_finite_number(level[0])
        and _is_positive_finite_number(level[1])
        for level in value
    )


def _is_positive_finite_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and number > 0


def _market_provider(*, snapshot: dict[str, Any], points: dict[str, Any]) -> str | None:
    source = str(snapshot.get("source") or "").strip()
    if source:
        return source
    sources = [
        str(_mapping(point).get("source") or "").strip()
        for point in points.values()
        if isinstance(point, dict) and str(_mapping(point).get("source") or "").strip()
    ]
    if not sources:
        return None
    if "okx_public" in sources:
        return "okx_public"
    if "fixture" in sources:
        return "fixture"
    return sources[0]


def _market_provider_label(provider: str | None) -> str | None:
    if not provider:
        return None
    if provider == "okx_public":
        return "OKX public"
    if provider == "fixture":
        return "本地样本"
    return provider.replace("_", " ")


def _market_status_summary(
    *,
    provider: str | None,
    ok_count: int,
    failed_count: int,
    missing_count: int,
    execution_facts_ready: bool,
    payload: dict[str, Any],
) -> str:
    provider_label = _market_provider_label(provider) or "行情"
    parts = [f"{provider_label} 行情：成功 {ok_count} 项，失败 {failed_count} 项，缺失 {missing_count} 项"]
    if execution_facts_ready:
        parts.append("执行事实已具备，可进入人工复核前检查")
    else:
        missing_facts = _string_list(_mapping(payload.get("facts_gate")).get("missing_execution_facts"))
        if missing_facts:
            missing_label = "交易所原生 " if provider != "okx_public" else ""
            parts.append(f"执行事实不完整：缺少{missing_label}{'、'.join(missing_facts)}")
        else:
            parts.append("执行事实不完整：需要 OKX public 标记价、指数价和订单簿")
    return "；".join(parts) + "。"


def _execution_facts_ready(*, items: list[dict[str, Any]], payload: dict[str, Any]) -> bool:
    facts_gate = _mapping(payload.get("facts_gate"))
    if _string_list(facts_gate.get("missing_execution_facts")):
        return False
    by_name = {item["name"]: item for item in items}
    for name in ("mark", "index", "order_book"):
        item = by_name.get(name) or {}
        if item.get("status") != "ok" or item.get("source") != "okx_public":
            return False
    return True


def _unavailable_by_name(value: Any) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in _string_list(value):
        name, _, reason = item.partition(":")
        key = name.strip()
        if not key:
            continue
        result[key] = _safe_error_type(reason)
    return result


def _safe_error_type(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "Unavailable"
    match = re.search(r"[A-Za-z][A-Za-z0-9_]*(?:Error|Timeout|Exception|Unavailable|Failure|Failed)?", text)
    if not match:
        return "Unavailable"
    token = match.group(0)
    if UNSAFE_MODEL_EXCERPT_PATTERN.search(token):
        return "Unavailable"
    return token[:80]


def _first_market_value(*, points: dict[str, Any], point_names: tuple[str, ...]) -> Any:
    for point_name in point_names:
        point = _mapping(points.get(point_name))
        if "value" in point:
            return point.get("value")
    return None


def _market_value_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, float):
        return f"{value:g}"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return _safe_business_excerpt(value)
    if isinstance(value, dict):
        return "已记录结构化数据"
    if isinstance(value, list):
        return f"已记录 {len(value)} 条"
    return _safe_business_excerpt(str(value))


def _market_item_status_label(status: str) -> str:
    if status == "ok":
        return "成功"
    if status == "failed":
        return "失败"
    return "缺失"


def _duration_text(value: float | None) -> str | None:
    if value is None:
        return None
    return f"{value:.0f} ms"


def _token_text(value: float | None) -> str | None:
    if value is None:
        return None
    return f"{value:.0f} tokens"


def _next_steps(*, allowed: bool, fixture_like: bool) -> list[str]:
    steps: list[str] = []
    if fixture_like:
        steps.append("当前只是本地流程验证，不要作为真实市场操作依据。")
    if allowed:
        steps.append("人工核对价格、事件状态、仓位风险后再手动执行。")
    else:
        steps.append("已阻断，需补齐缺失事实或调整配置后重新评估。")
    steps.append("系统不自动下单；所有操作必须由人工在交易所手动完成。")
    return steps


def _evidence_bullets(payload: dict[str, Any]) -> list[str]:
    bullets: list[str] = []
    snapshot = _mapping(payload.get("evidence_snapshot") or payload.get("snapshot"))
    if snapshot.get("source"):
        bullets.append(f"行情来源：{snapshot.get('source')}")
    if snapshot.get("symbol"):
        bullets.append(f"行情标的：{snapshot.get('symbol')}")
    event_bullet = _event_status_bullet(snapshot)
    if event_bullet:
        bullets.append(event_bullet)
    research = _mapping(payload.get("research"))
    if research:
        bullets.append("已记录 research audit，可在工程详情核对。")
    return bullets


def _event_status_bullet(snapshot: dict[str, Any]) -> str:
    points = _mapping(snapshot.get("points"))
    event_point = _mapping(points.get("active_event_status"))
    event_value = _mapping(event_point.get("value"))
    if event_value.get("status") != "no_active_event":
        return ""
    if event_value.get("metadata_complete") is False:
        return "无活跃宏观事件人工断言已记录，但元数据不完整，不能作为生产证明。"
    operator_ref = str(event_value.get("operator_ref") or "未记录确认人")
    source_ref = str(event_value.get("source_ref") or "未记录依据")
    valid_until = str(event_value.get("valid_until") or "未记录有效期")
    horizon = str(event_value.get("horizon") or "未记录窗口")
    return (
        "人工确认无活跃宏观事件："
        f"确认人 {operator_ref}，依据 {source_ref}，适用窗口 {horizon}，有效期至 {valid_until}。"
    )


def _rule_hit_messages(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    messages: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        message = item.get("message") or item.get("rule_id")
        if message:
            messages.append(str(message))
    return messages


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)] if str(value).strip() else []


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _optional_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_present(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping:
            return mapping.get(key)
    return None


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        text = str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result
