from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from crypto_manual_alert.config import load_config
from crypto_manual_alert.decision.legacy_final_input_step import build_legacy_final_input_step
from crypto_manual_alert.domain import MarketSnapshot
from crypto_manual_alert.research_pipeline import ResearchAudit, ResearchPlan, SearchResult
from crypto_manual_alert.skills.context_loader import SkillRuntime


def test_legacy_final_input_step_builds_safe_prompt_and_frozen_input():
    config = load_config("config/default.yaml")
    skill_runtime = SkillRuntime(config)
    skill_context = skill_runtime.load_context()
    snapshot = MarketSnapshot(
        symbol="ETH-USDT-SWAP",
        fetched_at=datetime.now(timezone.utc),
        points={},
        unavailable=[],
    )
    research_audit = ResearchAudit(
        plan=ResearchPlan(queries=[], reason="fixture"),
        results={
            "eth_price_context": [
                SearchResult(
                    title="ETH headline",
                    url="https://example.test/eth",
                    snippet="raw snippet must stay out of final prompt",
                )
            ]
        },
    )

    result = build_legacy_final_input_step(
        trace_id="trace-1",
        skill_runtime=skill_runtime,
        skill_context=skill_context,
        snapshot=snapshot,
        research_audit=research_audit,
    )

    rendered_prompt = json.dumps(result.prompt_packet, ensure_ascii=False)
    expected_hash = hashlib.sha256(
        json.dumps(result.prompt_packet, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()

    assert "raw snippet must stay out of final prompt" not in rendered_prompt
    assert result.prompt_packet["research"]["results"]["eth_price_context"][0]["snippet_ref"].endswith(
        ".snippet_redacted"
    )
    assert result.frozen_input.input_payload == result.prompt_packet
    assert result.frozen_input.frozen_input_hash == expected_hash
    assert result.prompt_summary == {"keys": sorted(result.prompt_packet)}
    assert result.freeze_summary == {
        "frozen_input_hash": expected_hash,
        "schema_version": result.frozen_input.schema_version,
        "kind": "decision_prompt_packet",
        "top_level_keys": sorted(result.prompt_packet),
    }
