"""LLM-as-Judge - G-Eval 方法实现，4 维度评分。

来源：V2重构方案评审与补充建议_修订版.md 第 6.3 节。

Judge 模型：GPT-4o 或 Claude Sonnet（与生产模型不同，避免 self-enhancement bias），
temperature=0。

4 维度评分：
1. 方向准确性 (1-5 分)
2. 风险控制 (1-5 分)
3. 证据引用 (1-5 分)
4. 可执行性 (1-5 分)

G-Eval 方法：先给出每个维度的评分理由（CoT），然后给出 1-5 分评分。
"""

from typing import Any

from pydantic import BaseModel, Field


# ===========================================================================
# Judge Prompt 模板（从设计文档复制）
# ===========================================================================

JUDGE_PROMPT = """你是一个加密货币市场分析质量评审专家。请按照以下标准评估分析报告的质量。

## 分析报告
{analysis_output}

## 参考答案
{reference_answer}

## 评估维度

### 1. 方向准确性 (1-5分)
- 5分：方向完全正确，与参考答案一致
- 4分：方向基本正确，但置信度偏差较大
- 3分：方向模糊或部分正确
- 2分：方向错误但有合理推理
- 1分：方向完全错误

### 2. 风险控制 (1-5分)
- 5分：止损、入场区间、失效条件完整且合理
- 4分：大部分风控要素完整
- 3分：部分风控要素缺失
- 2分：风控要素严重不足
- 1分：无风控要素

### 3. 证据引用 (1-5分)
- 5分：引用了所有必需证据且推理逻辑清晰
- 4分：引用了大部分必需证据
- 3分：引用了部分证据但逻辑有跳跃
- 2分：证据引用不足
- 1分：无证据引用

### 4. 可执行性 (1-5分)
- 5分：manual_execution_required=true，参数完整可执行
- 4分：大部分参数完整
- 3分：部分参数缺失
- 2分：参数严重不足
- 1分：无法执行

## 请先给出每个维度的评分理由（CoT），然后给出1-5分评分。
"""


# ===========================================================================
# 评分结果 Schema
# ===========================================================================

class DimensionScore(BaseModel):
    """单维度评分。"""
    score: int = Field(ge=1, le=5, description="1-5 分")
    reasoning: str = Field(description="评分理由（CoT）")


class JudgeResult(BaseModel):
    """Judge 完整评分结果。"""
    direction_accuracy: DimensionScore = Field(description="方向准确性")
    risk_control: DimensionScore = Field(description="风险控制")
    evidence_citation: DimensionScore = Field(description="证据引用")
    executability: DimensionScore = Field(description="可执行性")
    overall_score: float = Field(description="4 维度平均分（1-5）")

    def compute_overall(self) -> float:
        """计算 4 维度平均分。"""
        scores = [
            self.direction_accuracy.score,
            self.risk_control.score,
            self.evidence_citation.score,
            self.executability.score,
        ]
        return sum(scores) / len(scores)


# ===========================================================================
# G-Eval 实现
# ===========================================================================

def format_judge_prompt(
    analysis_output: dict[str, Any] | str,
    reference_answer: dict[str, Any] | str,
) -> str:
    """格式化 Judge prompt。

    analysis_output 和 reference_answer 可以是 dict（MarketAnalysis）或 str（文本）。
    """
    if isinstance(analysis_output, dict):
        analysis_str = _format_analysis(analysis_output)
    else:
        analysis_str = analysis_output

    if isinstance(reference_answer, dict):
        reference_str = _format_reference(reference_answer)
    else:
        reference_str = reference_answer

    return JUDGE_PROMPT.format(
        analysis_output=analysis_str,
        reference_answer=reference_str,
    )


def _format_analysis(analysis: dict[str, Any]) -> str:
    """格式化分析报告为可读文本。"""
    lines = [
        f"动作: {analysis.get('main_action', 'N/A')}",
        f"标的: {analysis.get('instrument', 'N/A')}",
        f"周期: {analysis.get('horizon', 'N/A')}",
        f"参考价: {analysis.get('reference_price', 'N/A')}",
        f"入场触发: {analysis.get('entry_trigger', 'N/A')}",
        f"止损: {analysis.get('stop_price', 'N/A')}",
        f"目标1: {analysis.get('target_1', 'N/A')}",
        f"胜率: {analysis.get('probability', 'N/A')}",
        f"杠杆: {analysis.get('max_leverage', 'N/A')}",
        f"风险占比: {analysis.get('risk_pct', 'N/A')}",
        f"手动执行: {analysis.get('manual_execution_required', 'N/A')}",
        f"根因链: {analysis.get('root_cause_chain', 'N/A')}",
        f"反向审查: {analysis.get('why_not_opposite', 'N/A')}",
        f"失效条件: {analysis.get('invalidation', 'N/A')}",
    ]
    return "\n".join(lines)


def _format_reference(reference: dict[str, Any]) -> str:
    """格式化参考答案为可读文本。"""
    lines = [
        f"期望方向: {reference.get('expected_direction', 'N/A')}",
        f"期望置信度范围: {reference.get('expected_confidence_range', 'N/A')}",
        f"期望风控拦截: {reference.get('expected_risk_blocked', 'N/A')}",
        f"期望风控规则命中: {reference.get('expected_risk_rules_hit', 'N/A')}",
        f"必需证据: {reference.get('must_include_evidence', 'N/A')}",
        f"禁止包含: {reference.get('must_not_include', 'N/A')}",
        f"关键检查: {reference.get('key_checks', 'N/A')}",
    ]
    return "\n".join(lines)


async def run_judge(
    analysis_output: dict[str, Any] | str,
    reference_answer: dict[str, Any] | str,
    model_name: str = "gpt-4o",
    api_key: str | None = None,
    base_url: str | None = None,
) -> JudgeResult:
    """执行 LLM-as-Judge 评分。

    使用 G-Eval 方法：先 CoT 推理，再评分。
    使用 response_format=JudgeResult 强制结构化输出。

    Args:
        analysis_output: 分析报告（dict 或 str）
        reference_answer: 参考答案（dict 或 str）
        model_name: Judge 模型名（默认 gpt-4o）
        api_key: OpenAI API key（默认从 settings 读取）
        base_url: OpenAI base URL（默认从 settings 读取）

    Returns:
        JudgeResult: 4 维度评分结果
    """
    from langchain_openai import ChatOpenAI

    from crypto_alert_v2.config import settings

    prompt = format_judge_prompt(analysis_output, reference_answer)

    llm = ChatOpenAI(
        model=model_name,
        temperature=0,
        api_key=api_key or settings.openai_api_key,
        base_url=base_url or settings.openai_base_url,
    )

    # 使用 structured output 强制输出 JudgeResult
    structured_llm = llm.with_structured_output(JudgeResult)
    result = await structured_llm.ainvoke(prompt)

    # 计算总分
    result.overall_score = result.compute_overall()
    return result


def run_judge_sync(
    analysis_output: dict[str, Any] | str,
    reference_answer: dict[str, Any] | str,
    model_name: str = "gpt-4o",
    api_key: str | None = None,
    base_url: str | None = None,
) -> JudgeResult:
    """同步版本的 LLM-as-Judge 评分。

    在非 async 上下文中使用。
    """
    import asyncio

    return asyncio.run(
        run_judge(
            analysis_output=analysis_output,
            reference_answer=reference_answer,
            model_name=model_name,
            api_key=api_key,
            base_url=base_url,
        )
    )


# ===========================================================================
# 确定性评估器（非 LLM）
# ===========================================================================

def evaluate_direction(
    analysis: dict[str, Any],
    expected_direction: str,
) -> bool:
    """确定性方向检查（不使用 LLM）。

    比较分析结果中的 main_action 推导方向与期望方向。
    """
    action = analysis.get("main_action", "no_trade")
    derived = _derive_direction(action)
    return derived == expected_direction


def _derive_direction(action: str) -> str:
    """从 main_action 派生方向。"""
    action = action.lower()
    long_actions = {"open_long", "hold_long", "trigger_long", "flip_short_to_long"}
    short_actions = {"open_short", "hold_short", "trigger_short", "flip_long_to_short"}
    if action in long_actions:
        return "long"
    if action in short_actions:
        return "short"
    return "neutral"


def evaluate_risk_rules(
    analysis: dict[str, Any],
    expected_blocked: bool,
    expected_rules_hit: list[str],
    actual_blocked: bool,
    actual_rules_hit: list[str],
) -> dict[str, Any]:
    """确定性风控规则检查。"""
    return {
        "blocked_match": expected_blocked == actual_blocked,
        "rules_match": set(expected_rules_hit) == set(actual_rules_hit),
        "expected_blocked": expected_blocked,
        "actual_blocked": actual_blocked,
        "expected_rules": expected_rules_hit,
        "actual_rules": actual_rules_hit,
    }


def evaluate_evidence_coverage(
    analysis: dict[str, Any],
    must_include: list[str],
    must_not_include: list[str],
) -> dict[str, Any]:
    """确定性证据覆盖检查。"""
    analysis_text = str(analysis)
    missing = [e for e in must_include if e not in analysis_text]
    forbidden_present = [e for e in must_not_include if e in analysis_text]
    return {
        "all_evidence_included": len(missing) == 0,
        "missing_evidence": missing,
        "forbidden_present": forbidden_present,
        "pass": len(missing) == 0 and len(forbidden_present) == 0,
    }


def evaluate_schema_completeness(analysis: dict[str, Any]) -> dict[str, Any]:
    """结构化输出完整性检查。"""
    required_fields = [
        "main_action", "instrument", "horizon", "reference_price",
        "probability", "max_leverage", "risk_pct", "root_cause_chain",
        "why_not_opposite", "invalidation", "manual_execution_required",
        "expires_in_seconds",
    ]
    missing = [f for f in required_fields if f not in analysis or analysis[f] is None]
    return {
        "complete": len(missing) == 0,
        "missing_fields": missing,
    }


# ===========================================================================
# 校准辅助
# ===========================================================================

def calculate_agreement(
    judge_scores: list[float],
    human_scores: list[float],
    tolerance: float = 1.0,
) -> dict[str, float]:
    """计算 Judge 与人工评分的一致性。

    Args:
        judge_scores: Judge 评分列表
        human_scores: 人工评分列表
        tolerance: 容差（差值在此范围内视为一致）

    Returns:
        包含 agreement_rate 和 spearman_correlation 的字典
    """
    if len(judge_scores) != len(human_scores) or len(judge_scores) == 0:
        return {"agreement_rate": 0.0, "spearman_correlation": 0.0}

    # 一致率
    agreements = sum(
        1 for j, h in zip(judge_scores, human_scores) if abs(j - h) <= tolerance
    )
    agreement_rate = agreements / len(judge_scores)

    # Spearman 相关系数（简化实现）
    spearman = _spearman_correlation(judge_scores, human_scores)

    return {
        "agreement_rate": agreement_rate,
        "spearman_correlation": spearman,
    }


def _spearman_correlation(x: list[float], y: list[float]) -> float:
    """计算 Spearman 等级相关系数（简化实现）。"""
    n = len(x)
    if n < 2:
        return 0.0

    # 计算等级
    x_ranks = _rank(x)
    y_ranks = _rank(y)

    # Spearman = 1 - 6*sum(d^2) / (n*(n^2-1))
    d_squared = sum((a - b) ** 2 for a, b in zip(x_ranks, y_ranks))
    return 1.0 - (6.0 * d_squared) / (n * (n * n - 1))


def _rank(values: list[float]) -> list[float]:
    """计算等级（1-based）。"""
    indexed = sorted(enumerate(values), key=lambda v: v[1])
    ranks = [0.0] * len(values)
    for rank, (idx, _) in enumerate(indexed, 1):
        ranks[idx] = float(rank)
    return ranks
