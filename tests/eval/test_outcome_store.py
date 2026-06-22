from __future__ import annotations

from crypto_manual_alert.eval.outcome_store import OutcomeStore
from crypto_manual_alert.eval.outcomes import DecisionOutcome, OutcomeWindow


def test_outcome_store_round_trips_decision_outcomes_by_target(tmp_path):
    store = OutcomeStore(tmp_path / "outcomes.db")
    legacy = _outcome("trace-1:legacy", "legacy_final")
    candidate = _outcome("trace-1:candidate", "swarm_candidate_final")

    store.upsert_outcomes([legacy, candidate])

    assert store.list_outcomes(evaluation_target="legacy_final") == [legacy]
    assert store.list_outcomes(evaluation_target="swarm_candidate_final") == [candidate]


def test_outcome_store_keeps_multiple_windows_for_the_same_decision(tmp_path):
    store = OutcomeStore(tmp_path / "outcomes.db")
    one_hour = _outcome("trace-1:candidate", "swarm_candidate_final", window_name="1h")
    four_hour = _outcome("trace-1:candidate", "swarm_candidate_final", window_name="4h")

    store.upsert_outcomes([one_hour, four_hour])

    outcomes = store.list_outcomes(evaluation_target="swarm_candidate_final")
    assert [outcome.window.name for outcome in outcomes] == ["1h", "4h"]
    assert outcomes == [one_hour, four_hour]


def _outcome(decision_ref: str, target: str, *, window_name: str = "1h") -> DecisionOutcome:
    return DecisionOutcome(
        decision_ref=decision_ref,
        evaluation_target=target,
        symbol="ETH-USDT-SWAP",
        action="trigger long",
        probability=0.61,
        entry_price=3000,
        stop_price=2950,
        target_1=3100,
        target_2=None,
        regime="risk_on_repair",
        window=OutcomeWindow(
            name=window_name,
            symbol="ETH-USDT-SWAP",
            interval="1m",
            source_type="exchange_native",
            window_start="2026-07-04T01:00:00Z",
            window_end="2026-07-04T02:00:00Z",
            collected_at="2026-07-04T02:01:00Z",
            open_price=3000,
            high_price=3110,
            low_price=2990,
            close_price=3070,
            matured=True,
        ),
    )
