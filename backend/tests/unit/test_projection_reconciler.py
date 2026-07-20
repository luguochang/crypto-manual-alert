from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest

from crypto_alert_v2.api.agent_server import RemoteRunHandle, RemoteRunState
from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.projections.reconciler import (
    ProductProjectionReconciler,
    ProjectionReconciliationLease,
)


NOW = datetime(2026, 7, 17, 8, 0, tzinfo=UTC)


def projection_lease(
    *,
    remote_handle: RemoteRunHandle | None = None,
) -> ProjectionReconciliationLease:
    return ProjectionReconciliationLease(
        command_id=UUID("00000000-0000-0000-0000-000000000001"),
        command_attempt=2,
        command_sequence=3,
        product_run_id=UUID("00000000-0000-0000-0000-000000000002"),
        product_thread_id=UUID("00000000-0000-0000-0000-000000000003"),
        task_id=UUID("00000000-0000-0000-0000-000000000004"),
        projection_fence=1,
        worker_id="projection-worker",
        actor=ActorContext(
            tenant_id="tenant-1",
            workspace_id="workspace-1",
            user_id="user-1",
            roles=("member",),
            permissions=("analysis:read", "analysis:write"),
        ),
        remote_thread_id="official-thread-1",
        remote_handle=remote_handle,
    )


class RecordingStore:
    def __init__(
        self,
        lease: ProjectionReconciliationLease | None,
        *,
        observe_result: bool = True,
    ) -> None:
        self.lease = lease
        self.observe_result = observe_result
        self.claims: list[dict[str, Any]] = []
        self.registered: list[
            tuple[ProjectionReconciliationLease, RemoteRunHandle]
        ] = []
        self.absences: list[ProjectionReconciliationLease] = []
        self.observed: list[tuple[RemoteRunHandle, RemoteRunState]] = []
        self.released: list[ProjectionReconciliationLease] = []
        self.released_workers: list[str] = []

    async def claim_next(self, **kwargs: Any) -> ProjectionReconciliationLease | None:
        self.claims.append(kwargs)
        return self.lease

    async def register_remote_handle(
        self,
        lease: ProjectionReconciliationLease,
        handle: RemoteRunHandle,
        *,
        now: datetime,
    ) -> bool:
        del now
        self.registered.append((lease, handle))
        return True

    async def observe_remote_absence(
        self,
        lease: ProjectionReconciliationLease,
        *,
        now: datetime,
    ) -> bool:
        del now
        self.absences.append(lease)
        return True

    async def observe_remote_state(
        self,
        lease: ProjectionReconciliationLease,
        handle: RemoteRunHandle,
        state: RemoteRunState,
        *,
        now: datetime,
    ) -> bool:
        del lease, now
        self.observed.append((handle, state))
        return self.observe_result

    async def release(
        self,
        lease: ProjectionReconciliationLease,
        *,
        now: datetime,
    ) -> bool:
        del now
        self.released.append(lease)
        return True

    async def release_owned(self, *, worker_id: str, now: datetime) -> None:
        del now
        self.released_workers.append(worker_id)


class ReadOnlyRunner:
    def __init__(
        self,
        *,
        found: RemoteRunHandle | None,
        state: RemoteRunState,
        get_delay: float = 0,
    ) -> None:
        self.found = found
        self.state = state
        self.get_delay = get_delay
        self.calls: list[str] = []
        self.find_kwargs: dict[str, Any] | None = None
        self.start_calls = 0
        self.join_calls = 0

    async def find(self, **kwargs: Any) -> RemoteRunHandle | None:
        self.calls.append("find")
        self.find_kwargs = kwargs
        return self.found

    def authorize(
        self,
        handle: RemoteRunHandle,
        actor: ActorContext,
    ) -> RemoteRunHandle:
        del actor
        self.calls.append("authorize")
        return replace(handle, authorization="Bearer synthetic-test-token")

    async def get(self, handle: RemoteRunHandle) -> RemoteRunState:
        assert handle.authorization == "Bearer synthetic-test-token"
        self.calls.append("get")
        if self.get_delay:
            await asyncio.sleep(self.get_delay)
        return self.state

    async def start(self, **kwargs: Any) -> RemoteRunHandle:
        del kwargs
        self.start_calls += 1
        raise AssertionError("projection reconciliation must never start a Run")

    async def join(self, handle: RemoteRunHandle) -> dict[str, Any]:
        del handle
        self.join_calls += 1
        raise AssertionError("projection reconciliation must not join terminal output")


def reconciler(
    store: RecordingStore,
    runner: ReadOnlyRunner,
    **overrides: Any,
) -> ProductProjectionReconciler:
    values = {
        "store": store,
        "runner": runner,
        "worker_id": "projection-worker",
        "clock": lambda: NOW,
    }
    values.update(overrides)
    return ProductProjectionReconciler(**values)


@pytest.mark.asyncio
async def test_no_stale_projection_does_not_read_agent_server() -> None:
    store = RecordingStore(None)
    runner = ReadOnlyRunner(found=None, state=RemoteRunState(status="running"))

    assert await reconciler(store, runner).dispatch_once() is False

    assert runner.calls == []
    assert store.released == []


@pytest.mark.asyncio
async def test_missing_handle_is_discovered_and_terminal_state_is_observed_read_only() -> (
    None
):
    lease = projection_lease()
    handle = RemoteRunHandle(
        assistant_id="official-assistant",
        thread_id=lease.remote_thread_id,
        run_id="official-run-1",
    )
    store = RecordingStore(lease)
    runner = ReadOnlyRunner(found=handle, state=RemoteRunState(status="success"))

    assert await reconciler(store, runner).dispatch_once() is True

    assert runner.calls == ["find", "authorize", "get"]
    assert runner.find_kwargs == {
        "actor": lease.actor,
        "task_id": str(lease.task_id),
        "product_thread_id": lease.remote_thread_id,
        "product_run_id": str(lease.product_run_id),
    }
    assert store.registered == [(lease, handle)]
    assert store.observed == [
        (replace(handle, authorization="Bearer synthetic-test-token"), runner.state)
    ]
    assert store.released == [lease]
    assert runner.start_calls == runner.join_calls == 0


@pytest.mark.asyncio
async def test_registered_handle_skips_discovery_and_lost_fence_is_a_noop() -> None:
    handle = RemoteRunHandle(
        assistant_id="official-assistant",
        thread_id="official-thread-1",
        run_id="official-run-1",
    )
    lease = projection_lease(remote_handle=handle)
    store = RecordingStore(lease, observe_result=False)
    runner = ReadOnlyRunner(found=None, state=RemoteRunState(status="error"))

    assert await reconciler(store, runner).dispatch_once() is False

    assert runner.calls == ["authorize", "get"]
    assert store.registered == [(lease, handle)]
    assert store.released == [lease]
    assert runner.start_calls == runner.join_calls == 0


@pytest.mark.asyncio
async def test_missing_official_run_is_released_without_guessing_or_starting() -> None:
    lease = projection_lease()
    store = RecordingStore(lease)
    runner = ReadOnlyRunner(found=None, state=RemoteRunState(status="running"))

    assert await reconciler(store, runner).dispatch_once() is True

    assert runner.calls == ["find"]
    assert store.registered == []
    assert store.absences == [lease]
    assert store.observed == []
    assert store.released == [lease]
    assert runner.start_calls == runner.join_calls == 0


@pytest.mark.asyncio
async def test_remote_timeout_releases_claimed_projection_lease() -> None:
    handle = RemoteRunHandle(
        assistant_id="official-assistant",
        thread_id="official-thread-1",
        run_id="official-run-1",
    )
    lease = projection_lease(remote_handle=handle)
    store = RecordingStore(lease)
    runner = ReadOnlyRunner(
        found=None,
        state=RemoteRunState(status="running"),
        get_delay=0.1,
    )

    with pytest.raises(TimeoutError):
        await reconciler(
            store,
            runner,
            lease_seconds=3,
            remote_timeout_seconds=0.01,
        ).dispatch_once()

    assert store.observed == []
    assert store.released == [lease]
    assert runner.start_calls == runner.join_calls == 0


@pytest.mark.asyncio
async def test_shutdown_releases_every_owned_lease() -> None:
    store = RecordingStore(None)
    runner = ReadOnlyRunner(found=None, state=RemoteRunState(status="running"))

    await reconciler(store, runner).release_owned_leases()

    assert store.released_workers == ["projection-worker"]
