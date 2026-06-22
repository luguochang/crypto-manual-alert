from __future__ import annotations

import importlib
import sys
from pathlib import Path
from collections.abc import Iterator
from contextlib import contextmanager


@contextmanager
def _without_modules(*prefixes: str) -> Iterator[None]:
    previous = {
        name: module
        for name, module in sys.modules.items()
        if any(name == prefix or name.startswith(f"{prefix}.") for prefix in prefixes)
    }
    for name in previous:
        sys.modules.pop(name, None)
    try:
        yield
    finally:
        for name in list(sys.modules):
            if any(name == prefix or name.startswith(f"{prefix}.") for prefix in prefixes):
                sys.modules.pop(name, None)
        sys.modules.update(previous)


def test_eval_judges_package_import_does_not_eagerly_import_judge_modules():
    with _without_modules("crypto_manual_alert.eval.judges"):
        judges = importlib.import_module("crypto_manual_alert.eval.judges")

        assert "crypto_manual_alert.eval.judges.fixture_llm" not in sys.modules
        assert "crypto_manual_alert.eval.judges.llm" not in sys.modules
        assert "crypto_manual_alert.eval.judges.rules" not in sys.modules
        assert "crypto_manual_alert.eval.judges.side_effects" not in sys.modules

        llm = importlib.import_module("crypto_manual_alert.eval.judges.llm")
        rules = importlib.import_module("crypto_manual_alert.eval.judges.rules")
        fixture = importlib.import_module("crypto_manual_alert.eval.judges.fixture_llm")
        side_effects = importlib.import_module("crypto_manual_alert.eval.judges.side_effects")

        assert judges.OpenAICompatibleLLMJudge is llm.OpenAICompatibleLLMJudge
        assert judges.RuleJudge is rules.RuleJudge
        assert judges.OPENING_ACTIONS is rules.OPENING_ACTIONS
        assert judges.FixtureLLMJudge is fixture.FixtureLLMJudge
        assert judges.build_side_effect_score is side_effects.build_side_effect_score


def test_financial_quality_gate_stays_separate_from_structural_release_gate():
    source = Path("src/crypto_manual_alert/eval/release_gate.py").read_text(encoding="utf-8")

    assert "financial_quality" not in source
    assert "PredictionQualityMetrics" not in source


def test_financial_quality_modules_do_not_import_live_fetch_or_production_side_effects():
    guarded_files = [
        Path("src/crypto_manual_alert/eval/financial_quality_summary.py"),
        Path("src/crypto_manual_alert/eval/financial_quality_gate.py"),
        Path("src/crypto_manual_alert/eval/market_outcome_collector.py"),
        Path("src/crypto_manual_alert/eval/outcome_store.py"),
        Path("src/crypto_manual_alert/eval/prediction_metrics.py"),
    ]
    forbidden = [
        "httpx",
        "requests",
        "market.providers",
        "notification",
        "record_outcome",
        "append_plan_run",
        "open_order",
        "place_order",
    ]

    for path in guarded_files:
        source = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in source, f"{path} must not depend on live fetch or production side effects"
