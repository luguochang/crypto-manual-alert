from __future__ import annotations

from pydantic import ValidationError
import pytest

from crypto_alert_v2.evaluation.frozen_replay import (
    FrozenReplayPacket,
    freeze_replay_packet,
    rule_judge,
)


def _packet() -> FrozenReplayPacket:
    return freeze_replay_packet(
        request={"symbol": "BTC-USDT-SWAP", "horizon": "15m"},
        versions={"prompt": "market-v1", "graph": "graph-v2"},
        market={"source": "exchange_native", "last": "65627.1"},
        evidence=({"source": "tavily", "content_hash": "abc"},),
        gates={
            "evidence": {"sufficient": True},
            "risk": {"allowed": True},
        },
        observed_output={"terminal_status": "succeeded", "main_action": "no_trade"},
    )


def test_frozen_packet_is_deterministic_and_disables_live_effects() -> None:
    first = _packet()
    second = _packet()

    assert first.source_hash == second.source_hash
    assert first.allow_live_fetch is False
    assert first.allow_live_side_effects is False


def test_frozen_packet_rejects_mutation_under_the_old_hash() -> None:
    packet = _packet()
    payload = packet.model_dump(mode="json")
    payload["request"]["horizon"] = "4h"

    with pytest.raises(ValidationError, match="source_hash"):
        FrozenReplayPacket.model_validate(payload)


def test_rule_judge_uses_only_the_frozen_packet() -> None:
    result = rule_judge(_packet())

    assert result.model_dump() == {
        "structure": 1.0,
        "evidence": 1.0,
        "risk": 1.0,
        "product_output": 1.0,
        "reasons": (),
    }
