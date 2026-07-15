from __future__ import annotations

from types import SimpleNamespace

from pydantic import SecretStr
import pytest

from crypto_alert_v2.api.agent_server import (
    RemoteCheckpoint,
    RemoteInterrupt,
    RemoteInterruptSet,
)
from crypto_alert_v2.commands.seed_hitl_e2e import (
    ARTIFACT,
    FIXTURE_ASSISTANTS,
    FIXTURE_INTERRUPT_COUNTS,
    GRAPH_STATE,
    _authorization,
    _interrupt_member_set_hash,
    _loopback_url,
    _request_hash,
)
from crypto_alert_v2.domain.models import Artifact


@pytest.mark.parametrize(
    "value",
    (
        "http://127.0.0.1:8123",
        "http://127.8.9.10:8123",
        "http://localhost:8123",
        "http://[::1]:8123",
    ),
)
def test_seed_accepts_only_valid_loopback_urls(value: str) -> None:
    assert _loopback_url(value) is True


@pytest.mark.parametrize(
    "value",
    (
        "https://agent.example.com",
        "http://192.0.2.10:8123",
        "ftp://127.0.0.1:8123",
        "not-a-url",
    ),
)
def test_seed_rejects_non_loopback_or_invalid_urls(value: str) -> None:
    assert _loopback_url(value) is False


def test_seed_authorization_is_local_only_and_requires_a_token() -> None:
    local = SimpleNamespace(
        app_environment="local",
        agent_server_url="http://127.0.0.1:8123",
        agent_server_local_token=SecretStr("local-secret"),
    )
    assert _authorization(local) == "Bearer local-secret"

    with pytest.raises(RuntimeError, match="loopback"):
        _authorization(
            SimpleNamespace(
                app_environment="local",
                agent_server_url="https://agent.example.com",
                agent_server_local_token=SecretStr("local-secret"),
            )
        )
    with pytest.raises(RuntimeError, match="outside local test"):
        _authorization(
            SimpleNamespace(
                app_environment="production",
                agent_server_url="http://127.0.0.1:8123",
                agent_server_local_token=SecretStr("local-secret"),
            )
        )
    with pytest.raises(RuntimeError, match="AGENT_SERVER_LOCAL_TOKEN"):
        _authorization(
            SimpleNamespace(
                app_environment="test",
                agent_server_url="http://127.0.0.1:8123",
                agent_server_local_token=None,
            )
        )


def test_seed_state_contains_a_valid_reviewable_artifact() -> None:
    artifact = Artifact.model_validate(ARTIFACT)

    assert artifact.status == "draft"
    assert artifact.risk_verdict.allowed is True
    assert artifact.evidence_verdict.sufficient is True
    assert GRAPH_STATE["artifact"] == ARTIFACT
    assert GRAPH_STATE["review_policy"] == "required"
    assert GRAPH_STATE["terminal_status"] == "running"
    assert len(_request_hash()) == 64


def test_seed_fixture_registry_requires_real_official_interrupt_counts() -> None:
    assert FIXTURE_ASSISTANTS == {
        "canonical": "crypto_analysis",
        "multi_interrupt": "multi_interrupt_fixture",
    }
    assert FIXTURE_INTERRUPT_COUNTS == {
        "canonical": 1,
        "multi_interrupt": 2,
    }


def test_interrupt_member_set_hash_uses_root_checkpoint_and_sorted_members() -> None:
    checkpoint = RemoteCheckpoint(
        thread_id="official-thread",
        checkpoint_ns="",
        checkpoint_id="root-checkpoint",
        checkpoint_map={"child": "nested-checkpoint"},
    )
    first = RemoteInterrupt(
        interrupt_id="interrupt-a",
        namespace="",
        checkpoint_id="root-checkpoint",
        value={"kind": "review"},
    )
    second = RemoteInterrupt(
        interrupt_id="interrupt-b",
        namespace="child:",
        checkpoint_id="nested-checkpoint",
        value={"kind": "review"},
    )
    forward = RemoteInterruptSet(checkpoint=checkpoint, interrupts=(first, second))
    reversed_members = RemoteInterruptSet(
        checkpoint=checkpoint,
        interrupts=(second, first),
    )

    member_set_hash = _interrupt_member_set_hash(forward)

    assert len(member_set_hash) == 64
    assert member_set_hash == _interrupt_member_set_hash(reversed_members)
    assert member_set_hash != _interrupt_member_set_hash(
        RemoteInterruptSet(
            checkpoint=RemoteCheckpoint(
                thread_id="official-thread",
                checkpoint_ns="",
                checkpoint_id="different-root",
                checkpoint_map={"child": "nested-checkpoint"},
            ),
            interrupts=(first, second),
        )
    )
    assert member_set_hash != _interrupt_member_set_hash(
        RemoteInterruptSet(checkpoint=checkpoint, interrupts=(first,))
    )
