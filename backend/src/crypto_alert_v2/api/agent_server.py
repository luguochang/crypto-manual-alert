from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any

from crypto_alert_v2.api.schemas import AnalysisSubmission
from crypto_alert_v2.auth.context import ActorContext


@dataclass(frozen=True, slots=True)
class RemoteRunResult:
    thread_id: str
    run_id: str
    output: dict[str, Any]


@dataclass(frozen=True, slots=True)
class RemoteRunHandle:
    assistant_id: str
    thread_id: str
    run_id: str
    authorization: str | None = field(default=None, repr=False, compare=False)


class AgentServerRunner:
    def __init__(
        self,
        *,
        client: Any,
        assistant_id: str,
        authorization_provider: Callable[[ActorContext], str] | None = None,
    ) -> None:
        self._client = client
        self._assistant_id = assistant_id
        self._authorization_provider = authorization_provider

    async def run(
        self,
        *,
        actor: ActorContext,
        task_id: str,
        submission: AnalysisSubmission,
    ) -> RemoteRunResult:
        handle = await self.start(
            actor=actor,
            task_id=task_id,
            product_thread_id=None,
            product_run_id=task_id,
            submission=submission,
        )
        output = await self.join(handle)
        return RemoteRunResult(
            thread_id=handle.thread_id,
            run_id=handle.run_id,
            output=output,
        )

    async def start(
        self,
        *,
        actor: ActorContext,
        task_id: str,
        product_thread_id: str | None,
        product_run_id: str,
        submission: AnalysisSubmission,
    ) -> RemoteRunHandle:
        metadata = {
            "tenant_id": actor.tenant_id,
            "workspace_id": actor.workspace_id,
            "user_id": actor.user_id,
            "task_id": task_id,
            "product_run_id": product_run_id,
        }
        thread_options: dict[str, Any] = {
            "metadata": metadata,
            "graph_id": self._assistant_id,
        }
        authorization = (
            self._authorization_provider(actor)
            if self._authorization_provider is not None
            else None
        )
        headers = {"authorization": authorization} if authorization else None
        if headers is not None:
            thread_options["headers"] = headers
        if product_thread_id is not None:
            thread_options.update(
                thread_id=product_thread_id,
                if_exists="do_nothing",
            )
        thread = await self._client.threads.create(**thread_options)
        thread_id = str(thread["thread_id"])
        if product_thread_id is not None:
            list_options = {"headers": headers} if headers is not None else {}
            existing_runs = await self._client.runs.list(
                thread_id,
                limit=100,
                **list_options,
            )
            for existing in existing_runs:
                existing_metadata = existing.get("metadata") or {}
                if (
                    existing_metadata.get("tenant_id") == actor.tenant_id
                    and existing_metadata.get("workspace_id") == actor.workspace_id
                    and existing_metadata.get("user_id") == actor.user_id
                    and existing_metadata.get("task_id") == task_id
                    and existing_metadata.get("product_run_id") == product_run_id
                ):
                    return RemoteRunHandle(
                        assistant_id=_required_remote_id(
                            existing, "assistant_id"
                        ),
                        thread_id=thread_id,
                        run_id=str(existing["run_id"]),
                        authorization=authorization,
                    )
        run_options: dict[str, Any] = {
            "input": {"request": submission.model_dump(mode="json")},
            "durability": "sync",
            "metadata": metadata,
        }
        if headers is not None:
            run_options["headers"] = headers
        run = await self._client.runs.create(
            thread_id,
            self._assistant_id,
            **run_options,
        )
        run_id = str(run["run_id"])
        return RemoteRunHandle(
            assistant_id=_required_remote_id(run, "assistant_id"),
            thread_id=thread_id,
            run_id=run_id,
            authorization=authorization,
        )

    async def join(self, handle: RemoteRunHandle) -> dict[str, Any]:
        options = (
            {"headers": {"authorization": handle.authorization}}
            if handle.authorization
            else {}
        )
        return await self._client.runs.join(handle.thread_id, handle.run_id, **options)

    async def cancel(self, handle: RemoteRunHandle) -> None:
        options = (
            {"headers": {"authorization": handle.authorization}}
            if handle.authorization
            else {}
        )
        await self._client.runs.cancel(handle.thread_id, handle.run_id, **options)

    def authorize(
        self,
        handle: RemoteRunHandle,
        actor: ActorContext,
    ) -> RemoteRunHandle:
        if handle.authorization or self._authorization_provider is None:
            return handle
        return replace(handle, authorization=self._authorization_provider(actor))


def _required_remote_id(payload: dict[str, Any], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"Agent Server response omitted {field_name}")
    return value.strip()


__all__ = ["AgentServerRunner", "RemoteRunHandle", "RemoteRunResult"]
