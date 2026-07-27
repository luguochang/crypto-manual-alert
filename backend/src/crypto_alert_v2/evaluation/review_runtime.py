"""Small adapter over the official LangGraph SDK for candidate review interrupts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from langgraph_sdk import get_client

from crypto_alert_v2.api.agent_server import (
    AgentServerRunner,
    RemoteCheckpoint,
    RemoteInterrupt,
    RemoteRunHandle,
    _portable_run_metadata,
    _run_lineage_context,
)
from crypto_alert_v2.api.request_identity import (
    execution_metadata,
    new_request_id,
    transport_headers,
)
from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.auth.worker_authorization import (
    create_agent_server_authorization_provider,
)
from crypto_alert_v2.config import Settings


@dataclass(frozen=True, slots=True)
class CandidateReviewReceipt:
    handle: RemoteRunHandle
    interrupt: RemoteInterrupt
    checkpoint: RemoteCheckpoint


class CandidateReviewRuntime:
    def __init__(
        self,
        *,
        client: Any,
        authorization_provider: Any = None,
    ) -> None:
        self._client = client
        self._authorization_provider = authorization_provider
        self._runner = AgentServerRunner(
            client=client,
            assistant_id="candidate_review",
            authorization_provider=authorization_provider,
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> "CandidateReviewRuntime":
        return cls(
            client=get_client(url=settings.agent_server_url),
            authorization_provider=create_agent_server_authorization_provider(settings),
        )

    async def start(
        self,
        *,
        actor: ActorContext,
        review_id: str,
        candidate_id: str,
        candidate_version: str,
        rationale: str,
    ) -> CandidateReviewReceipt:
        request_id = new_request_id()
        authorization = (
            self._authorization_provider(actor)
            if self._authorization_provider is not None
            else None
        )
        metadata = {
            "tenant_id": actor.tenant_id,
            "workspace_id": actor.workspace_id,
            "user_id": actor.user_id,
            "identity_issuer": actor.identity_issuer,
            "review_id": review_id,
            "task_id": review_id,
            "product_run_id": review_id,
            **execution_metadata(
                task_id=review_id,
                request_id=request_id,
                operation="candidate_review",
                product_run_id=review_id,
            ),
        }
        headers = transport_headers(
            request_id=request_id,
            authorization=authorization,
        )
        thread = await self._client.threads.create(
            thread_id=review_id,
            if_exists="do_nothing",
            graph_id="candidate_review",
            metadata=metadata,
            headers=headers,
        )
        thread_id = str(thread["thread_id"])
        runs = await self._client.runs.list(
            thread_id,
            limit=100,
            offset=0,
            headers=headers,
        )
        existing = next(
            (
                item
                for item in runs
                if isinstance(item, Mapping)
                and isinstance(item.get("metadata"), Mapping)
                and item["metadata"].get("review_id") == review_id
            ),
            None,
        )
        if existing is None:
            run_request_id = new_request_id()
            run_metadata = {
                **metadata,
                "thread_id": thread_id,
                **execution_metadata(
                    task_id=review_id,
                    request_id=run_request_id,
                    operation="candidate_review",
                    product_run_id=review_id,
                ),
            }
            run = await self._client.runs.create(
                thread_id,
                "candidate_review",
                input={
                    "candidate_id": candidate_id,
                    "candidate_version": candidate_version,
                    "rationale": rationale,
                },
                durability="sync",
                stream_mode=["values", "updates", "custom"],
                stream_resumable=True,
                if_not_exists="reject",
                multitask_strategy="reject",
                metadata=_portable_run_metadata(run_metadata),
                context=_run_lineage_context(run_metadata),
                headers=transport_headers(
                    request_id=run_request_id,
                    authorization=authorization,
                ),
            )
        else:
            run = existing
        handle = RemoteRunHandle(
            assistant_id=str(run.get("assistant_id") or "candidate_review"),
            thread_id=thread_id,
            run_id=str(run["run_id"]),
            authorization=authorization,
        )
        await self._client.runs.join(
            handle.thread_id,
            handle.run_id,
            headers=headers,
        )
        interrupt_set = await self._runner.get_interrupts(handle)
        if len(interrupt_set.interrupts) != 1:
            raise RuntimeError("candidate review must expose exactly one interrupt")
        return CandidateReviewReceipt(
            handle=handle,
            interrupt=interrupt_set.interrupts[0],
            checkpoint=interrupt_set.checkpoint,
        )

    async def decide(
        self,
        *,
        actor: ActorContext,
        review_id: str,
        receipt: CandidateReviewReceipt,
        action: str,
        comment: str | None,
    ) -> dict[str, Any]:
        if action not in {"approve", "reject"}:
            raise ValueError("candidate review action must approve or reject")
        response: dict[str, Any] = {"action": action}
        if comment is not None:
            response["comment"] = comment
        resumed = await self._runner.resume(
            actor=actor,
            handle=receipt.handle,
            task_id=review_id,
            product_run_id=f"{review_id}:resume",
            responses={receipt.interrupt.interrupt_id: response},
            checkpoint=receipt.checkpoint,
        )
        return await self._runner.join(resumed)


__all__ = ["CandidateReviewReceipt", "CandidateReviewRuntime"]
