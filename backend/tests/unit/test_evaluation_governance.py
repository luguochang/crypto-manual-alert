from __future__ import annotations

import pytest

from crypto_alert_v2.evaluation.frozen_replay import freeze_replay_packet
from crypto_alert_v2.evaluation.governance import (
    CandidateStatus,
    RuleCandidate,
    run_frozen_rule_experiment,
    transition_candidate,
)


def _candidate() -> RuleCandidate:
    return RuleCandidate.create(
        name="strict-rule-v2",
        base_version="rule-v1",
        candidate_version="rule-v2",
        rollback_target_version="rule-v1",
        rationale="Require all deterministic gates before release.",
        diff={"minimum_scores": {"evidence": 1.0, "risk": 1.0}},
    )


def _packet():
    return freeze_replay_packet(
        request={"symbol": "BTC-USDT-SWAP", "horizon": "15m"},
        versions={"graph": "v2"},
        market={"source": "exchange_native"},
        evidence=({"source": "tavily"},),
        gates={"evidence": {"sufficient": True}, "risk": {"allowed": True}},
        observed_output={"terminal_status": "succeeded", "main_action": "no_trade"},
    )


def test_candidate_hash_is_deterministic_and_carries_rollback_target() -> None:
    assert _candidate().version_hash == _candidate().version_hash
    assert _candidate().rollback_target_version == "rule-v1"


def test_candidate_state_machine_requires_review_shadow_and_active_rollback() -> None:
    status = transition_candidate(CandidateStatus.DRAFT, CandidateStatus.EVALUATED)
    status = transition_candidate(status, CandidateStatus.PENDING_REVIEW)
    status = transition_candidate(status, CandidateStatus.APPROVED)
    status = transition_candidate(status, CandidateStatus.SHADOW)
    status = transition_candidate(status, CandidateStatus.ACTIVE)
    status = transition_candidate(status, CandidateStatus.ROLLED_BACK)

    assert status is CandidateStatus.ROLLED_BACK
    with pytest.raises(ValueError, match="forbidden"):
        transition_candidate(CandidateStatus.DRAFT, CandidateStatus.ACTIVE)


def test_frozen_rule_experiment_reuses_existing_release_metrics() -> None:
    result = run_frozen_rule_experiment(
        (("case-b", _packet()), ("case-a", _packet())),
        candidate=_candidate(),
        prompt_version="market-v1",
        git_revision="git-sha",
    )

    assert [item.case_name for item in result.case_results] == ["case-a", "case-b"]
    assert result.metrics == {
        "structure": 1.0,
        "evidence": 1.0,
        "risk": 1.0,
        "product_output": 1.0,
    }
