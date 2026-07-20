from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
from hashlib import sha256
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
from typing import AsyncIterator
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from crypto_alert_v2.api.schemas import TerminalGraphOutput
from crypto_alert_v2.persistence.base import Base
from crypto_alert_v2.persistence.models import (
    Membership,
    Run,
    Task,
    TaskCommand,
    Tenant,
    Thread,
    User,
    Workspace,
)
from tests.integration.support.fake_agent_server import FakeAgentServer
from tests.integration.support.actor_cleanup import delete_tenant_test_data


PRODUCT_DATABASE_URL = os.getenv("PRODUCT_DATABASE_URL")
REAL_DATABASE_TESTS = os.getenv("REAL_DATABASE_TESTS") == "1"
BACKEND_ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.skipif(
    not REAL_DATABASE_TESTS or not PRODUCT_DATABASE_URL,
    reason="requires REAL_DATABASE_TESTS=1 and PRODUCT_DATABASE_URL",
)


@dataclass(frozen=True, slots=True)
class SeededCommand:
    tenant_id: UUID
    task_id: UUID
    command_id: UUID


@pytest_asyncio.fixture
async def database() -> AsyncIterator[
    tuple[AsyncEngine, async_sessionmaker[AsyncSession]]
]:
    if not REAL_DATABASE_TESTS or PRODUCT_DATABASE_URL is None:
        pytest.skip("requires REAL_DATABASE_TESTS=1 and PRODUCT_DATABASE_URL")
    engine = create_async_engine(PRODUCT_DATABASE_URL, pool_pre_ping=True)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield engine, session_factory
    finally:
        await engine.dispose()


async def _seed_committed_command(
    session_factory: async_sessionmaker[AsyncSession],
) -> SeededCommand:
    tenant_id = uuid4()
    workspace_id = uuid4()
    user_id = uuid4()
    thread_id = uuid4()
    task_id = uuid4()
    command_id = uuid4()
    unique = uuid4().hex
    request_payload = {
        "symbol": "BTC-USDT-SWAP",
        "horizon": "4h",
        "query_text": f"process recovery harness {unique}",
        "notify": False,
    }
    payload_hash = sha256(
        json.dumps(request_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    async with session_factory() as session, session.begin():
        session.add(
            Tenant(
                id=tenant_id,
                external_id=f"worker-recovery-tenant-{unique}",
                name="Worker recovery test tenant",
            )
        )
        await session.flush()
        session.add_all(
            [
                User(
                    id=user_id,
                    tenant_id=tenant_id,
                    identity_issuer="worker-recovery-test",
                    external_subject=f"worker-recovery-user-{unique}",
                    display_name="Worker recovery test user",
                ),
                Workspace(
                    id=workspace_id,
                    tenant_id=tenant_id,
                    external_id=f"worker-recovery-workspace-{unique}",
                    name="Worker recovery test workspace",
                    review_policy="bypass",
                ),
            ]
        )
        await session.flush()
        session.add_all(
            [
                Membership(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    user_id=user_id,
                    role="member",
                    permissions=["analysis:read", "analysis:write"],
                ),
                Thread(
                    id=thread_id,
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    owner_user_id=user_id,
                    title="Worker process recovery",
                    context={},
                ),
            ]
        )
        await session.flush()
        session.add(
            Task(
                id=task_id,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                owner_user_id=user_id,
                thread_id=thread_id,
                task_type="market_analysis",
                status="queued",
                idempotency_key=f"worker-recovery-{unique}",
                request_payload_hash=payload_hash,
                request_payload=request_payload,
            )
        )
        await session.flush()
        session.add(
            TaskCommand(
                id=command_id,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                actor_user_id=user_id,
                task_id=task_id,
                thread_id=thread_id,
                command_type="submit",
                payload=request_payload,
                payload_hash=payload_hash,
                sequence=1,
                status="pending",
                attempt=0,
                idempotency_key=f"submit:{task_id}",
            )
        )

    return SeededCommand(
        tenant_id=tenant_id,
        task_id=task_id,
        command_id=command_id,
    )


def _start_worker(
    *,
    cwd: Path,
    database_url: str,
    agent_server_url: str,
    local_token: str,
    worker_id: str,
) -> subprocess.Popen[bytes]:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        health_port = listener.getsockname()[1]
    environment = {
        "AGENT_ASSISTANT_ID": "crypto_analysis",
        "AGENT_SERVER_LOCAL_TOKEN": local_token,
        "AGENT_SERVER_URL": agent_server_url,
        "APP_ENVIRONMENT": "test",
        "PRODUCT_DATABASE_URL": database_url,
        "PYTHONPATH": str(BACKEND_ROOT / "src"),
        "PYTHONUNBUFFERED": "1",
        "WORKER_HEALTH_HOST": "127.0.0.1",
        "WORKER_HEALTH_PORT": str(health_port),
    }
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "crypto_alert_v2.workers",
            "--worker-id",
            worker_id,
            "--poll-interval",
            "0.05",
            "--shutdown-budget-seconds",
            "1",
        ],
        cwd=cwd,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


async def _wait_for_event(event: object, *, timeout: float, description: str) -> None:
    wait = getattr(event, "wait")
    reached = await asyncio.to_thread(wait, timeout)
    assert reached, f"timed out waiting for {description}"


async def _wait_for_completion(
    session_factory: async_sessionmaker[AsyncSession],
    command_id: UUID,
    process: subprocess.Popen[bytes],
    *,
    timeout: float,
) -> tuple[TaskCommand, Run]:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        async with session_factory() as session:
            command = await session.scalar(
                select(TaskCommand).where(TaskCommand.id == command_id)
            )
            product_run = await session.scalar(
                select(Run)
                .join(TaskCommand, TaskCommand.task_id == Run.task_id)
                .where(TaskCommand.id == command_id)
            )
        if (
            command is not None
            and product_run is not None
            and command.status == "dispatched"
            and product_run.status == "failed"
        ):
            return command, product_run
        if process.poll() is not None:
            raise AssertionError(
                f"successor worker exited before recovery (code {process.returncode})"
            )
        await asyncio.sleep(0.05)
    raise AssertionError("timed out waiting for successor database projection")


async def _stop_worker(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is None:
        process.send_signal(signal.SIGTERM)
    try:
        await asyncio.to_thread(process.wait, 5)
    except subprocess.TimeoutExpired:
        process.kill()
        await asyncio.to_thread(process.wait, 5)


async def _expire_command_lease(
    session_factory: async_sessionmaker[AsyncSession],
    command_id: UUID,
) -> None:
    async with session_factory() as session, session.begin():
        await session.execute(
            update(TaskCommand)
            .where(TaskCommand.id == command_id)
            .values(lease_expires_at=func.now() - timedelta(seconds=1))
        )
    async with session_factory() as session:
        lease_is_expired = await session.scalar(
            select(TaskCommand.lease_expires_at <= func.now()).where(
                TaskCommand.id == command_id
            )
        )
    assert lease_is_expired is True


def _post_join(agent_server_url: str, thread_id: str, run_id: str) -> dict[str, object]:
    parsed = urlsplit(agent_server_url)
    connection = HTTPConnection(parsed.hostname, parsed.port, timeout=5)
    try:
        connection.request(
            "POST",
            f"/threads/{thread_id}/runs/{run_id}/join",
            body=b"{}",
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        payload = json.loads(response.read())
        assert response.status == 200
        assert isinstance(payload, dict)
        return payload
    finally:
        connection.close()


@pytest.mark.asyncio
async def test_sigkill_after_remote_accept_recovers_without_duplicate_create(
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
    tmp_path: Path,
) -> None:
    _, session_factory = database
    assert PRODUCT_DATABASE_URL is not None
    seeded = await _seed_committed_command(session_factory)
    fake = FakeAgentServer()
    fake.start()
    local_token = secrets.token_urlsafe(32)
    first_worker_id = f"recovery-first-{uuid4().hex}"
    successor_worker_id = f"recovery-successor-{uuid4().hex}"
    first: subprocess.Popen[bytes] | None = None
    successor: subprocess.Popen[bytes] | None = None

    try:
        first = _start_worker(
            cwd=tmp_path,
            database_url=PRODUCT_DATABASE_URL,
            agent_server_url=fake.url,
            local_token=local_token,
            worker_id=first_worker_id,
        )
        await _wait_for_event(
            fake.run_accepted,
            timeout=15,
            description="the fake Agent Server to accept the remote Run",
        )

        async with session_factory() as session:
            command = await session.scalar(
                select(TaskCommand).where(TaskCommand.id == seeded.command_id)
            )
            product_run = await session.scalar(
                select(Run).where(Run.task_id == seeded.task_id)
            )
        assert command is not None
        assert product_run is not None
        assert command.status == "dispatching"
        assert command.lease_owner == f"{first_worker_id}:command"
        assert command.attempt == 1
        assert command.official_run_id is None
        assert product_run.failure_code == "agent_submit_create_intent"
        assert product_run.official_run_id is None
        assert fake.count("POST", "/threads/{id}/runs") == 1

        first.kill()
        first_returncode = await asyncio.to_thread(first.wait, 5)
        assert first_returncode == -signal.SIGKILL
        fake.release_run_response.set()

        await _expire_command_lease(session_factory, seeded.command_id)

        successor = _start_worker(
            cwd=tmp_path,
            database_url=PRODUCT_DATABASE_URL,
            agent_server_url=fake.url,
            local_token=local_token,
            worker_id=successor_worker_id,
        )
        await _wait_for_event(
            fake.join_requested,
            timeout=15,
            description="the successor to join the discovered remote Run",
        )
        recovered_command, recovered_run = await _wait_for_completion(
            session_factory,
            seeded.command_id,
            successor,
            timeout=15,
        )

        assert recovered_command.attempt >= 2
        assert recovered_command.official_run_id == recovered_run.official_run_id
        assert recovered_run.official_run_id is not None
        assert recovered_run.failure_code == "controlled_process_recovery"
        assert fake.count("GET", "/threads/{id}/runs") >= 1
        assert fake.count("GET", "/threads/{id}/runs/{run_id}") >= 1
        assert fake.count("GET", "/threads/{id}/runs/{run_id}/stream") >= 1
        assert fake.count("GET", "/threads/{id}/state") >= 1
        assert fake.count("GET", "/threads/{id}/runs/{run_id}/join") >= 1
        assert fake.count("POST", "/threads/{id}/runs") == 1

        post_join_output = await asyncio.to_thread(
            _post_join,
            fake.url,
            str(recovered_run.thread_id),
            recovered_run.official_run_id,
        )
        terminal = TerminalGraphOutput.model_validate(post_join_output)
        assert terminal.terminal_status == "failed"
        assert fake.count("POST", "/threads/{id}/runs/{run_id}/join") == 1
    finally:
        fake.release_run_response.set()
        if first is not None:
            await _stop_worker(first)
        if successor is not None:
            await _stop_worker(successor)
        fake.close()
        async with session_factory() as session, session.begin():
            await delete_tenant_test_data(session, seeded.tenant_id)


@pytest.mark.asyncio
async def test_sigkill_after_product_registration_reuses_persisted_remote_handle(
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
    tmp_path: Path,
) -> None:
    _, session_factory = database
    assert PRODUCT_DATABASE_URL is not None
    seeded = await _seed_committed_command(session_factory)
    fake = FakeAgentServer()
    fake.block_run_status = True
    fake.release_run_response.set()
    fake.start()
    local_token = secrets.token_urlsafe(32)
    first_worker_id = f"registered-first-{uuid4().hex}"
    successor_worker_id = f"registered-successor-{uuid4().hex}"
    first: subprocess.Popen[bytes] | None = None
    successor: subprocess.Popen[bytes] | None = None

    try:
        first = _start_worker(
            cwd=tmp_path,
            database_url=PRODUCT_DATABASE_URL,
            agent_server_url=fake.url,
            local_token=local_token,
            worker_id=first_worker_id,
        )
        await _wait_for_event(
            fake.run_status_requested,
            timeout=15,
            description="the first worker to request registered Run status",
        )

        async with session_factory() as session:
            command = await session.scalar(
                select(TaskCommand).where(TaskCommand.id == seeded.command_id)
            )
            product_run = await session.scalar(
                select(Run).where(Run.task_id == seeded.task_id)
            )
            product_thread = await session.scalar(
                select(Thread)
                .join(Run, Run.thread_id == Thread.id)
                .where(Run.task_id == seeded.task_id)
            )
        assert command is not None
        assert product_run is not None
        assert product_thread is not None
        assert command.status == "dispatching"
        assert command.lease_owner == f"{first_worker_id}:command"
        assert command.attempt == 1
        assert command.official_run_id is not None
        assert product_run.official_run_id == command.official_run_id
        assert product_run.official_assistant_id is not None
        assert product_thread.official_thread_id == str(product_thread.id)
        assert product_run.failure_code is None
        assert fake.count("POST", "/threads/{id}/runs") == 1
        discovery_count_before_kill = fake.count("GET", "/threads/{id}/runs")
        assert discovery_count_before_kill == 1

        first.kill()
        first_returncode = await asyncio.to_thread(first.wait, 5)
        assert first_returncode == -signal.SIGKILL
        fake.release_run_status.set()
        await _expire_command_lease(session_factory, seeded.command_id)

        successor = _start_worker(
            cwd=tmp_path,
            database_url=PRODUCT_DATABASE_URL,
            agent_server_url=fake.url,
            local_token=local_token,
            worker_id=successor_worker_id,
        )
        recovered_command, recovered_run = await _wait_for_completion(
            session_factory,
            seeded.command_id,
            successor,
            timeout=15,
        )

        assert recovered_command.attempt >= 2
        assert recovered_command.official_run_id == command.official_run_id
        assert recovered_run.official_run_id == command.official_run_id
        assert recovered_run.failure_code == "controlled_process_recovery"
        assert fake.count("POST", "/threads") == 1
        assert fake.count("POST", "/threads/{id}/runs") == 1
        assert fake.count("GET", "/threads/{id}/runs") == discovery_count_before_kill
        assert fake.count("GET", "/threads/{id}/runs/{run_id}") >= 2
        assert fake.count("GET", "/threads/{id}/runs/{run_id}/stream") >= 2
        assert fake.count("GET", "/threads/{id}/runs/{run_id}/join") >= 1
    finally:
        fake.release_run_response.set()
        fake.release_run_status.set()
        if first is not None:
            await _stop_worker(first)
        if successor is not None:
            await _stop_worker(successor)
        fake.close()
        async with session_factory() as session, session.begin():
            await delete_tenant_test_data(session, seeded.tenant_id)
