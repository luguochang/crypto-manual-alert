from __future__ import annotations

import importlib
from typing import Any

import pytest
from pydantic import ValidationError


MODULE_NAME = "crypto_alert_v2.agents.research_harness_selection"


def _module() -> Any:
    try:
        return importlib.import_module(MODULE_NAME)
    except ModuleNotFoundError as exc:
        if exc.name != MODULE_NAME:
            raise
        raise AssertionError(
            "CAPABILITY GAP [task-13-research-schema]: the Deep Research typed "
            "result contract does not exist"
        ) from exc


def test_deep_research_report_requires_verified_citation_indexes() -> None:
    harness = _module()

    report = harness.DeepResearchReport.model_validate(
        {
            "executive_summary": "BTC 风险结构仍偏谨慎。",
            "sections": [
                {
                    "title": "宏观环境",
                    "summary": "实际利率维持高位。",
                    "findings": [
                        {
                            "claim": "实际利率仍处于限制性区间。",
                            "source_indexes": [1, 2],
                        }
                    ],
                }
            ],
            "risk_notes": ["事件窗口可能放大波动。"],
            "evidence_gaps": ["缺少可验证的期权期限结构。"],
        }
    )

    assert report.sections[0].findings[0].source_indexes == [1, 2]

    with pytest.raises(ValidationError, match="source_indexes"):
        harness.DeepResearchReport.model_validate(
            {
                "executive_summary": "缺少引用。",
                "sections": [
                    {
                        "title": "无来源段落",
                        "summary": "此段落不可接受。",
                        "findings": [
                            {
                                "claim": "没有 provider citation 的结论。",
                                "source_indexes": [],
                            }
                        ],
                    }
                ],
            }
        )


def test_deep_research_report_rejects_raw_urls_and_provider_payloads() -> None:
    harness = _module()
    schema = harness.DeepResearchReport.model_json_schema()
    serialized = str(schema).lower()

    assert "source_url" not in serialized
    assert "provider_payload" not in serialized
    assert "raw_payload" not in serialized

    with pytest.raises(ValidationError):
        harness.DeepResearchReport.model_validate(
            {
                "executive_summary": "测试。",
                "sections": [],
                "source_url": "https://unverified.example/source",
            }
        )


@pytest.mark.parametrize(
    "source_indexes",
    ([0], [-1], [9], [1, 1]),
)
def test_deep_research_report_rejects_invalid_or_duplicate_source_indexes(
    source_indexes: list[int],
) -> None:
    harness = _module()

    with pytest.raises(ValidationError, match="source_indexes"):
        harness.DeepResearchReport.model_validate(
            {
                "executive_summary": "引用必须落在本次受限来源目录中。",
                "sections": [
                    {
                        "title": "引用完整性",
                        "summary": "无效索引必须失败关闭。",
                        "findings": [
                            {
                                "claim": "该结论携带了无效来源索引。",
                                "source_indexes": source_indexes,
                            }
                        ],
                    }
                ],
            }
        )
