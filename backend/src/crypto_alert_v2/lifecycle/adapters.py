from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from hashlib import sha256
import json
from typing import Any, Literal, Protocol
from uuid import uuid4

from langgraph_sdk.errors import NotFoundError

from crypto_alert_v2.api.request_identity import transport_headers
from crypto_alert_v2.auth.context import ActorContext


LifecycleSystem = Literal[
    "checkpoint",
    "store",
    "object_storage",
    "search",
    "langsmith",
    "langfuse",
    "logs",
    "backups",
]
LifecycleOutcome = Literal[
    "succeeded",
    "not_applicable",
    "pending_external",
    "pending_expiry",
    "failed",
]


def _canonical_hash(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class LifecycleAdapterResult:
    outcome: LifecycleOutcome
    affected_count: int = 0
    survivor_count: int = 0
    reference: dict[str, Any] | None = None
    evidence: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.affected_count < 0 or self.survivor_count < 0:
            raise ValueError("lifecycle adapter counts must be non-negative")


class LifecycleSystemAdapter(Protocol):
    system: LifecycleSystem

    async def delete(self, actor: ActorContext) -> LifecycleAdapterResult: ...

    async def survivor_scan(self, actor: ActorContext) -> LifecycleAdapterResult: ...


class AegraCheckpointAdapter:
    """Delete actor-scoped Threads through the official LangGraph SDK.

    In Aegra, deleting a Thread is the supported ownership boundary for the
    Thread's Runs and checkpoints. The server auth hook adds the actor filter.
    """

    system: LifecycleSystem = "checkpoint"

    def __init__(
        self,
        *,
        client: Any,
        authorization_provider: Callable[[ActorContext], str],
        page_size: int = 100,
    ) -> None:
        if page_size < 1 or page_size > 1000:
            raise ValueError("page_size must be between 1 and 1000")
        self._client = client
        self._authorization_provider = authorization_provider
        self._page_size = page_size

    def _headers(self, actor: ActorContext) -> Mapping[str, str]:
        return transport_headers(
            request_id=f"lifecycle-{uuid4()}",
            authorization=self._authorization_provider(actor),
        )

    async def _thread_ids(self, actor: ActorContext, *, limit: int | None = None) -> list[str]:
        headers = self._headers(actor)
        metadata = {
            "tenant_id": actor.tenant_id,
            "workspace_id": actor.workspace_id,
            "user_id": actor.user_id,
            "identity_issuer": actor.identity_issuer,
            **(
                {"context_id": str(actor.context_id)}
                if actor.context_id is not None
                else {}
            ),
        }
        found: list[str] = []
        offset = 0
        while limit is None or len(found) < limit:
            page_limit = self._page_size
            if limit is not None:
                page_limit = min(page_limit, limit - len(found))
            rows = await self._client.threads.search(
                metadata=metadata,
                limit=page_limit,
                offset=offset,
                headers=headers,
            )
            for row in rows:
                thread_id = row.get("thread_id") if isinstance(row, Mapping) else None
                if isinstance(thread_id, str) and thread_id:
                    found.append(thread_id)
            if len(rows) < page_limit:
                break
            offset += page_limit
        return found

    async def delete(self, actor: ActorContext) -> LifecycleAdapterResult:
        thread_ids = await self._thread_ids(actor)
        headers = self._headers(actor)
        deleted = 0
        for thread_id in thread_ids:
            try:
                await self._client.threads.delete(thread_id, headers=headers)
            except NotFoundError:
                continue
            deleted += 1
        return LifecycleAdapterResult(
            outcome="succeeded",
            affected_count=deleted,
            reference={"deleted_thread_set_sha256": _canonical_hash(sorted(thread_ids))},
            evidence={"official_api": "threads.search/delete", "checkpoint_owner": "thread"},
        )

    async def survivor_scan(self, actor: ActorContext) -> LifecycleAdapterResult:
        survivors = await self._thread_ids(actor, limit=1)
        return LifecycleAdapterResult(
            outcome="succeeded" if not survivors else "failed",
            survivor_count=len(survivors),
            reference={"survivor_set_sha256": _canonical_hash(sorted(survivors))},
            evidence={"official_api": "threads.search", "scan_limit": 1},
        )


class AegraStoreAdapter:
    """Delete the authenticated actor's private Store namespace with the SDK."""

    system: LifecycleSystem = "store"

    def __init__(
        self,
        *,
        client: Any,
        authorization_provider: Callable[[ActorContext], str],
        page_size: int = 100,
    ) -> None:
        if page_size < 1 or page_size > 1000:
            raise ValueError("page_size must be between 1 and 1000")
        self._client = client
        self._authorization_provider = authorization_provider
        self._page_size = page_size

    def _headers(self, actor: ActorContext) -> Mapping[str, str]:
        return transport_headers(
            request_id=f"lifecycle-{uuid4()}",
            authorization=self._authorization_provider(actor),
        )

    async def _namespaces(self, actor: ActorContext) -> list[list[str]]:
        headers = self._headers(actor)
        namespaces: list[list[str]] = []
        offset = 0
        while True:
            response = await self._client.store.list_namespaces(
                prefix=[],
                limit=self._page_size,
                offset=offset,
                headers=headers,
            )
            page = response.get("namespaces", []) if isinstance(response, Mapping) else []
            namespaces.extend(
                list(namespace)
                for namespace in page
                if isinstance(namespace, Sequence) and not isinstance(namespace, (str, bytes))
            )
            if len(page) < self._page_size:
                break
            offset += self._page_size
        return namespaces

    async def _items(self, actor: ActorContext, namespace: list[str]) -> list[tuple[list[str], str]]:
        headers = self._headers(actor)
        items: list[tuple[list[str], str]] = []
        offset = 0
        while True:
            response = await self._client.store.search_items(
                namespace,
                limit=self._page_size,
                offset=offset,
                headers=headers,
            )
            page = response.get("items", []) if isinstance(response, Mapping) else []
            for item in page:
                if not isinstance(item, Mapping):
                    continue
                key = item.get("key")
                raw_namespace = item.get("namespace")
                if (
                    isinstance(key, str)
                    and key
                    and isinstance(raw_namespace, Sequence)
                    and not isinstance(raw_namespace, (str, bytes))
                ):
                    items.append((list(raw_namespace), key))
            if len(page) < self._page_size:
                break
            offset += self._page_size
        return items

    async def _all_items(self, actor: ActorContext, *, limit: int | None = None) -> list[tuple[list[str], str]]:
        found: list[tuple[list[str], str]] = []
        for namespace in await self._namespaces(actor):
            found.extend(await self._items(actor, namespace))
            if limit is not None and len(found) >= limit:
                return found[:limit]
        return found

    async def delete(self, actor: ActorContext) -> LifecycleAdapterResult:
        items = await self._all_items(actor)
        headers = self._headers(actor)
        for namespace, key in items:
            await self._client.store.delete_item(namespace, key, headers=headers)
        identities = sorted((namespace, key) for namespace, key in items)
        return LifecycleAdapterResult(
            outcome="succeeded",
            affected_count=len(items),
            reference={"deleted_item_set_sha256": _canonical_hash(identities)},
            evidence={"official_api": "store.list/search/delete_item"},
        )

    async def survivor_scan(self, actor: ActorContext) -> LifecycleAdapterResult:
        survivors = await self._all_items(actor, limit=1)
        return LifecycleAdapterResult(
            outcome="succeeded" if not survivors else "failed",
            survivor_count=len(survivors),
            reference={"survivor_set_sha256": _canonical_hash(survivors)},
            evidence={"official_api": "store.list/search", "scan_limit": 1},
        )


class NotConfiguredLifecycleAdapter:
    """Truthful receipt for a data system that is not enabled in this deployment."""

    def __init__(self, system: LifecycleSystem, *, reason: str) -> None:
        if system in {"checkpoint", "store", "logs", "backups"}:
            raise ValueError(f"{system} requires a concrete lifecycle adapter")
        if not reason.strip():
            raise ValueError("reason is required")
        self.system = system
        self._reason = reason.strip()

    async def delete(self, actor: ActorContext) -> LifecycleAdapterResult:
        del actor
        return LifecycleAdapterResult(
            outcome="not_applicable",
            evidence={"inventory": "not_configured", "reason": self._reason},
        )

    async def survivor_scan(self, actor: ActorContext) -> LifecycleAdapterResult:
        del actor
        return LifecycleAdapterResult(
            outcome="not_applicable",
            evidence={"inventory": "not_configured", "reason": self._reason},
        )


__all__ = [
    "AegraCheckpointAdapter",
    "AegraStoreAdapter",
    "LifecycleAdapterResult",
    "LifecycleSystemAdapter",
    "NotConfiguredLifecycleAdapter",
]
