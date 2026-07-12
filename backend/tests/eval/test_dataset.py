"""评测集单元测试。

测试范围：
- 评测集可以加载
- 覆盖维度分布正确
- Judge prompt 格式正确
- 每条用例结构完整

来源：V2重构方案评审与补充建议_修订版.md 第 6.2 节。
"""

import pytest

from crypto_alert_v2.eval.dataset import (
    DIMENSION_DISTRIBUTION,
    TOTAL_CASES,
    filter_by_dimension,
    generate_dataset,
    get_dimension_distribution,
    load_dataset,
)
from crypto_alert_v2.eval.judge import (
    JUDGE_PROMPT,
    format_judge_prompt,
    evaluate_direction,
    evaluate_evidence_coverage,
    evaluate_schema_completeness,
    calculate_agreement,
)


# ===========================================================================
# 评测集加载测试
# ===========================================================================

class TestDatasetLoading:
    """测试评测集加载。"""

    def test_dataset_generates_correct_count(self):
        """评测集生成 100 条。"""
        cases = generate_dataset()
        assert len(cases) == TOTAL_CASES
        assert len(cases) == 100

    def test_load_dataset_returns_cached(self):
        """load_dataset 返回缓存结果。"""
        cases1 = load_dataset()
        cases2 = load_dataset()
        assert cases1 is cases2  # 同一对象（缓存）

    def test_each_case_has_required_fields(self):
        """每条用例包含 inputs / outputs / metadata。"""
        cases = generate_dataset()
        for case in cases:
            assert "id" in case, f"用例缺少 id: {case}"
            assert "inputs" in case, f"用例 {case['id']} 缺少 inputs"
            assert "outputs" in case, f"用例 {case['id']} 缺少 outputs"
            assert "metadata" in case, f"用例 {case['id']} 缺少 metadata"

    def test_each_case_inputs_has_required_fields(self):
        """每条用例的 inputs 包含必需字段。"""
        cases = generate_dataset()
        required_input_fields = ["symbol", "horizon", "query_text", "market_snapshot", "research_bundle"]
        for case in cases:
            for field in required_input_fields:
                assert field in case["inputs"], (
                    f"用例 {case['id']} inputs 缺少 {field}"
                )

    def test_each_case_outputs_has_required_fields(self):
        """每条用例的 outputs 包含必需字段。"""
        cases = generate_dataset()
        required_output_fields = [
            "expected_direction",
            "expected_confidence_range",
            "expected_risk_blocked",
            "must_not_include",
            "key_checks",
        ]
        for case in cases:
            for field in required_output_fields:
                assert field in case["outputs"], (
                    f"用例 {case['id']} outputs 缺少 {field}"
                )

    def test_each_case_metadata_has_required_fields(self):
        """每条用例的 metadata 包含必需字段。"""
        cases = generate_dataset()
        required_meta_fields = ["category", "difficulty", "source", "created_at"]
        for case in cases:
            for field in required_meta_fields:
                assert field in case["metadata"], (
                    f"用例 {case['id']} metadata 缺少 {field}"
                )


# ===========================================================================
# 维度分布测试
# ===========================================================================

class TestDimensionDistribution:
    """测试维度分布。"""

    def test_distribution_matches_design(self):
        """维度分布符合设计文档定义。"""
        cases = generate_dataset()
        distribution = get_dimension_distribution(cases)

        for dim, expected_count in DIMENSION_DISTRIBUTION.items():
            actual_count = distribution.get(dim, 0)
            assert actual_count == expected_count, (
                f"维度 {dim}: 期望 {expected_count} 条，实际 {actual_count} 条"
            )

    def test_total_count_matches(self):
        """总数为 100。"""
        cases = generate_dataset()
        distribution = get_dimension_distribution(cases)
        total = sum(distribution.values())
        assert total == 100

    def test_all_8_dimensions_present(self):
        """8 个维度全部存在。"""
        cases = generate_dataset()
        distribution = get_dimension_distribution(cases)
        expected_dims = set(DIMENSION_DISTRIBUTION.keys())
        actual_dims = set(distribution.keys())
        assert expected_dims == actual_dims, (
            f"维度不匹配: 期望 {expected_dims}, 实际 {actual_dims}"
        )

    def test_filter_by_dimension(self):
        """按维度筛选功能正确。"""
        cases = generate_dataset()
        long_cases = filter_by_dimension(cases, "market_analysis_long")
        assert len(long_cases) == 15
        for case in long_cases:
            assert case["metadata"]["category"] == "market_analysis_long"

    def test_long_cases_count(self):
        """做多场景 15 条。"""
        cases = generate_dataset()
        long_cases = filter_by_dimension(cases, "market_analysis_long")
        assert len(long_cases) == 15

    def test_short_cases_count(self):
        """做空场景 15 条。"""
        cases = generate_dataset()
        short_cases = filter_by_dimension(cases, "market_analysis_short")
        assert len(short_cases) == 15

    def test_hold_cases_count(self):
        """观望场景 10 条。"""
        cases = generate_dataset()
        hold_cases = filter_by_dimension(cases, "market_analysis_hold")
        assert len(hold_cases) == 10

    def test_risk_intercept_cases_count(self):
        """风险拦截场景 20 条。"""
        cases = generate_dataset()
        risk_cases = filter_by_dimension(cases, "risk_intercept")
        assert len(risk_cases) == 20

    def test_evidence_cases_count(self):
        """证据评估场景 10 条。"""
        cases = generate_dataset()
        evidence_cases = filter_by_dimension(cases, "evidence_eval")
        assert len(evidence_cases) == 10

    def test_degradation_cases_count(self):
        """降级处理场景 10 条。"""
        cases = generate_dataset()
        degrade_cases = filter_by_dimension(cases, "degradation")
        assert len(degrade_cases) == 10

    def test_multi_turn_cases_count(self):
        """多轮对话场景 10 条。"""
        cases = generate_dataset()
        multi_cases = filter_by_dimension(cases, "multi_turn")
        assert len(multi_cases) == 10

    def test_boundary_cases_count(self):
        """边界测试场景 10 条。"""
        cases = generate_dataset()
        boundary_cases = filter_by_dimension(cases, "boundary")
        assert len(boundary_cases) == 10


# ===========================================================================
# Judge Prompt 格式测试
# ===========================================================================

class TestJudgePrompt:
    """测试 Judge prompt 格式。"""

    def test_prompt_template_has_placeholders(self):
        """prompt 模板包含 {analysis_output} 和 {reference_answer} 占位符。"""
        assert "{analysis_output}" in JUDGE_PROMPT
        assert "{reference_answer}" in JUDGE_PROMPT

    def test_prompt_contains_4_dimensions(self):
        """prompt 包含 4 个评估维度。"""
        assert "方向准确性" in JUDGE_PROMPT
        assert "风险控制" in JUDGE_PROMPT
        assert "证据引用" in JUDGE_PROMPT
        assert "可执行性" in JUDGE_PROMPT

    def test_prompt_contains_scoring_scale(self):
        """prompt 包含 1-5 分评分标准。"""
        assert "5分" in JUDGE_PROMPT
        assert "1分" in JUDGE_PROMPT

    def test_prompt_contains_cot_instruction(self):
        """prompt 包含 CoT 指令。"""
        assert "CoT" in JUDGE_PROMPT or "评分理由" in JUDGE_PROMPT

    def test_format_prompt_with_dict(self):
        """使用 dict 格式化 prompt。"""
        analysis = {
            "main_action": "open_long",
            "instrument": "BTC-USDT-SWAP",
            "horizon": "4h",
            "reference_price": 65000,
            "probability": 0.65,
        }
        reference = {
            "expected_direction": "long",
            "expected_confidence_range": [0.55, 0.75],
        }
        prompt = format_judge_prompt(analysis, reference)
        assert "BTC-USDT-SWAP" in prompt
        assert "long" in prompt

    def test_format_prompt_with_string(self):
        """使用 str 格式化 prompt。"""
        prompt = format_judge_prompt(
            "分析报告文本",
            "参考答案文本",
        )
        assert "分析报告文本" in prompt
        assert "参考答案文本" in prompt

    def test_formatted_prompt_contains_all_sections(self):
        """格式化后的 prompt 包含所有必要部分。"""
        prompt = format_judge_prompt(
            {"main_action": "open_long"},
            {"expected_direction": "long"},
        )
        assert "分析报告" in prompt
        assert "参考答案" in prompt
        assert "方向准确性" in prompt
        assert "风险控制" in prompt
        assert "证据引用" in prompt
        assert "可执行性" in prompt


# ===========================================================================
# 确定性评估器测试
# ===========================================================================

class TestDeterministicEvaluators:
    """测试确定性评估器（非 LLM）。"""

    def test_evaluate_direction_long(self):
        """方向评估 - 做多。"""
        analysis = {"main_action": "open_long"}
        assert evaluate_direction(analysis, "long") is True

    def test_evaluate_direction_short(self):
        """方向评估 - 做空。"""
        analysis = {"main_action": "open_short"}
        assert evaluate_direction(analysis, "short") is True

    def test_evaluate_direction_neutral(self):
        """方向评估 - 观望。"""
        analysis = {"main_action": "no_trade"}
        assert evaluate_direction(analysis, "neutral") is True

    def test_evaluate_direction_mismatch(self):
        """方向评估 - 不匹配。"""
        analysis = {"main_action": "open_long"}
        assert evaluate_direction(analysis, "short") is False

    def test_evaluate_evidence_coverage_pass(self):
        """证据覆盖检查 - 通过。"""
        analysis = {"text": "funding_rate is positive, open_interest is rising"}
        result = evaluate_evidence_coverage(
            analysis,
            must_include=["funding_rate", "open_interest"],
            must_not_include=["auto_order"],
        )
        assert result["pass"] is True

    def test_evaluate_evidence_coverage_missing(self):
        """证据覆盖检查 - 缺少必需证据。"""
        analysis = {"text": "funding_rate is positive"}
        result = evaluate_evidence_coverage(
            analysis,
            must_include=["funding_rate", "open_interest"],
            must_not_include=["auto_order"],
        )
        assert result["pass"] is False
        assert "open_interest" in result["missing_evidence"]

    def test_evaluate_evidence_coverage_forbidden(self):
        """证据覆盖检查 - 包含禁止项。"""
        analysis = {"text": "auto_order is enabled"}
        result = evaluate_evidence_coverage(
            analysis,
            must_include=[],
            must_not_include=["auto_order"],
        )
        assert result["pass"] is False
        assert "auto_order" in result["forbidden_present"]

    def test_evaluate_schema_completeness_pass(self):
        """Schema 完整性检查 - 通过。"""
        analysis = {
            "main_action": "open_long",
            "instrument": "BTC-USDT-SWAP",
            "horizon": "4h",
            "reference_price": 65000,
            "probability": 0.65,
            "max_leverage": 2,
            "risk_pct": 0.1,
            "root_cause_chain": ["reason1"],
            "why_not_opposite": "reason",
            "invalidation": "condition",
            "manual_execution_required": True,
            "expires_in_seconds": 90,
        }
        result = evaluate_schema_completeness(analysis)
        assert result["complete"] is True
        assert len(result["missing_fields"]) == 0

    def test_evaluate_schema_completeness_missing(self):
        """Schema 完整性检查 - 缺少字段。"""
        analysis = {
            "main_action": "open_long",
            "instrument": "BTC-USDT-SWAP",
        }
        result = evaluate_schema_completeness(analysis)
        assert result["complete"] is False
        assert len(result["missing_fields"]) > 0


# ===========================================================================
# 校准辅助测试
# ===========================================================================

class TestCalibration:
    """测试校准辅助函数。"""

    def test_agreement_perfect(self):
        """完美一致。"""
        scores = [4.0, 3.0, 5.0, 2.0]
        result = calculate_agreement(scores, scores, tolerance=0)
        assert result["agreement_rate"] == 1.0

    def test_agreement_within_tolerance(self):
        """在容差范围内一致。"""
        judge = [4.0, 3.0, 5.0]
        human = [3.5, 3.0, 4.5]
        result = calculate_agreement(judge, human, tolerance=1.0)
        assert result["agreement_rate"] == 1.0

    def test_agreement_partial(self):
        """部分一致。"""
        judge = [4.0, 3.0, 5.0, 1.0]
        human = [4.0, 3.0, 2.0, 1.0]
        result = calculate_agreement(judge, human, tolerance=0.5)
        assert result["agreement_rate"] == 0.75

    def test_spearman_perfect_correlation(self):
        """Spearman 完全正相关。"""
        scores = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = calculate_agreement(scores, scores)
        assert result["spearman_correlation"] == 1.0

    def test_spearman_inverse_correlation(self):
        """Spearman 完全负相关。"""
        judge = [1.0, 2.0, 3.0, 4.0, 5.0]
        human = [5.0, 4.0, 3.0, 2.0, 1.0]
        result = calculate_agreement(judge, human)
        assert result["spearman_correlation"] == -1.0

    def test_empty_lists(self):
        """空列表返回 0。"""
        result = calculate_agreement([], [])
        assert result["agreement_rate"] == 0.0
