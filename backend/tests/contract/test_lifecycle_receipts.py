from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.lifecycle.adapters import (
    AegraCheckpointAdapter,
    AegraStoreAdapter,
    NotConfiguredLifecycleAdapter,
)


ROOT = Path(__file__).resolve().parents[3]


class FakeThreads:
    def __init__(self) -> None:
        self.rows = [{"thread_id": "thread-1"}, {"thread_id": "thread-2"}]
        self.search_calls: list[dict[str, object]] = []
        self.deleted: list[str] = []

    async def search(self, **kwargs: object) -> list[dict[str, str]]:
        self.search_calls.append(kwargs)
        limit = int(kwargs["limit"])
        offset = int(kwargs["offset"])
        return self.rows[offset : offset + limit]

    async def delete(self, thread_id: str, **kwargs: object) -> None:
        assert kwargs["headers"]
        self.deleted.append(thread_id)
        self.rows = [row for row in self.rows if row["thread_id"] != thread_id]


class FakeStore:
    def __init__(self) -> None:
        self.items = {
            ("alpha",): {"one": {"value": 1}},
            ("beta",): {"two": {"value": 2}},
        }
        self.deleted: list[tuple[tuple[str, ...], str]] = []

    async def list_namespaces(self, **kwargs: object) -> dict[str, object]:
        assert kwargs["prefix"] == []
        namespaces = [list(namespace) for namespace, items in self.items.items() if items]
        offset = int(kwargs["offset"])
        limit = int(kwargs["limit"])
        return {"namespaces": namespaces[offset : offset + limit]}

    async def search_items(
        self, namespace: list[str], **kwargs: object
    ) -> dict[str, object]:
        offset = int(kwargs["offset"])
        limit = int(kwargs["limit"])
        items = [
            {"namespace": namespace, "key": key, "value": value}
            for key, value in self.items.get(tuple(namespace), {}).items()
        ]
        return {"items": items[offset : offset + limit]}

    async def delete_item(
        self, namespace: list[str], key: str, **kwargs: object
    ) -> None:
        assert kwargs["headers"]
        self.items[tuple(namespace)].pop(key)
        self.deleted.append((tuple(namespace), key))


def _actor() -> ActorContext:
    return ActorContext(
        tenant_id="tenant-a",
        workspace_id="workspace-a",
        user_id="user-a",
        identity_issuer="https://issuer.example",
        context_id=uuid4(),
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )


@pytest.mark.asyncio
async def test_aegra_checkpoint_adapter_uses_official_thread_owner_boundary() -> None:
    threads = FakeThreads()
    adapter = AegraCheckpointAdapter(
        client=SimpleNamespace(threads=threads),
        authorization_provider=lambda actor: f"Bearer token-for-{actor.user_id}",
        page_size=1,
    )

    deleted = await adapter.delete(_actor())
    scanned = await adapter.survivor_scan(_actor())

    assert deleted.outcome == "succeeded"
    assert deleted.affected_count == 2
    assert threads.deleted == ["thread-1", "thread-2"]
    assert scanned.outcome == "succeeded"
    assert scanned.survivor_count == 0
    assert all(call["metadata"] for call in threads.search_calls)


@pytest.mark.asyncio
async def test_aegra_store_adapter_deletes_items_and_scans_actor_namespace() -> None:
    store = FakeStore()
    adapter = AegraStoreAdapter(
        client=SimpleNamespace(store=store),
        authorization_provider=lambda actor: f"Bearer token-for-{actor.user_id}",
        page_size=1,
    )

    deleted = await adapter.delete(_actor())
    scanned = await adapter.survivor_scan(_actor())

    assert deleted.outcome == "succeeded"
    assert deleted.affected_count == 2
    assert store.deleted == [(('alpha',), "one"), (('beta',), "two")]
    assert scanned.outcome == "succeeded"
    assert scanned.survivor_count == 0


@pytest.mark.asyncio
async def test_not_configured_system_is_not_claimed_as_deleted() -> None:
    adapter = NotConfiguredLifecycleAdapter(
        "object_storage", reason="no object storage backend configured"
    )

    deleted = await adapter.delete(_actor())
    scanned = await adapter.survivor_scan(_actor())

    assert deleted.outcome == "not_applicable"
    assert deleted.evidence["inventory"] == "not_configured"
    assert scanned.outcome == "not_applicable"


def test_lifecycle_receipt_migration_is_append_only_and_actor_scoped() -> None:
    source = (
        ROOT / "backend" / "alembic" / "versions" / "0030_lifecycle_receipts.py"
    ).read_text(encoding="utf-8")

    assert 'revision = "0030_lifecycle_receipts"' in source
    assert 'down_revision = "0029_webhook_security"' in source
    assert "data_deletion_receipts" in source
    assert "BEFORE UPDATE OR DELETE ON app.data_deletion_receipts" in source
    assert "deletion_job_id" in source
    assert "owner_user_id" in source
    assert "survivor_count" in source
    assert "receipt_hash" in source


def test_lifecycle_receipts_survive_parent_data_deletion() -> None:
    source = (
        ROOT
        / "backend"
        / "alembic"
        / "versions"
        / "0031_lifecycle_receipt_retention.py"
    ).read_text(encoding="utf-8")

    assert 'revision = "0031_lifecycle_receipt_retention"' in source
    assert 'down_revision = "0030_lifecycle_receipts"' in source
    assert "op.drop_constraint(" in source
    assert source.count("fk_data_deletion_receipts_") == 4
    assert "data_deletion_receipts_append_only" not in source
