from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any, Literal

from langgraph_sdk.errors import ConflictError, NotFoundError

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


RemoteRunStatus = Literal[
    "pending",
    "running",
    "error",
    "success",
    "timeout",
    "interrupted",
]


@dataclass(frozen=True, slots=True)
class RemoteRunState:
    status: RemoteRunStatus


RemoteCancelOutcome = Literal["confirmed", "terminal", "unconfirmed"]


@dataclass(frozen=True, slots=True)
class RemoteCancelResult:
    outcome: RemoteCancelOutcome
    state: RemoteRunState | None = None


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
            existing = await self._find_existing_run(
                actor=actor,
                task_id=task_id,
                product_run_id=product_run_id,
                thread_id=thread_id,
                authorization=authorization,
            )
            if existing is not None:
                return existing
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

    async def find(
        self,
        *,
        actor: ActorContext,
        task_id: str,
        product_thread_id: str,
        product_run_id: str,
    ) -> RemoteRunHandle | None:
        authorization = (
            self._authorization_provider(actor)
            if self._authorization_provider is not None
            else None
        )
        try:
            return await self._find_existing_run(
                actor=actor,
                task_id=task_id,
                product_run_id=product_run_id,
                thread_id=product_thread_id,
                authorization=authorization,
            )
        except NotFoundError:
            return None

    async def _find_existing_run(
        self,
        *,
        actor: ActorContext,
        task_id: str,
        product_run_id: str,
        thread_id: str,
        authorization: str | None,
    ) -> RemoteRunHandle | None:
        options = (
            {"headers": {"authorization": authorization}}
            if authorization
            else {}
        )
        matches: list[RemoteRunHandle] = []
        page_size = 100
        max_pages = 100
        for page in range(max_pages):
            existing_runs = await self._client.runs.list(
                thread_id,
                limit=page_size,
                offset=page * page_size,
                **options,
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
                    matches.append(
                        RemoteRunHandle(
                            assistant_id=_required_remote_id(existing, "assistant_id"),
                            thread_id=thread_id,
                            run_id=_required_remote_id(existing, "run_id"),
                            authorization=authorization,
                        )
                    )
            if len(existing_runs) < page_size:
                break
        else:
            raise RuntimeError("Agent Server Run discovery exceeded its scan limit")

        if len(matches) > 1:
            raise RuntimeError("Multiple Agent Server Runs share one product_run_id")
        return matches[0] if matches else None

    async def join(self, handle: RemoteRunHandle) -> dict[str, Any]:
        return await self._client.runs.join(
            handle.thread_id,
            handle.run_id,
            **_authorization_options(handle),
        )

    async def get(self, handle: RemoteRunHandle) -> RemoteRunState:
        run = await self._client.runs.get(
            handle.thread_id,
            handle.run_id,
            **_authorization_options(handle),
        )
        status = run.get("status") if isinstance(run, dict) else None
        if status not in {
            "pending",
            "running",
            "error",
            "success",
            "timeout",
            "interrupted",
        }:
            raise RuntimeError("Agent Server returned an unknown status")
        return RemoteRunState(status=status)

    async def cancel(self, handle: RemoteRunHandle) -> RemoteCancelResult:
        try:
            await self._client.runs.cancel(
                handle.thread_id,
                handle.run_id,
                wait=True,
                action="interrupt",
                **_authorization_options(handle),
            )
        except NotFoundError:
            return RemoteCancelResult(outcome="unconfirmed")
        except ConflictError:
            pass

        try:
            state = await self.get(handle)
        except NotFoundError:
            return RemoteCancelResult(outcome="unconfirmed")
        if state.status in {"pending", "running"}:
            return RemoteCancelResult(outcome="unconfirmed", state=state)
        if state.status == "interrupted":
            return RemoteCancelResult(outcome="confirmed", state=state)
        return RemoteCancelResult(outcome="terminal", state=state)

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


def _authorization_options(handle: RemoteRunHandle) -> dict[str, Any]:
    return (
        {"headers": {"authorization": handle.authorization}}
        if handle.authorization
        else {}
    )


__all__ = [
    "AgentServerRunner",
    "RemoteCancelOutcome",
    "RemoteCancelResult",
    "RemoteRunHandle",
    "RemoteRunResult",
    "RemoteRunState",
    "RemoteRunStatus",
]
