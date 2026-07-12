"""回归测试 runner - 三级判定（硬回归/软回归/趋势回归）。

来源：V2重构方案评审与补充建议_修订版.md 第 6.4 节。

回归触发条件：Prompt 变更 / 模型升级 / Graph 结构变更 / Tool Schema 修改 / 风控规则变更。

门禁规则：
| 级别     | 条件                                    | 动作       |
|----------|-----------------------------------------|------------|
| 硬回归   | 任务完成率下降 >5% 或方向准确率下降 >3% | 阻断发布   |
| 硬回归   | 风控拦截率下降 >1% 或误拦截率上升 >2%   | 阻断发布   |
| 软回归   | 任何指标下降 >2% 但未触发硬回归         | 人工 Review|
| 趋势回归 | 连续 3 次评测同一指标下降               | 长期监控+告警|
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ===========================================================================
# 指标定义
# ===========================================================================

class MetricName(str, Enum):
    """回归测试监控的指标。"""
    TASK_COMPLETION_RATE = "task_completion_rate"
    DIRECTION_ACCURACY = "direction_accuracy"
    RISK_INTERCEPT_RATE = "risk_intercept_rate"
    RISK_FALSE_POSITIVE_RATE = "risk_false_positive_rate"
    EVIDENCE_COVERAGE = "evidence_coverage"
    JUDGE_OVERALL_SCORE = "judge_overall_score"
    SCHEMA_COMPLETENESS = "schema_completeness"


@dataclass
class MetricResult:
    """单指标评测结果。"""
    name: MetricName
    current_value: float
    baseline_value: float
    delta: float  # current - baseline（百分比点）
    delta_pct: float  # 相对变化百分比

    def is_degraded(self) -> bool:
        """是否下降。"""
        return self.delta < 0

    def is_improved(self) -> bool:
        """是否提升。"""
        return self.delta > 0


# ===========================================================================
# 回归级别
# ===========================================================================

class RegressionLevel(str, Enum):
    """回归判定级别。"""
    NONE = "none"            # 无回归
    HARD = "hard"            # 硬回归 - 阻断发布
    SOFT = "soft"            # 软回归 - 人工 Review
    TREND = "trend"          # 趋势回归 - 长期监控 + 告警


class RegressionAction(str, Enum):
    """回归判定动作。"""
    PASS = "pass"            # 通过
    BLOCK = "block"          # 阻断发布
    REVIEW = "review"        # 人工 Review
    MONITOR = "monitor"      # 长期监控 + 告警


# ===========================================================================
# 门禁规则
# ===========================================================================

# 硬回归阈值
HARD_REGRESSION_THRESHOLDS: dict[MetricName, float] = {
    MetricName.TASK_COMPLETION_RATE: -5.0,   # 下降 >5%
    MetricName.DIRECTION_ACCURACY: -3.0,     # 下降 >3%
    MetricName.RISK_INTERCEPT_RATE: -1.0,    # 下降 >1%
    MetricName.RISK_FALSE_POSITIVE_RATE: 2.0,  # 上升 >2%（正值表示恶化）
}

# 软回归阈值
SOFT_REGRESSION_THRESHOLDS: dict[MetricName, float] = {
    MetricName.TASK_COMPLETION_RATE: -2.0,
    MetricName.DIRECTION_ACCURACY: -2.0,
    MetricName.RISK_INTERCEPT_RATE: -2.0,
    MetricName.RISK_FALSE_POSITIVE_RATE: 2.0,
    MetricName.EVIDENCE_COVERAGE: -2.0,
    MetricName.JUDGE_OVERALL_SCORE: -2.0,
    MetricName.SCHEMA_COMPLETENESS: -2.0,
}

# 趋势回归：连续 3 次下降
TREND_CONSECUTIVE_COUNT = 3


# ===========================================================================
# 回归判定结果
# ===========================================================================

class RegressionResult(BaseModel):
    """单次回归判定结果。"""
    level: RegressionLevel = Field(description="回归级别")
    action: RegressionAction = Field(description="执行动作")
    triggered_metrics: list[str] = Field(
        default_factory=list, description="触发回归的指标"
    )
    all_metrics: list[dict[str, Any]] = Field(
        default_factory=list, description="所有指标结果"
    )
    summary: str = Field(description="判定摘要")

    @property
    def is_blocking(self) -> bool:
        """是否阻断发布。"""
        return self.action == RegressionAction.BLOCK


# ===========================================================================
# 回归测试 Runner
# ===========================================================================

def compute_metric(
    name: MetricName,
    current: float,
    baseline: float,
) -> MetricResult:
    """计算单指标的变化。"""
    delta = current - baseline
    delta_pct = (delta / baseline * 100) if baseline != 0 else 0.0
    return MetricResult(
        name=name,
        current_value=current,
        baseline_value=baseline,
        delta=delta,
        delta_pct=delta_pct,
    )


def check_hard_regression(metric: MetricResult) -> bool:
    """检查是否触发硬回归。

    硬回归条件（满足任一即触发）：
    - 任务完成率下降 >5%
    - 方向准确率下降 >3%
    - 风控拦截率下降 >1%
    - 误拦截率上升 >2%
    """
    if metric.name not in HARD_REGRESSION_THRESHOLDS:
        return False

    threshold = HARD_REGRESSION_THRESHOLDS[metric.name]

    # 对于误拦截率，上升是恶化（delta > threshold 触发）
    if metric.name == MetricName.RISK_FALSE_POSITIVE_RATE:
        return metric.delta > threshold

    # 对于其他指标，下降是恶化（delta < threshold 触发，threshold 为负值）
    return metric.delta < threshold


def check_soft_regression(metric: MetricResult) -> bool:
    """检查是否触发软回归。

    软回归条件：任何指标下降 >2% 但未触发硬回归。
    """
    if metric.name not in SOFT_REGRESSION_THRESHOLDS:
        return False

    threshold = SOFT_REGRESSION_THRESHOLDS[metric.name]

    if metric.name == MetricName.RISK_FALSE_POSITIVE_RATE:
        return metric.delta > threshold and not check_hard_regression(metric)

    return metric.delta < threshold and not check_hard_regression(metric)


def check_trend_regression(
    metric_name: MetricName,
    history: list[float],
) -> bool:
    """检查是否触发趋势回归。

    趋势回归条件：连续 3 次评测同一指标下降。
    """
    if len(history) < TREND_CONSECUTIVE_COUNT:
        return False

    # 检查最近 N 次是否持续下降
    recent = history[-TREND_CONSECUTIVE_COUNT:]
    for i in range(1, len(recent)):
        if recent[i] >= recent[i - 1]:
            return False  # 不是持续下降
    return True


def run_regression_check(
    current_metrics: dict[MetricName, float],
    baseline_metrics: dict[MetricName, float],
    trend_history: dict[MetricName, list[float]] | None = None,
) -> RegressionResult:
    """执行完整的回归判定。

    Args:
        current_metrics: 当前评测的指标值
        baseline_metrics: 基线指标值
        trend_history: 趋势历史（每个指标的历史值列表）

    Returns:
        RegressionResult: 回归判定结果
    """
    trend_history = trend_history or {}
    all_metric_results: list[dict[str, Any]] = []
    hard_triggers: list[str] = []
    soft_triggers: list[str] = []
    trend_triggers: list[str] = []

    for name, current_val in current_metrics.items():
        baseline_val = baseline_metrics.get(name, current_val)
        metric = compute_metric(name, current_val, baseline_val)

        metric_dict = {
            "name": name.value,
            "current": current_val,
            "baseline": baseline_val,
            "delta": metric.delta,
            "delta_pct": round(metric.delta_pct, 2),
            "is_hard_regression": check_hard_regression(metric),
            "is_soft_regression": check_soft_regression(metric),
        }

        if check_hard_regression(metric):
            hard_triggers.append(name.value)
            metric_dict["level"] = "hard"
        elif check_soft_regression(metric):
            soft_triggers.append(name.value)
            metric_dict["level"] = "soft"
        else:
            metric_dict["level"] = "none"

        # 趋势检查
        history = trend_history.get(name, [])
        if check_trend_regression(name, history):
            trend_triggers.append(name.value)
            metric_dict["is_trend_regression"] = True
        else:
            metric_dict["is_trend_regression"] = False

        all_metric_results.append(metric_dict)

    # 判定最终级别（优先级：硬 > 软 > 趋势）
    if hard_triggers:
        level = RegressionLevel.HARD
        action = RegressionAction.BLOCK
        summary = f"硬回归触发，阻断发布。触发指标: {', '.join(hard_triggers)}"
    elif soft_triggers:
        level = RegressionLevel.SOFT
        action = RegressionAction.REVIEW
        summary = f"软回归触发，需要人工 Review。触发指标: {', '.join(soft_triggers)}"
    elif trend_triggers:
        level = RegressionLevel.TREND
        action = RegressionAction.MONITOR
        summary = f"趋势回归触发，长期监控 + 告警。触发指标: {', '.join(trend_triggers)}"
    else:
        level = RegressionLevel.NONE
        action = RegressionAction.PASS
        summary = "所有指标正常，通过回归测试。"

    return RegressionResult(
        level=level,
        action=action,
        triggered_metrics=hard_triggers + soft_triggers + trend_triggers,
        all_metrics=all_metric_results,
        summary=summary,
    )


# ===========================================================================
# 评测 Runner（集成 Judge + 确定性评估器）
# ===========================================================================

@dataclass
class EvalRunConfig:
    """评测运行配置。"""
    experiment_prefix: str = "regression"
    prompt_version: str = "v2.0.0"
    model_version: str = "gpt-4o"
    graph_version: str = "phase1"
    max_concurrency: int = 5
    timeout_seconds: int = 180


@dataclass
class EvalRunResult:
    """单次评测运行结果。"""
    config: EvalRunConfig
    total_cases: int = 0
    completed: int = 0
    failed: int = 0
    metrics: dict[MetricName, float] = field(default_factory=dict)
    case_results: list[dict[str, Any]] = field(default_factory=list)

    @property
    def completion_rate(self) -> float:
        """任务完成率。"""
        if self.total_cases == 0:
            return 0.0
        return (self.completed / self.total_cases) * 100


async def run_eval_suite(
    cases: list[dict[str, Any]],
    target_fn: Any,  # callable: inputs -> analysis_output
    config: EvalRunConfig | None = None,
) -> EvalRunResult:
    """执行评测套件。

    Args:
        cases: 评测用例列表
        target_fn: 被评测的目标函数（接收 inputs，返回 analysis_output）
        config: 评测配置

    Returns:
        EvalRunResult: 评测结果
    """
    import asyncio

    from crypto_alert_v2.eval.judge import (
        evaluate_direction,
        evaluate_evidence_coverage,
        evaluate_risk_rules,
        evaluate_schema_completeness,
    )

    config = config or EvalRunConfig()
    result = EvalRunResult(config=config, total_cases=len(cases))

    # 限制并发
    semaphore = asyncio.Semaphore(config.max_concurrency)

    async def run_single(case: dict[str, Any]) -> dict[str, Any]:
        async with semaphore:
            try:
                analysis = await target_fn(case["inputs"])

                # 确定性评估
                expected = case["outputs"]
                direction_ok = evaluate_direction(
                    analysis, expected["expected_direction"]
                )
                evidence_result = evaluate_evidence_coverage(
                    analysis,
                    expected.get("must_include_evidence", []),
                    expected.get("must_not_include", []),
                )
                schema_result = evaluate_schema_completeness(analysis)

                result.completed += 1
                return {
                    "case_id": case["id"],
                    "direction_ok": direction_ok,
                    "evidence_pass": evidence_result["pass"],
                    "schema_complete": schema_result["complete"],
                    "analysis": analysis,
                }
            except Exception as exc:
                result.failed += 1
                return {
                    "case_id": case["id"],
                    "error": str(exc),
                    "direction_ok": False,
                    "evidence_pass": False,
                    "schema_complete": False,
                }

    # 并发执行所有用例
    tasks = [run_single(case) for case in cases]
    case_results = await asyncio.gather(*tasks)
    result.case_results = list(case_results)

    # 计算聚合指标
    total = len(case_results)
    if total > 0:
        direction_correct = sum(1 for r in case_results if r.get("direction_ok"))
        evidence_pass = sum(1 for r in case_results if r.get("evidence_pass"))
        schema_ok = sum(1 for r in case_results if r.get("schema_complete"))

        result.metrics[MetricName.TASK_COMPLETION_RATE] = (
            result.completed / total * 100
        )
        result.metrics[MetricName.DIRECTION_ACCURACY] = (
            direction_correct / total * 100
        )
        result.metrics[MetricName.EVIDENCE_COVERAGE] = (
            evidence_pass / total * 100
        )
        result.metrics[MetricName.SCHEMA_COMPLETENESS] = (
            schema_ok / total * 100
        )

    return result
