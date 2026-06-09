from __future__ import annotations

import inspect

import pytest

from crypto_manual_alert.skills.facade import (
    EvidenceCandidate,
    LiquidityOrderBookSkill,
    MacroEventSkill,
    MarketSentimentSkill,
    RealtimeSearchSkill,
    RootCauseSearchSkill,
    SkillConstraints,
    SkillTaskContext,
    SkillToolResult,
)


class _SpoofedString(str):
    def __new__(cls, stored: str, displayed: str):
        value = super().__new__(cls, stored)
        value.displayed = displayed
        return value

    def __str__(self) -> str:
        return self.displayed


def test_skill_facade_contract_is_exported_from_skills_package():
    import crypto_manual_alert.skills as skills

    assert skills.SkillTaskContext is SkillTaskContext
    assert skills.SkillToolResult.__name__ == "SkillToolResult"
    assert skills.EvidenceCandidate is EvidenceCandidate
    assert skills.SkillConstraints is SkillConstraints
    assert skills.RealtimeSearchSkill is RealtimeSearchSkill
    assert skills.LiquidityOrderBookSkill is LiquidityOrderBookSkill


def test_realtime_search_skill_only_accepts_controlled_task_context():
    signature = inspect.signature(RealtimeSearchSkill.run)

    assert list(signature.parameters) == ["self", "context"]


def test_skill_facades_return_structured_tool_results_not_agent_contributions():
    context = SkillTaskContext(
        skill_name="realtime_search",
        task_id="skill:realtime_search",
        symbol="ETH-USDT-SWAP",
        trace_id="trace-skill",
        query="ETF flow surprise",
        input_view={
            "facts_gate": {"passed": False},
            "search_results": [
                {
                    "title": "ETF flow surprise",
                    "url": "https://example.test/etf",
                    "snippet_ref": "research.results.macro_context[0].snippet_redacted",
                    "source_type": "search_derived",
                }
            ],
        },
        max_depth=2,
        timeout_seconds=12,
    )

    result = RealtimeSearchSkill().run(context)

    public = result.to_public_dict()

    assert public == {
        "skill_name": "realtime_search",
        "task_id": "skill:realtime_search",
        "status": "ok",
        "decision_effect": "none",
        "result_type": "evidence_candidates",
        "source_type": "search_derived",
        "can_satisfy_execution_fact": False,
        "evidence_candidates": [
            {
                "title": "ETF flow surprise",
                "url": "https://example.test/etf",
                "snippet_ref": "research.results.macro_context[0].snippet_redacted",
                "source_type": "search_derived",
            }
        ],
        "constraints": {
            "must_pass_facts_gate": True,
            "raw_snippets_redacted": True,
            "max_depth": 2,
            "timeout_seconds": 12,
        },
        "missing_inputs": [],
        "trace_ref": "trace-skill:skill:realtime_search",
    }
    assert "contribution_id" not in public
    assert "agent_name" not in public
    assert "main_action" not in str(public)
    assert "risk_verdict" not in str(public)


def test_realtime_search_candidates_are_always_search_derived():
    context = SkillTaskContext(
        skill_name="realtime_search",
        task_id="skill:realtime_search",
        symbol="ETH-USDT-SWAP",
        trace_id="trace-skill",
        query="exchange mark price breaking news",
        input_view={
            "search_results": [
                {
                    "title": "Caller tried to tag search result as native",
                    "url": "https://example.test/search",
                    "snippet_ref": "research.results.live_news[0].snippet_redacted",
                    "source_type": "exchange_native",
                }
            ],
        },
    )

    result = RealtimeSearchSkill().run(context)

    public = result.to_public_dict()

    assert public["source_type"] == "search_derived"
    assert public["can_satisfy_execution_fact"] is False
    assert public["evidence_candidates"] == [
        {
            "title": "Caller tried to tag search result as native",
            "url": "https://example.test/search",
            "snippet_ref": "research.results.live_news[0].snippet_redacted",
            "source_type": "search_derived",
        }
    ]


def test_skill_tool_result_rejects_final_or_side_effect_semantics():
    with pytest.raises(ValueError, match="decision_effect"):
        SkillToolResult(
            skill_name="realtime_search",
            task_id="skill:realtime_search",
            status="ok",
            result_type="evidence_candidates",
            source_type="search_derived",
            can_satisfy_execution_fact=False,
            decision_effect="production_final_input",
        )

    with pytest.raises(ValueError, match="EvidenceCandidate"):
        SkillToolResult(
            skill_name="realtime_search",
            task_id="skill:realtime_search",
            status="ok",
            result_type="evidence_candidates",
            source_type="search_derived",
            can_satisfy_execution_fact=False,
            evidence_candidates=[{"title": "not allowed", "main_action": "open"}],
        )

    with pytest.raises(ValueError, match="SkillConstraints"):
        SkillToolResult(
            skill_name="realtime_search",
            task_id="skill:realtime_search",
            status="ok",
            result_type="evidence_candidates",
            source_type="search_derived",
            can_satisfy_execution_fact=False,
            constraints={"allow_production_journal_write": True},
        )


@pytest.mark.parametrize(
    "field_name",
    [
        "allow_notification_intent",
        "entry_trigger",
        "max_leverage",
        "order_payload",
        "risk_pct",
        "stop_price",
        "target_1",
        "target_2",
    ],
)
def test_skill_tool_result_rejects_executable_field_variants(field_name: str):
    with pytest.raises(ValueError, match="SkillConstraints"):
        SkillToolResult(
            skill_name="realtime_search",
            task_id="skill:realtime_search",
            status="ok",
            result_type="evidence_candidates",
            source_type="search_derived",
            can_satisfy_execution_fact=False,
            constraints={field_name: "not allowed"},
        )


def test_skill_tool_result_rejects_open_mutable_payloads():
    with pytest.raises(ValueError, match="EvidenceCandidate"):
        SkillToolResult(
            skill_name="realtime_search",
            task_id="skill:realtime_search",
            status="ok",
            result_type="evidence_candidates",
            source_type="search_derived",
            can_satisfy_execution_fact=False,
            evidence_candidates=[{"title": "safe looking"}],
        )

    with pytest.raises(ValueError, match="SkillConstraints"):
        SkillToolResult(
            skill_name="realtime_search",
            task_id="skill:realtime_search",
            status="ok",
            result_type="evidence_candidates",
            source_type="search_derived",
            can_satisfy_execution_fact=False,
            constraints={"outputs": ["final_decision"]},
        )


def test_skill_tool_result_rejects_unapproved_result_and_source_types():
    with pytest.raises(ValueError, match="result_type"):
        SkillToolResult(
            skill_name="realtime_search",
            task_id="skill:realtime_search",
            status="ok",
            result_type="final_decision",
            source_type="search_derived",
            can_satisfy_execution_fact=False,
        )

    with pytest.raises(ValueError, match="source_type"):
        SkillToolResult(
            skill_name="realtime_search",
            task_id="skill:realtime_search",
            status="ok",
            result_type="evidence_candidates",
            source_type="production_final_input",
            can_satisfy_execution_fact=False,
        )

    with pytest.raises(ValueError, match="execution fact"):
        SkillToolResult(
            skill_name="realtime_search",
            task_id="skill:realtime_search",
            status="ok",
            result_type="evidence_candidates",
            source_type="search_derived",
            can_satisfy_execution_fact=True,
        )


def test_skill_tool_result_rejects_illegal_skill_contract_combinations():
    with pytest.raises(ValueError, match="contract"):
        SkillToolResult(
            skill_name="realtime_search",
            task_id="skill:realtime_search",
            status="ok",
            result_type="exchange_execution_fact_candidates",
            source_type="exchange_native",
            can_satisfy_execution_fact=True,
            constraints=SkillConstraints(
                search_derived_cannot_satisfy_execution_fact=True,
                required_execution_facts=("mark", "index", "order_book"),
            ),
        )

    with pytest.raises(ValueError, match="contract"):
        SkillToolResult(
            skill_name="macro_event",
            task_id="skill:macro_event",
            status="ok",
            result_type="macro_event_candidates",
            source_type="official_or_event_pool",
            can_satisfy_execution_fact=False,
            constraints=SkillConstraints(required_fields=("event_status",)),
        )


def test_skill_tool_result_rejects_cross_skill_extra_constraints():
    with pytest.raises(ValueError, match="contract"):
        SkillToolResult(
            skill_name="macro_event",
            task_id="skill:macro_event",
            status="ok",
            result_type="macro_event_candidates",
            source_type="official_or_event_pool",
            can_satisfy_execution_fact=False,
            constraints=SkillConstraints(
                required_fields=(
                    "event_status",
                    "actual",
                    "consensus",
                    "surprise",
                    "market_reaction",
                    "lagged_confirmation",
                    "released_at",
                ),
                search_derived_cannot_satisfy_execution_fact=True,
                required_execution_facts=("mark", "index", "order_book"),
            ),
        )

    with pytest.raises(ValueError, match="contract"):
        SkillToolResult(
            skill_name="realtime_search",
            task_id="skill:realtime_search",
            status="ok",
            result_type="evidence_candidates",
            source_type="search_derived",
            can_satisfy_execution_fact=False,
            constraints=SkillConstraints(
                raw_snippets_redacted=True,
                required_fields=(
                    "event_status",
                    "actual",
                    "consensus",
                    "surprise",
                    "market_reaction",
                    "lagged_confirmation",
                    "released_at",
                ),
            ),
        )


def test_skill_tool_result_rejects_modified_common_constraints():
    with pytest.raises(ValueError, match="contract"):
        SkillToolResult(
            skill_name="realtime_search",
            task_id="skill:realtime_search",
            status="ok",
            result_type="evidence_candidates",
            source_type="search_derived",
            can_satisfy_execution_fact=False,
            constraints=SkillConstraints(must_pass_facts_gate=False, raw_snippets_redacted=True),
        )


def test_skill_tool_result_rejects_non_structured_public_field_values():
    with pytest.raises(ValueError, match="status"):
        SkillToolResult(
            skill_name="realtime_search",
            task_id="skill:realtime_search",
            status={"main_action": "trigger"},
            result_type="evidence_candidates",
            source_type="search_derived",
            can_satisfy_execution_fact=False,
        )

    with pytest.raises(ValueError, match="missing_inputs"):
        SkillToolResult(
            skill_name="realtime_search",
            task_id="skill:realtime_search",
            status="ok",
            result_type="evidence_candidates",
            source_type="search_derived",
            can_satisfy_execution_fact=False,
            missing_inputs=[{"order_payload": {"side": "buy"}}],
        )


def test_skill_tool_result_rejects_mapping_payloads_for_sequences():
    with pytest.raises(ValueError, match="evidence_candidates"):
        SkillToolResult(
            skill_name="realtime_search",
            task_id="skill:realtime_search",
            status="ok",
            result_type="evidence_candidates",
            source_type="search_derived",
            can_satisfy_execution_fact=False,
            evidence_candidates={
                "payload": EvidenceCandidate(
                    title="safe title",
                    url="https://example.test/safe",
                    snippet_ref="research.results.safe[0]",
                )
            },
            constraints=SkillConstraints(raw_snippets_redacted=True),
        )

    with pytest.raises(ValueError, match="missing_inputs"):
        SkillToolResult(
            skill_name="realtime_search",
            task_id="skill:realtime_search",
            status="ok",
            result_type="evidence_candidates",
            source_type="search_derived",
            can_satisfy_execution_fact=False,
            constraints=SkillConstraints(raw_snippets_redacted=True),
            missing_inputs={"symbol": "symbol"},
        )


def test_skill_tool_result_rejects_falsy_non_sequence_payloads():
    with pytest.raises(ValueError, match="evidence_candidates"):
        SkillToolResult(
            skill_name="realtime_search",
            task_id="skill:realtime_search",
            status="ok",
            result_type="evidence_candidates",
            source_type="search_derived",
            can_satisfy_execution_fact=False,
            evidence_candidates={},
            constraints=SkillConstraints(raw_snippets_redacted=True),
        )

    with pytest.raises(ValueError, match="missing_inputs"):
        SkillToolResult(
            skill_name="realtime_search",
            task_id="skill:realtime_search",
            status="ok",
            result_type="evidence_candidates",
            source_type="search_derived",
            can_satisfy_execution_fact=False,
            constraints=SkillConstraints(raw_snippets_redacted=True),
            missing_inputs="",
        )


def test_skill_tool_result_rejects_spoofed_string_subclasses():
    with pytest.raises(ValueError, match="skill_name"):
        SkillToolResult(
            skill_name=_SpoofedString("realtime_search", "final_decision"),
            task_id="skill:realtime_search",
            status="ok",
            result_type="evidence_candidates",
            source_type="search_derived",
            can_satisfy_execution_fact=False,
        )

    with pytest.raises(ValueError, match="decision_effect"):
        SkillToolResult(
            skill_name="realtime_search",
            task_id="skill:realtime_search",
            status="ok",
            result_type="evidence_candidates",
            source_type="search_derived",
            can_satisfy_execution_fact=False,
            decision_effect=_SpoofedString("none", "production_final_input"),
        )


def test_skill_tool_result_rejects_value_object_subclasses():
    class UnsafeEvidenceCandidate(EvidenceCandidate):
        def to_public_dict(self) -> dict[str, object]:
            return {"order_payload": {"side": "buy"}}

    class UnsafeSkillConstraints(SkillConstraints):
        def to_public_dict(self) -> dict[str, object]:
            return {"allow_production_journal_write": True}

    with pytest.raises(ValueError, match="EvidenceCandidate"):
        SkillToolResult(
            skill_name="realtime_search",
            task_id="skill:realtime_search",
            status="ok",
            result_type="evidence_candidates",
            source_type="search_derived",
            can_satisfy_execution_fact=False,
            evidence_candidates=[
                UnsafeEvidenceCandidate(
                    title="safe",
                    url="https://example.test/safe",
                    snippet_ref="research.results.safe[0]",
                )
            ],
        )

    with pytest.raises(ValueError, match="SkillConstraints"):
        SkillToolResult(
            skill_name="realtime_search",
            task_id="skill:realtime_search",
            status="ok",
            result_type="evidence_candidates",
            source_type="search_derived",
            can_satisfy_execution_fact=False,
            constraints=UnsafeSkillConstraints(raw_snippets_redacted=True),
        )


def test_skill_tool_result_rejects_unapproved_identity_values():
    with pytest.raises(ValueError, match="skill_name"):
        SkillToolResult(
            skill_name="final_decision",
            task_id="skill:realtime_search",
            status="ok",
            result_type="evidence_candidates",
            source_type="search_derived",
            can_satisfy_execution_fact=False,
        )

    with pytest.raises(ValueError, match="task_id"):
        SkillToolResult(
            skill_name="realtime_search",
            task_id="live_order",
            status="ok",
            result_type="evidence_candidates",
            source_type="search_derived",
            can_satisfy_execution_fact=False,
        )

    with pytest.raises(ValueError, match="trace_ref"):
        SkillToolResult(
            skill_name="realtime_search",
            task_id="skill:realtime_search",
            status="ok",
            result_type="evidence_candidates",
            source_type="search_derived",
            can_satisfy_execution_fact=False,
            trace_ref="notification:production_journal",
        )


def test_skill_tool_result_rejects_trace_ref_and_missing_input_semantic_leakage():
    with pytest.raises(ValueError, match="trace_ref"):
        SkillToolResult(
            skill_name="realtime_search",
            task_id="skill:realtime_search",
            status="ok",
            result_type="evidence_candidates",
            source_type="search_derived",
            can_satisfy_execution_fact=False,
            trace_ref="notification:production_journal:skill:realtime_search",
        )

    with pytest.raises(ValueError, match="missing_inputs"):
        SkillToolResult(
            skill_name="realtime_search",
            task_id="skill:realtime_search",
            status="ok",
            result_type="evidence_candidates",
            source_type="search_derived",
            can_satisfy_execution_fact=False,
            missing_inputs=["order_payload"],
        )


def test_evidence_candidate_rejects_final_or_side_effect_text_values():
    with pytest.raises(ValueError, match="title"):
        EvidenceCandidate(
            title="final_decision",
            url="https://example.test/safe",
            snippet_ref="research.results.safe[0]",
        )

    with pytest.raises(ValueError, match="snippet_ref"):
        EvidenceCandidate(
            title="safe title",
            url="https://example.test/safe",
            snippet_ref="research.results.order_payload[0]",
        )


def test_evidence_candidate_rejects_spoofed_source_type():
    with pytest.raises(ValueError, match="source_type"):
        EvidenceCandidate(
            title="safe title",
            url="https://example.test/safe",
            snippet_ref="research.results.safe[0]",
            source_type=_SpoofedString("search_derived", "exchange_native"),
        )


@pytest.mark.parametrize(
    "unsafe_text",
    [
        "final decision",
        "live order",
        "order payload",
        "main action",
        "risk verdict",
        "side effect",
        "production final input",
        "order-payload",
    ],
)
def test_evidence_candidate_rejects_spaced_or_hyphenated_semantic_values(unsafe_text: str):
    with pytest.raises(ValueError, match="title"):
        EvidenceCandidate(
            title=unsafe_text,
            url="https://example.test/safe",
            snippet_ref="research.results.safe[0]",
        )


def test_realtime_search_sanitizes_unsafe_evidence_text_values():
    context = SkillTaskContext(
        skill_name="realtime_search",
        task_id="skill:realtime_search",
        symbol="ETH-USDT-SWAP",
        trace_id="trace-skill",
        query="ETF flow surprise",
        input_view={
            "search_results": [
                {
                    "title": "final_decision",
                    "url": "https://example.test/order_payload",
                    "snippet_ref": "research.results.notification[0]",
                    "source_type": "exchange_native",
                }
            ],
        },
    )

    public = RealtimeSearchSkill().run(context).to_public_dict()

    assert public["evidence_candidates"] == [
        {
            "title": "",
            "url": "",
            "snippet_ref": "",
            "source_type": "search_derived",
        }
    ]


def test_realtime_search_sanitizes_spaced_or_hyphenated_evidence_text_values():
    context = SkillTaskContext(
        skill_name="realtime_search",
        task_id="skill:realtime_search",
        symbol="ETH-USDT-SWAP",
        trace_id="trace-skill",
        query="ETF flow surprise",
        input_view={
            "search_results": [
                {
                    "title": "final decision",
                    "url": "https://example.test/order-payload",
                    "snippet_ref": "research.results.live order[0]",
                }
            ],
        },
    )

    public = RealtimeSearchSkill().run(context).to_public_dict()

    assert public["evidence_candidates"] == [
        {
            "title": "",
            "url": "",
            "snippet_ref": "",
            "source_type": "search_derived",
        }
    ]


def test_skill_task_context_snapshots_input_view_before_run():
    input_view = {
        "search_results": [
            {
                "title": "safe title",
                "url": "https://example.test/safe",
                "snippet_ref": "research.results.safe[0]",
            }
        ]
    }
    context = SkillTaskContext(
        skill_name="realtime_search",
        task_id="skill:realtime_search",
        symbol="ETH-USDT-SWAP",
        trace_id="trace-skill",
        query="ETF flow surprise",
        input_view=input_view,
    )
    input_view["search_results"][0]["title"] = "final_decision"
    input_view["search_results"][0]["url"] = "https://example.test/order_payload"

    public = RealtimeSearchSkill().run(context).to_public_dict()

    assert public["evidence_candidates"] == [
        {
            "title": "safe title",
            "url": "https://example.test/safe",
            "snippet_ref": "research.results.safe[0]",
            "source_type": "search_derived",
        }
    ]


def test_skill_task_context_rejects_trace_id_semantic_leakage():
    with pytest.raises(ValueError, match="trace_id"):
        SkillTaskContext(
            skill_name="realtime_search",
            task_id="skill:realtime_search",
            symbol="ETH-USDT-SWAP",
            trace_id="final decision",
            query="ETF flow surprise",
            input_view={},
        )

    with pytest.raises(ValueError, match="trace_id"):
        SkillTaskContext(
            skill_name="realtime_search",
            task_id="skill:realtime_search",
            symbol="ETH-USDT-SWAP",
            trace_id="order-payload",
            query="ETF flow surprise",
            input_view={},
        )


def test_skill_constraints_reject_unapproved_semantic_values():
    with pytest.raises(ValueError, match="outputs"):
        SkillConstraints(outputs=("final_decision",))

    with pytest.raises(ValueError, match="required_execution_facts"):
        SkillConstraints(required_execution_facts=("order_payload",))

    with pytest.raises(ValueError, match="required_fields"):
        SkillConstraints(required_fields=("main_action",))


def test_facade_result_public_views_are_deep_copies():
    context = SkillTaskContext(
        skill_name="root_cause_search",
        task_id="skill:root_cause",
        symbol="ETH-USDT-SWAP",
        trace_id="trace-skill",
        query="ETF flow surprise",
        input_view={},
        max_depth=3,
        timeout_seconds=20,
    )
    result = RootCauseSearchSkill().run(context)

    public = result.to_public_dict()
    public["constraints"]["allowed_factor_types"].append("final_decision")
    result.constraints["allowed_factor_types"].append("live_order")

    assert result.to_public_dict()["constraints"]["allowed_factor_types"] == [
        "macro_event",
        "derivatives",
        "liquidity",
        "sentiment",
        "policy",
        "flow",
    ]


def test_facade_evidence_public_view_is_deep_copy():
    context = SkillTaskContext(
        skill_name="realtime_search",
        task_id="skill:realtime_search",
        symbol="ETH-USDT-SWAP",
        trace_id="trace-skill",
        query="ETF flow surprise",
        input_view={
            "search_results": [
                {
                    "title": "ETF flow surprise",
                    "url": "https://example.test/etf",
                    "snippet_ref": "research.results.macro_context[0].snippet_redacted",
                    "source_type": "search_derived",
                }
            ],
        },
    )
    result = RealtimeSearchSkill().run(context)

    public = result.to_public_dict()
    public["evidence_candidates"][0]["order_payload"] = {"side": "buy"}

    assert "order_payload" not in result.to_public_dict()["evidence_candidates"][0]


def test_domain_skill_facades_encode_realtime_boundaries_and_domain_policies():
    root_context = SkillTaskContext(
        skill_name="root_cause_search",
        task_id="skill:root_cause",
        symbol="ETH-USDT-SWAP",
        trace_id="trace-skill",
        query="ETF flow surprise",
        input_view={},
        max_depth=3,
        timeout_seconds=20,
    )
    sentiment_context = SkillTaskContext(
        skill_name="market_sentiment",
        task_id="skill:market_sentiment",
        symbol="ETH-USDT-SWAP",
        trace_id="trace-skill",
        query="ETF flow surprise",
        input_view={},
        max_depth=3,
        timeout_seconds=20,
    )
    macro_context = SkillTaskContext(
        skill_name="macro_event",
        task_id="skill:macro_event",
        symbol="ETH-USDT-SWAP",
        trace_id="trace-skill",
        query="ETF flow surprise",
        input_view={},
        max_depth=3,
        timeout_seconds=20,
    )
    liquidity_context = SkillTaskContext(
        skill_name="liquidity_order_book",
        task_id="skill:liquidity_order_book",
        symbol="ETH-USDT-SWAP",
        trace_id="trace-skill",
        query="ETF flow surprise",
        input_view={},
        max_depth=3,
        timeout_seconds=20,
    )

    root = RootCauseSearchSkill().run(root_context)
    sentiment = MarketSentimentSkill().run(sentiment_context)
    macro = MacroEventSkill().run(macro_context)
    liquidity = LiquidityOrderBookSkill().run(liquidity_context)

    assert root.constraints == {
        "must_pass_facts_gate": True,
        "max_depth": 3,
        "timeout_seconds": 20,
        "recursive_factor_search": True,
        "allowed_factor_types": ["macro_event", "derivatives", "liquidity", "sentiment", "policy", "flow"],
    }
    assert sentiment.constraints == {
        "must_pass_facts_gate": True,
        "max_depth": 3,
        "timeout_seconds": 20,
        "separate_objective_facts_from_crowding": True,
        "outputs": ["crowding", "priced_in", "reflexivity"],
    }
    assert macro.constraints == {
        "must_pass_facts_gate": True,
        "max_depth": 3,
        "timeout_seconds": 20,
        "required_fields": [
            "event_status",
            "actual",
            "consensus",
            "surprise",
            "market_reaction",
            "lagged_confirmation",
            "released_at",
        ],
    }
    assert liquidity.source_type == "exchange_native"
    assert liquidity.can_satisfy_execution_fact is True
    assert liquidity.constraints == {
        "must_pass_facts_gate": True,
        "max_depth": 3,
        "timeout_seconds": 20,
        "search_derived_cannot_satisfy_execution_fact": True,
        "required_execution_facts": ["mark", "index", "order_book"],
    }


def test_skill_task_context_rejects_invalid_limits():
    try:
        SkillTaskContext(
            skill_name="root_cause_search",
            task_id="skill:root_cause",
            symbol="ETH-USDT-SWAP",
            trace_id="trace-skill",
            query="ETF flow surprise",
            input_view={},
            max_depth=0,
            timeout_seconds=20,
        )
    except ValueError as exc:
        assert "max_depth" in str(exc)
    else:
        raise AssertionError("max_depth=0 should be rejected")

    try:
        SkillTaskContext(
            skill_name="root_cause_search",
            task_id="skill:root_cause",
            symbol="ETH-USDT-SWAP",
            trace_id="trace-skill",
            query="ETF flow surprise",
            input_view={},
            max_depth=2,
            timeout_seconds=0,
        )
    except ValueError as exc:
        assert "timeout_seconds" in str(exc)
    else:
        raise AssertionError("timeout_seconds=0 should be rejected")

    try:
        SkillTaskContext(
            skill_name="root_cause_search",
            task_id="skill:root_cause",
            symbol="ETH-USDT-SWAP",
            trace_id="trace-skill",
            query="ETF flow surprise",
            input_view={},
            max_depth=True,
            timeout_seconds=20,
        )
    except ValueError as exc:
        assert "max_depth" in str(exc)
    else:
        raise AssertionError("max_depth=True should be rejected")

    with pytest.raises(ValueError, match="timeout_seconds"):
        SkillConstraints(timeout_seconds=True)
