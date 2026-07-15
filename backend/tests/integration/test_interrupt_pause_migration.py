from __future__ import annotations

import asyncio
from collections.abc import Iterator
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import pytest
from sqlalchemy.engine import URL, make_url


BACKEND_ROOT = Path(__file__).resolve().parents[2]
DATABASE_URL = os.getenv("PRODUCT_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    os.getenv("REAL_DATABASE_TESTS") != "1" or not DATABASE_URL,
    reason="requires REAL_DATABASE_TESTS=1 and PRODUCT_DATABASE_URL",
)


def _render_url(url: URL, *, database: str, async_driver: bool) -> str:
    drivername = "postgresql+asyncpg" if async_driver else "postgresql"
    return url.set(drivername=drivername, database=database).render_as_string(
        hide_password=False
    )


async def _create_database(admin_url: str, database: str) -> None:
    connection = await asyncpg.connect(admin_url)
    try:
        await connection.execute(f'CREATE DATABASE "{database}"')
    finally:
        await connection.close()


async def _drop_database(admin_url: str, database: str) -> None:
    connection = await asyncpg.connect(admin_url)
    try:
        await connection.execute(
            "SELECT pg_terminate_backend(pid) "
            "FROM pg_stat_activity "
            "WHERE datname = $1 AND pid <> pg_backend_pid()",
            database,
        )
        await connection.execute(f'DROP DATABASE IF EXISTS "{database}"')
    finally:
        await connection.close()


def _alembic(database_url: str, *args: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PRODUCT_DATABASE_URL"] = database_url
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", *args],
        cwd=BACKEND_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def migration_database() -> Iterator[str]:
    assert DATABASE_URL is not None
    configured_url = make_url(DATABASE_URL)
    database = f"crypto_alert_migration_{uuid4().hex}"
    admin_url = _render_url(configured_url, database="postgres", async_driver=False)
    migration_url = _render_url(configured_url, database=database, async_driver=True)
    asyncio.run(_create_database(admin_url, database))
    try:
        result = _alembic(migration_url, "upgrade", "0006_interrupt_projection")
        assert result.returncode == 0, result.stdout + result.stderr
        yield migration_url
    finally:
        asyncio.run(_drop_database(admin_url, database))


async def _connect(database_url: str) -> asyncpg.Connection:
    configured_url = make_url(database_url)
    dsn = _render_url(
        configured_url,
        database=configured_url.database or "postgres",
        async_driver=False,
    )
    return await asyncpg.connect(dsn)


async def _fetchval(database_url: str, query: str, *args: object) -> Any:
    connection = await _connect(database_url)
    try:
        return await connection.fetchval(query, *args)
    finally:
        await connection.close()


async def _fetchrow(database_url: str, query: str, *args: object) -> asyncpg.Record:
    connection = await _connect(database_url)
    try:
        row = await connection.fetchrow(query, *args)
        assert row is not None
        return row
    finally:
        await connection.close()


async def _execute(database_url: str, query: str, *args: object) -> None:
    connection = await _connect(database_url)
    try:
        await connection.execute(query, *args)
    finally:
        await connection.close()


async def _seed_legacy_run(database_url: str) -> dict[str, UUID]:
    ids = {
        "tenant_id": uuid4(),
        "workspace_id": uuid4(),
        "user_id": uuid4(),
        "thread_id": uuid4(),
        "task_id": uuid4(),
        "run_id": uuid4(),
    }
    connection = await _connect(database_url)
    try:
        async with connection.transaction():
            await connection.execute(
                "INSERT INTO app.tenants (id, external_id, name) VALUES ($1, $2, $3)",
                ids["tenant_id"],
                f"tenant-{ids['tenant_id']}",
                "Migration test tenant",
            )
            await connection.execute(
                "INSERT INTO app.users (id, tenant_id, external_subject, display_name) "
                "VALUES ($1, $2, $3, $4)",
                ids["user_id"],
                ids["tenant_id"],
                f"user-{ids['user_id']}",
                "Migration test user",
            )
            await connection.execute(
                "INSERT INTO app.workspaces (id, tenant_id, external_id, name) "
                "VALUES ($1, $2, $3, $4)",
                ids["workspace_id"],
                ids["tenant_id"],
                f"workspace-{ids['workspace_id']}",
                "Migration test workspace",
            )
            await connection.execute(
                "INSERT INTO app.threads "
                "(id, tenant_id, workspace_id, owner_user_id, official_thread_id) "
                "VALUES ($1, $2, $3, $4, $5)",
                ids["thread_id"],
                ids["tenant_id"],
                ids["workspace_id"],
                ids["user_id"],
                f"official-thread-{ids['thread_id']}",
            )
            await connection.execute(
                "INSERT INTO app.tasks "
                "(id, tenant_id, workspace_id, owner_user_id, thread_id, task_type, "
                "status, request_payload, idempotency_key, request_payload_hash) "
                "VALUES ($1, $2, $3, $4, $5, 'market_analysis', 'waiting_human', "
                "$6::jsonb, $7, $8)",
                ids["task_id"],
                ids["tenant_id"],
                ids["workspace_id"],
                ids["user_id"],
                ids["thread_id"],
                '{"symbol":"BTC-USDT-SWAP","horizon":"4h"}',
                f"task-{ids['task_id']}",
                "0" * 64,
            )
            await connection.execute(
                "INSERT INTO app.runs "
                "(id, tenant_id, workspace_id, owner_user_id, thread_id, task_id, "
                "attempt, status, official_run_id, checkpoint_id, input_payload, "
                "official_assistant_id) "
                "VALUES ($1, $2, $3, $4, $5, $6, 1, 'waiting_human', $7, $8, "
                "$9::jsonb, 'crypto_analysis')",
                ids["run_id"],
                ids["tenant_id"],
                ids["workspace_id"],
                ids["user_id"],
                ids["thread_id"],
                ids["task_id"],
                f"official-run-{ids['run_id']}",
                "root-checkpoint",
                '{"symbol":"BTC-USDT-SWAP","horizon":"4h"}',
            )
    finally:
        await connection.close()
    return ids


async def _insert_interrupt(
    database_url: str,
    ids: dict[str, UUID],
    *,
    interrupt_id: str,
    namespace: str,
    checkpoint_id: str,
    status: str = "pending",
) -> UUID:
    projection_id = uuid4()
    resolved = status in {"responding", "resolved"}
    response = '{"action":"approve"}' if resolved else None
    connection = await _connect(database_url)
    try:
        await connection.execute(
            "INSERT INTO app.interrupt_inbox "
            "(id, tenant_id, workspace_id, owner_user_id, task_id, run_id, "
            "official_interrupt_id, namespace, checkpoint_id, response_version, "
            "status, payload, response, responded_at) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 1, $10, "
            "'{\"kind\":\"artifact_review\"}'::jsonb, $11::jsonb, "
            "CASE WHEN $11::jsonb IS NULL THEN NULL ELSE now() END)",
            projection_id,
            ids["tenant_id"],
            ids["workspace_id"],
            ids["user_id"],
            ids["task_id"],
            ids["run_id"],
            interrupt_id,
            namespace,
            checkpoint_id,
            status,
            response,
        )
    finally:
        await connection.close()
    return projection_id


async def _insert_active_respond_command(
    database_url: str,
    ids: dict[str, UUID],
    *,
    status: str,
) -> None:
    connection = await _connect(database_url)
    try:
        await connection.execute(
            "INSERT INTO app.task_commands "
            "(id, tenant_id, workspace_id, actor_user_id, task_id, thread_id, "
            "command_type, payload, payload_hash, sequence, status, idempotency_key) "
            "VALUES ($1, $2, $3, $4, $5, $6, 'respond', $7::jsonb, $8, 1, $9, $10)",
            uuid4(),
            ids["tenant_id"],
            ids["workspace_id"],
            ids["user_id"],
            ids["task_id"],
            ids["thread_id"],
            '{"interrupt_id":"legacy-interrupt","checkpoint_id":"root-checkpoint",'
            '"namespace":"","response_version":1,"response":{"action":"approve"},'
            '"expired":false}',
            "1" * 64,
            status,
            f"respond-{status}-{ids['task_id']}",
        )
    finally:
        await connection.close()


async def _insert_second_run_and_pause(
    database_url: str,
    ids: dict[str, UUID],
    *,
    pause_status: str,
) -> None:
    run_id = uuid4()
    connection = await _connect(database_url)
    try:
        async with connection.transaction():
            await connection.execute(
                "INSERT INTO app.runs "
                "(id, tenant_id, workspace_id, owner_user_id, thread_id, task_id, "
                "attempt, status, official_run_id, checkpoint_id, input_payload, "
                "official_assistant_id) "
                "VALUES ($1, $2, $3, $4, $5, $6, 2, 'waiting_human', $7, $8, "
                "$9::jsonb, 'crypto_analysis')",
                run_id,
                ids["tenant_id"],
                ids["workspace_id"],
                ids["user_id"],
                ids["thread_id"],
                ids["task_id"],
                f"official-run-{run_id}",
                f"checkpoint-{run_id}",
                '{"symbol":"BTC-USDT-SWAP","horizon":"4h"}',
            )
            await connection.execute(
                "INSERT INTO app.interrupt_pauses "
                "(id, tenant_id, workspace_id, owner_user_id, task_id, run_id, "
                "pause_version, root_thread_id, root_checkpoint_ns, "
                "root_checkpoint_id, root_checkpoint_map, member_set_hash, status) "
                "VALUES ($1, $2, $3, $4, $5, $6, 1, $7, '', $8, '{}'::jsonb, "
                "$9, $10)",
                uuid4(),
                ids["tenant_id"],
                ids["workspace_id"],
                ids["user_id"],
                ids["task_id"],
                run_id,
                f"official-thread-{ids['thread_id']}",
                f"checkpoint-{run_id}",
                "2" * 64,
                pause_status,
            )
    finally:
        await connection.close()


def _assert_failed_before_ddl(
    database_url: str,
    result: subprocess.CompletedProcess[str],
    expected_message: str,
) -> None:
    output = result.stdout + result.stderr
    assert result.returncode != 0, output
    assert expected_message in output
    assert "Resolve or cancel the listed work before retrying revision 0007" in output
    assert (
        asyncio.run(
            _fetchval(
                database_url,
                "SELECT to_regclass('app.interrupt_pauses') IS NULL",
            )
        )
        is True
    )
    assert (
        asyncio.run(
            _fetchval(
                database_url,
                "SELECT NOT EXISTS ("
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = 'app' AND table_name = 'interrupt_inbox' "
                "AND column_name = 'pause_id')",
            )
        )
        is True
    )
    assert (
        asyncio.run(
            _fetchval(database_url, "SELECT version_num FROM app.alembic_version")
        )
        == "0006_interrupt_projection"
    )


def test_empty_database_up_down_round_trip(migration_database: str) -> None:
    upgrade = _alembic(migration_database, "upgrade", "0007_interrupt_pauses")
    assert upgrade.returncode == 0, upgrade.stdout + upgrade.stderr
    assert asyncio.run(
        _fetchval(
            migration_database,
            "SELECT to_regclass('app.interrupt_pauses') IS NOT NULL",
        )
    ) is True

    downgrade = _alembic(migration_database, "downgrade", "0006_interrupt_projection")
    assert downgrade.returncode == 0, downgrade.stdout + downgrade.stderr
    assert asyncio.run(
        _fetchval(migration_database, "SELECT to_regclass('app.interrupt_pauses')")
    ) is None


def test_single_member_legacy_pause_up_down_round_trip(
    migration_database: str,
) -> None:
    ids = asyncio.run(_seed_legacy_run(migration_database))
    projection_id = asyncio.run(
        _insert_interrupt(
            migration_database,
            ids,
            interrupt_id="legacy-single",
            namespace="",
            checkpoint_id="root-checkpoint",
        )
    )

    upgrade = _alembic(migration_database, "upgrade", "0007_interrupt_pauses")
    assert upgrade.returncode == 0, upgrade.stdout + upgrade.stderr
    pause = asyncio.run(
        _fetchrow(
            migration_database,
            "SELECT p.id, p.run_id, p.pause_version, p.root_thread_id, "
            "p.root_checkpoint_ns, p.root_checkpoint_id, p.root_checkpoint_map, "
            "p.status, p.member_set_hash, i.pause_id "
            "FROM app.interrupt_pauses AS p "
            "JOIN app.interrupt_inbox AS i ON i.pause_id = p.id "
            "WHERE i.id = $1",
            projection_id,
        )
    )
    assert pause["run_id"] == ids["run_id"]
    assert pause["pause_version"] == 1
    assert pause["root_thread_id"] == f"official-thread-{ids['thread_id']}"
    assert pause["root_checkpoint_ns"] == ""
    assert pause["root_checkpoint_id"] == "root-checkpoint"
    assert json.loads(pause["root_checkpoint_map"]) == {}
    assert pause["status"] == "pending"
    expected_member_set_hash = sha256(
        json.dumps(
            {
                "root_checkpoint": {
                    "thread_id": f"official-thread-{ids['thread_id']}",
                    "checkpoint_ns": "",
                    "checkpoint_id": "root-checkpoint",
                    "checkpoint_map": {},
                },
                "members": [
                    {
                        "interrupt_id": "legacy-single",
                        "namespace": "",
                        "checkpoint_id": "root-checkpoint",
                    }
                ],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    assert pause["member_set_hash"] == expected_member_set_hash
    assert pause["pause_id"] == pause["id"]

    downgrade = _alembic(migration_database, "downgrade", "0006_interrupt_projection")
    assert downgrade.returncode == 0, downgrade.stdout + downgrade.stderr
    assert asyncio.run(
        _fetchval(
            migration_database,
            "SELECT count(*) FROM app.interrupt_inbox WHERE id = $1",
            projection_id,
        )
    ) == 1
    assert asyncio.run(
        _fetchval(migration_database, "SELECT to_regclass('app.interrupt_pauses')")
    ) is None


def test_consistent_legacy_members_backfill_as_one_pause(
    migration_database: str,
) -> None:
    ids = asyncio.run(_seed_legacy_run(migration_database))
    for interrupt_id in ("legacy-root-review", "legacy-policy-review"):
        asyncio.run(
            _insert_interrupt(
                migration_database,
                ids,
                interrupt_id=interrupt_id,
                namespace="",
                checkpoint_id="root-checkpoint",
            )
        )

    upgrade = _alembic(migration_database, "upgrade", "0007_interrupt_pauses")
    assert upgrade.returncode == 0, upgrade.stdout + upgrade.stderr
    aggregate = asyncio.run(
        _fetchrow(
            migration_database,
            "SELECT count(DISTINCT p.id) AS pause_count, "
            "count(i.id) AS member_count, min(p.status) AS status "
            "FROM app.interrupt_pauses AS p "
            "JOIN app.interrupt_inbox AS i ON i.pause_id = p.id "
            "WHERE p.run_id = $1",
            ids["run_id"],
        )
    )
    assert aggregate["pause_count"] == 1
    assert aggregate["member_count"] == 2
    assert aggregate["status"] == "pending"


def test_partial_unique_index_allows_only_one_active_pause_per_task(
    migration_database: str,
) -> None:
    ids = asyncio.run(_seed_legacy_run(migration_database))
    asyncio.run(
        _insert_interrupt(
            migration_database,
            ids,
            interrupt_id="legacy-single",
            namespace="",
            checkpoint_id="root-checkpoint",
        )
    )
    upgrade = _alembic(migration_database, "upgrade", "0007_interrupt_pauses")
    assert upgrade.returncode == 0, upgrade.stdout + upgrade.stderr
    index_definition = asyncio.run(
        _fetchval(
            migration_database,
            "SELECT indexdef FROM pg_indexes "
            "WHERE schemaname = 'app' "
            "AND indexname = 'uq_interrupt_pauses_one_active_task'",
        )
    )
    assert index_definition is not None
    assert "UNIQUE INDEX" in index_definition
    assert "tenant_id, workspace_id, owner_user_id, task_id" in index_definition
    assert "status" in index_definition
    assert "pending" in index_definition
    assert "responding" in index_definition

    with pytest.raises(asyncpg.UniqueViolationError):
        asyncio.run(
            _insert_second_run_and_pause(
                migration_database,
                ids,
                pause_status="responding",
            )
        )
    asyncio.run(
        _insert_second_run_and_pause(
            migration_database,
            ids,
            pause_status="resolved",
        )
    )

    downgrade = _alembic(migration_database, "downgrade", "0006_interrupt_projection")
    assert downgrade.returncode == 0, downgrade.stdout + downgrade.stderr
    assert asyncio.run(
        _fetchval(
            migration_database,
            "SELECT to_regclass('app.uq_interrupt_pauses_one_active_task')",
        )
    ) is None


@pytest.mark.parametrize("command_status", ["pending", "dispatching"])
def test_active_legacy_respond_command_fails_before_ddl(
    migration_database: str,
    command_status: str,
) -> None:
    ids = asyncio.run(_seed_legacy_run(migration_database))
    asyncio.run(
        _insert_interrupt(
            migration_database,
            ids,
            interrupt_id="legacy-interrupt",
            namespace="",
            checkpoint_id="root-checkpoint",
            status="responding",
        )
    )
    asyncio.run(
        _insert_active_respond_command(
            migration_database,
            ids,
            status=command_status,
        )
    )

    result = _alembic(migration_database, "upgrade", "0007_interrupt_pauses")

    _assert_failed_before_ddl(
        migration_database,
        result,
        "active legacy respond command(s)",
    )


def test_multiple_checkpoint_pairs_for_one_run_fail_before_ddl(
    migration_database: str,
) -> None:
    ids = asyncio.run(_seed_legacy_run(migration_database))
    asyncio.run(
        _insert_interrupt(
            migration_database,
            ids,
            interrupt_id="root-interrupt",
            namespace="",
            checkpoint_id="root-checkpoint",
        )
    )
    asyncio.run(
        _insert_interrupt(
            migration_database,
            ids,
            interrupt_id="nested-interrupt",
            namespace="child:review",
            checkpoint_id="child-checkpoint",
        )
    )

    result = _alembic(migration_database, "upgrade", "0007_interrupt_pauses")

    _assert_failed_before_ddl(
        migration_database,
        result,
        "multiple namespace/checkpoint pairs",
    )


def test_non_root_legacy_checkpoint_fails_before_ddl(
    migration_database: str,
) -> None:
    ids = asyncio.run(_seed_legacy_run(migration_database))
    asyncio.run(
        _insert_interrupt(
            migration_database,
            ids,
            interrupt_id="nested-only-interrupt",
            namespace="child:review",
            checkpoint_id="child-checkpoint",
        )
    )

    result = _alembic(migration_database, "upgrade", "0007_interrupt_pauses")

    _assert_failed_before_ddl(
        migration_database,
        result,
        "non-root checkpoint namespace",
    )


def test_missing_official_thread_identity_fails_before_ddl(
    migration_database: str,
) -> None:
    ids = asyncio.run(_seed_legacy_run(migration_database))
    asyncio.run(
        _insert_interrupt(
            migration_database,
            ids,
            interrupt_id="legacy-interrupt",
            namespace="",
            checkpoint_id="root-checkpoint",
        )
    )
    asyncio.run(
        _execute(
            migration_database,
            "UPDATE app.threads SET official_thread_id = NULL WHERE id = $1",
            ids["thread_id"],
        )
    )

    result = _alembic(migration_database, "upgrade", "0007_interrupt_pauses")

    _assert_failed_before_ddl(
        migration_database,
        result,
        "no official thread identity",
    )


def test_mixed_member_statuses_fail_before_ddl(migration_database: str) -> None:
    ids = asyncio.run(_seed_legacy_run(migration_database))
    asyncio.run(
        _insert_interrupt(
            migration_database,
            ids,
            interrupt_id="pending-interrupt",
            namespace="",
            checkpoint_id="root-checkpoint",
        )
    )
    asyncio.run(
        _insert_interrupt(
            migration_database,
            ids,
            interrupt_id="resolved-interrupt",
            namespace="",
            checkpoint_id="root-checkpoint",
            status="resolved",
        )
    )

    result = _alembic(migration_database, "upgrade", "0007_interrupt_pauses")

    _assert_failed_before_ddl(
        migration_database,
        result,
        "mixed member statuses",
    )
