import asyncio
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Literal

from langgraph_sdk.errors import (
    APIConnectionError,
    APITimeoutError,
    ConflictError,
    NotFoundError,
)

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


@dataclass(frozen=True, slots=True)
class RemoteInterrupt:
    interrupt_id: str
    namespace: str
    checkpoint_id: str
    value: dict[str, Any]


@dataclass(frozen=True, slots=True)
class RemoteCheckpoint:
    thread_id: str
    checkpoint_ns: str
    checkpoint_id: str
    checkpoint_map: dict[str, str]


@dataclass(frozen=True, slots=True)
class RemoteInterruptSet(Sequence[RemoteInterrupt]):
    checkpoint: RemoteCheckpoint
    interrupts: tuple[RemoteInterrupt, ...]

    def __len__(self) -> int:
        return len(self.interrupts)

    def __getitem__(
        self,
        index: int | slice,
    ) -> RemoteInterrupt | tuple[RemoteInterrupt, ...]:
        return self.interrupts[index]


class RemoteResumeIndeterminateError(RuntimeError):
    """A resume create may have succeeded and must only be reconciled."""


class RemoteForkIndeterminateError(RuntimeError):
    """A checkpoint fork may have succeeded and must only be reconciled."""


class AgentServerRunner:
    def __init__(
        self,
        *,
        client: Any,
        assistant_id: str,
        authorization_provider: Callable[[ActorContext], str] | None = None,
        resume_reconciliation_delays: Sequence[float] = (0.05, 0.2, 0.5),
    ) -> None:
        if any(delay < 0 for delay in resume_reconciliation_delays):
            raise ValueError("resume reconciliation delays cannot be negative")
        self._client = client
        self._assistant_id = assistant_id
        self._authorization_provider = authorization_provider
        self._resume_reconciliation_delays = tuple(resume_reconciliation_delays)
        self._indeterminate_resumes: set[tuple[str, str, str, str, str]] = set()
        self._indeterminate_forks: set[tuple[str, str, str, str, str]] = set()
        self._resume_lock = asyncio.Lock()
        self._fork_lock = asyncio.Lock()

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
        review_policy: Literal["bypass", "required"] = "bypass",
    ) -> RemoteRunHandle:
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
            "input": {
                "request": submission.model_dump(mode="json"),
                "review_policy": review_policy,
            },
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

    async def fork(
        self,
        *,
        actor: ActorContext,
        handle: RemoteRunHandle,
        task_id: str,
        product_run_id: str,
        checkpoint_id: str,
    ) -> RemoteRunHandle:
        async with self._fork_lock:
            authorization = handle.authorization or (
                self._authorization_provider(actor)
                if self._authorization_provider is not None
                else None
            )
            fork_key = (
                actor.tenant_id,
                actor.workspace_id,
                actor.user_id,
                handle.thread_id,
                product_run_id,
            )
            existing = await self._find_existing_run(
                actor=actor,
                task_id=task_id,
                product_run_id=product_run_id,
                thread_id=handle.thread_id,
                authorization=authorization,
            )
            if existing is not None:
                self._indeterminate_forks.discard(fork_key)
                return existing
            if fork_key in self._indeterminate_forks:
                existing = await self._reconcile_existing_run(
                    actor=actor,
                    task_id=task_id,
                    product_run_id=product_run_id,
                    thread_id=handle.thread_id,
                    authorization=authorization,
                )
                if existing is not None:
                    self._indeterminate_forks.discard(fork_key)
                    return existing
                raise RemoteForkIndeterminateError(
                    "Agent Server checkpoint fork remains indeterminate; "
                    "refusing a duplicate create"
                )

            await self._validate_fork_checkpoint(
                handle=replace(handle, authorization=authorization),
                checkpoint_id=checkpoint_id,
            )

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
                "task_id": task_id,
                "product_run_id": product_run_id,
                "forked_from_official_run_id": handle.run_id,
                "forked_from_checkpoint_id": checkpoint_id,
            }
            options: dict[str, Any] = {
                "input": None,
                "checkpoint_id": checkpoint_id,
                "durability": "sync",
                "metadata": metadata,
            }
            created_run: dict[str, str] = {}

            def remember_created_run(created: Mapping[str, Any]) -> None:
                run_id = created.get("run_id")
                thread_id = created.get("thread_id")
                if (
                    isinstance(run_id, str)
                    and run_id.strip()
                    and (thread_id is None or thread_id == handle.thread_id)
                ):
                    created_run["run_id"] = run_id.strip()

            options["on_run_created"] = remember_created_run
            if authorization:
                options["headers"] = {"authorization": authorization}
            try:
                run = await self._client.runs.create(
                    handle.thread_id,
                    handle.assistant_id,
                    **options,
                )
            except (APIConnectionError, APITimeoutError) as exc:
                if accepted_run_id := created_run.get("run_id"):
                    return RemoteRunHandle(
                        assistant_id=handle.assistant_id,
                        thread_id=handle.thread_id,
                        run_id=accepted_run_id,
                        authorization=authorization,
                    )
                self._indeterminate_forks.add(fork_key)
                existing = await self._reconcile_existing_run(
                    actor=actor,
                    task_id=task_id,
                    product_run_id=product_run_id,
                    thread_id=handle.thread_id,
                    authorization=authorization,
                )
                if existing is not None:
                    self._indeterminate_forks.discard(fork_key)
                    return existing
                raise RemoteForkIndeterminateError(
                    "Agent Server checkpoint fork is indeterminate after bounded "
                    "reconciliation; refusing a duplicate create"
                ) from exc
            self._indeterminate_forks.discard(fork_key)
            return RemoteRunHandle(
                assistant_id=_required_remote_id(run, "assistant_id"),
                thread_id=handle.thread_id,
                run_id=_required_remote_id(run, "run_id"),
                authorization=authorization,
            )

    async def _validate_fork_checkpoint(
        self,
        *,
        handle: RemoteRunHandle,
        checkpoint_id: str,
    ) -> None:
        state = await self._client.threads.get_state(
            handle.thread_id,
            checkpoint_id=checkpoint_id,
            **_authorization_options(handle),
        )
        if not isinstance(state, dict):
            raise RuntimeError("Agent Server returned an invalid fork checkpoint")
        checkpoint = state.get("checkpoint")
        if not isinstance(checkpoint, dict):
            raise RuntimeError("Agent Server fork checkpoint is missing")
        if (
            _checkpoint_value(checkpoint, "thread_id") != handle.thread_id
            or _checkpoint_value(checkpoint, "checkpoint_id") != checkpoint_id
        ):
            raise RuntimeError("Agent Server returned a different fork checkpoint")
        if _state_checkpoint_run_id(state) != handle.run_id:
            raise RuntimeError(
                "Fork checkpoint does not belong to the selected source Run"
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
        options = {"headers": {"authorization": authorization}} if authorization else {}
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

    async def get_interrupts(
        self,
        handle: RemoteRunHandle,
    ) -> RemoteInterruptSet:
        state = await self._client.threads.get_state(
            handle.thread_id,
            subgraphs=True,
            **_authorization_options(handle),
        )
        if not isinstance(state, dict):
            raise RuntimeError("Agent Server returned an invalid Thread state")
        if _state_checkpoint_run_id(state) != handle.run_id:
            raise RuntimeError("Agent Server current checkpoint belongs to another Run")
        interrupts = _collect_remote_interrupts(
            state,
            expected_thread_id=handle.thread_id,
        )
        if not interrupts:
            raise RuntimeError(
                "Interrupted Agent Server Run has no resumable interrupt"
            )
        return interrupts

    async def resume(
        self,
        *,
        actor: ActorContext,
        handle: RemoteRunHandle,
        task_id: str,
        product_run_id: str,
        responses: Mapping[str, Mapping[str, Any]] | None = None,
        checkpoint: RemoteCheckpoint | None = None,
        response: Mapping[str, Any] | None = None,
        checkpoint_id: str | None = None,
    ) -> RemoteRunHandle:
        async with self._resume_lock:
            return await self._resume_once(
                actor=actor,
                handle=handle,
                task_id=task_id,
                product_run_id=product_run_id,
                responses=responses,
                checkpoint=checkpoint,
                response=response,
                checkpoint_id=checkpoint_id,
            )

    async def _resume_once(
        self,
        *,
        actor: ActorContext,
        handle: RemoteRunHandle,
        task_id: str,
        product_run_id: str,
        responses: Mapping[str, Mapping[str, Any]] | None = None,
        checkpoint: RemoteCheckpoint | None = None,
        response: Mapping[str, Any] | None = None,
        checkpoint_id: str | None = None,
    ) -> RemoteRunHandle:
        authorization = handle.authorization or (
            self._authorization_provider(actor)
            if self._authorization_provider is not None
            else None
        )
        metadata = {
            "tenant_id": actor.tenant_id,
            "workspace_id": actor.workspace_id,
            "user_id": actor.user_id,
            "task_id": task_id,
            "product_run_id": product_run_id,
            "resume_of_official_run_id": handle.run_id,
        }
        resume_key = (
            actor.tenant_id,
            actor.workspace_id,
            actor.user_id,
            handle.thread_id,
            product_run_id,
        )
        existing = await self._find_existing_run(
            actor=actor,
            task_id=task_id,
            product_run_id=product_run_id,
            thread_id=handle.thread_id,
            authorization=authorization,
        )
        if existing is not None:
            self._indeterminate_resumes.discard(resume_key)
            return existing
        if resume_key in self._indeterminate_resumes:
            existing = await self._reconcile_existing_run(
                actor=actor,
                task_id=task_id,
                product_run_id=product_run_id,
                thread_id=handle.thread_id,
                authorization=authorization,
            )
            if existing is not None:
                self._indeterminate_resumes.discard(resume_key)
                return existing
            raise RemoteResumeIndeterminateError(
                "Agent Server resume creation remains indeterminate; "
                "refusing a duplicate create"
            )
        interrupt_set = await self.get_interrupts(
            replace(handle, authorization=authorization)
        )
        resume_mapping = _normalize_resume_mapping(
            interrupt_set=interrupt_set,
            responses=responses,
            checkpoint=checkpoint,
            response=response,
            checkpoint_id=checkpoint_id,
        )
        options: dict[str, Any] = {
            "command": {"resume": resume_mapping},
            "durability": "sync",
            "multitask_strategy": "reject",
            "metadata": metadata,
        }
        created_run: dict[str, str] = {}

        def remember_created_run(created: Mapping[str, Any]) -> None:
            run_id = created.get("run_id")
            thread_id = created.get("thread_id")
            if (
                isinstance(run_id, str)
                and run_id.strip()
                and (thread_id is None or thread_id == handle.thread_id)
            ):
                created_run["run_id"] = run_id.strip()

        options["on_run_created"] = remember_created_run
        if authorization:
            options["headers"] = {"authorization": authorization}
        try:
            run = await self._client.runs.create(
                handle.thread_id,
                handle.assistant_id,
                **options,
            )
        except APITimeoutError as exc:
            if accepted_run_id := created_run.get("run_id"):
                return RemoteRunHandle(
                    assistant_id=handle.assistant_id,
                    thread_id=handle.thread_id,
                    run_id=accepted_run_id,
                    authorization=authorization,
                )
            self._indeterminate_resumes.add(resume_key)
            existing = await self._reconcile_existing_run(
                actor=actor,
                task_id=task_id,
                product_run_id=product_run_id,
                thread_id=handle.thread_id,
                authorization=authorization,
            )
            if existing is not None:
                self._indeterminate_resumes.discard(resume_key)
                return existing
            raise RemoteResumeIndeterminateError(
                "Agent Server resume creation is indeterminate after bounded "
                "reconciliation; refusing a duplicate create"
            ) from exc
        self._indeterminate_resumes.discard(resume_key)
        return RemoteRunHandle(
            assistant_id=_required_remote_id(run, "assistant_id"),
            thread_id=handle.thread_id,
            run_id=_required_remote_id(run, "run_id"),
            authorization=authorization,
        )

    async def _reconcile_existing_run(
        self,
        *,
        actor: ActorContext,
        task_id: str,
        product_run_id: str,
        thread_id: str,
        authorization: str | None,
    ) -> RemoteRunHandle | None:
        for delay in self._resume_reconciliation_delays:
            if delay:
                await asyncio.sleep(delay)
            existing = await self._find_existing_run(
                actor=actor,
                task_id=task_id,
                product_run_id=product_run_id,
                thread_id=thread_id,
                authorization=authorization,
            )
            if existing is not None:
                return existing
        return None

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
        if status == "success":
            thread_state = await self._client.threads.get_state(
                handle.thread_id,
                subgraphs=True,
                **_authorization_options(handle),
            )
            if not isinstance(thread_state, dict):
                raise RuntimeError("Agent Server returned an invalid Thread state")
            if _state_checkpoint_run_id(thread_state) == handle.run_id and len(
                _collect_remote_interrupts(
                    thread_state,
                    expected_thread_id=handle.thread_id,
                )
            ):
                return RemoteRunState(status="interrupted")
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


def _collect_remote_interrupts(
    state: dict[str, Any],
    *,
    expected_thread_id: str,
) -> RemoteInterruptSet:
    root_checkpoint = _parse_remote_checkpoint(state.get("checkpoint"))
    if root_checkpoint.thread_id != expected_thread_id:
        raise RuntimeError("Agent Server Thread state belongs to another thread")
    if root_checkpoint.checkpoint_ns:
        raise RuntimeError("Agent Server root checkpoint has a nested namespace")
    collected: dict[str, RemoteInterrupt] = {}
    priorities: dict[str, int] = {}
    checkpoint_map = {"": root_checkpoint.checkpoint_id}

    def merge_checkpoint(
        checkpoint: RemoteCheckpoint,
        *,
        parent_namespace: str | None,
    ) -> None:
        if checkpoint.thread_id != root_checkpoint.thread_id:
            raise RuntimeError(
                "Agent Server interrupt checkpoint belongs to another thread"
            )
        namespace = checkpoint.checkpoint_ns
        if parent_namespace is None:
            if namespace:
                raise RuntimeError(
                    "Agent Server root checkpoint has a nested namespace"
                )
        elif not _is_descendant_namespace(namespace, parent_namespace):
            raise RuntimeError(
                "Agent Server child checkpoint is outside its parent namespace"
            )

        advertised = checkpoint.checkpoint_map
        if advertised:
            if advertised.get(namespace) != checkpoint.checkpoint_id:
                raise RuntimeError(
                    "Agent Server checkpoint_map omits its own checkpoint"
                )
            if advertised.get("") != root_checkpoint.checkpoint_id:
                raise RuntimeError(
                    "Agent Server checkpoint_map belongs to another root"
                )
            for mapped_namespace, mapped_checkpoint_id in advertised.items():
                if not _is_ancestor_namespace(mapped_namespace, namespace):
                    raise RuntimeError(
                        "Agent Server checkpoint_map contains unrelated lineage"
                    )
                current = checkpoint_map.get(mapped_namespace)
                if current is not None and current != mapped_checkpoint_id:
                    raise RuntimeError(
                        "Agent Server returned conflicting checkpoint lineage"
                    )
                checkpoint_map[mapped_namespace] = mapped_checkpoint_id

        current = checkpoint_map.get(namespace)
        if current is not None and current != checkpoint.checkpoint_id:
            raise RuntimeError("Agent Server returned conflicting checkpoint lineage")
        checkpoint_map[namespace] = checkpoint.checkpoint_id

    def register(
        payload: object,
        *,
        checkpoint: RemoteCheckpoint,
        priority: int,
    ) -> None:
        parsed = _parse_remote_interrupt(payload, checkpoint=checkpoint)
        existing = collected.get(parsed.interrupt_id)
        if existing is None:
            collected[parsed.interrupt_id] = parsed
            priorities[parsed.interrupt_id] = priority
            return
        if existing.value != parsed.value:
            raise RuntimeError("Agent Server reused an interrupt id with another value")
        existing_coordinates = (existing.namespace, existing.checkpoint_id)
        parsed_coordinates = (parsed.namespace, parsed.checkpoint_id)
        existing_priority = priorities[parsed.interrupt_id]
        if priority == existing_priority and parsed_coordinates != existing_coordinates:
            raise RuntimeError(
                "Agent Server returned conflicting interrupt checkpoints"
            )
        if priority > existing_priority:
            collected[parsed.interrupt_id] = parsed
            priorities[parsed.interrupt_id] = priority

    def visit(
        snapshot: dict[str, Any],
        *,
        depth: int,
        parent_namespace: str | None,
    ) -> None:
        snapshot_checkpoint = _parse_remote_checkpoint(snapshot.get("checkpoint"))
        merge_checkpoint(snapshot_checkpoint, parent_namespace=parent_namespace)
        pending_names = _pending_node_names(snapshot)
        tasks = snapshot.get("tasks") or ()
        if not isinstance(tasks, Sequence) or isinstance(tasks, (str, bytes)):
            raise RuntimeError("Agent Server Thread state returned invalid tasks")
        for task in tasks:
            if not isinstance(task, dict):
                raise RuntimeError("Agent Server Thread state returned an invalid task")
            task_name = task.get("name")
            if not isinstance(task_name, str) or not task_name.strip():
                raise RuntimeError("Agent Server Thread task omitted name")
            if task_name not in pending_names:
                continue
            if task.get("result") is not None:
                raise RuntimeError(
                    "Agent Server marked a completed task as still pending"
                )

            task_state = task.get("state")
            state_checkpoint: RemoteCheckpoint | None = None
            if isinstance(task_state, dict):
                state_checkpoint = _parse_remote_checkpoint(
                    task_state.get("checkpoint")
                )
                merge_checkpoint(
                    state_checkpoint,
                    parent_namespace=snapshot_checkpoint.checkpoint_ns,
                )
            task_checkpoint_payload = task.get("checkpoint")
            if isinstance(task_checkpoint_payload, dict):
                task_checkpoint = _parse_remote_checkpoint(task_checkpoint_payload)
                merge_checkpoint(
                    task_checkpoint,
                    parent_namespace=snapshot_checkpoint.checkpoint_ns,
                )
                if state_checkpoint is not None and task_checkpoint != state_checkpoint:
                    raise RuntimeError(
                        "Agent Server task checkpoint conflicts with nested state"
                    )
            elif task_checkpoint_payload is not None:
                raise RuntimeError(
                    "Agent Server Thread task returned an invalid checkpoint"
                )
            elif state_checkpoint is not None:
                task_checkpoint = state_checkpoint
            else:
                task_checkpoint = snapshot_checkpoint
            task_priority = depth * 2 + (task_checkpoint is not snapshot_checkpoint)
            task_interrupts = task.get("interrupts") or ()
            if not isinstance(task_interrupts, Sequence) or isinstance(
                task_interrupts, (str, bytes)
            ):
                raise RuntimeError(
                    "Agent Server Thread task returned invalid interrupts"
                )
            for item in task_interrupts:
                register(
                    item,
                    checkpoint=task_checkpoint,
                    priority=task_priority,
                )
            if isinstance(task_state, dict):
                visit(
                    task_state,
                    depth=depth + 1,
                    parent_namespace=snapshot_checkpoint.checkpoint_ns,
                )
            elif task_state is not None:
                raise RuntimeError("Agent Server Thread task returned invalid state")

    visit(state, depth=0, parent_namespace=None)
    return RemoteInterruptSet(
        checkpoint=replace(root_checkpoint, checkpoint_map=checkpoint_map),
        interrupts=tuple(collected.values()),
    )


def _pending_node_names(snapshot: dict[str, Any]) -> set[str]:
    pending = snapshot.get("next")
    if not isinstance(pending, Sequence) or isinstance(pending, (str, bytes)):
        raise RuntimeError("Agent Server Thread state returned invalid next nodes")
    normalized: set[str] = set()
    for node_name in pending:
        if not isinstance(node_name, str) or not node_name.strip():
            raise RuntimeError(
                "Agent Server Thread state returned an invalid next node"
            )
        normalized.add(node_name)
    return normalized


def _is_descendant_namespace(namespace: str, parent_namespace: str) -> bool:
    if not namespace:
        return False
    if not parent_namespace:
        return True
    return namespace.startswith(f"{parent_namespace}|")


def _is_ancestor_namespace(namespace: str, descendant_namespace: str) -> bool:
    return namespace == descendant_namespace or (
        not namespace or descendant_namespace.startswith(f"{namespace}|")
    )


def _state_checkpoint_run_id(snapshot: dict[str, Any]) -> str | None:
    metadata = snapshot.get("metadata")
    run_id = metadata.get("run_id") if isinstance(metadata, dict) else None
    return run_id.strip() if isinstance(run_id, str) and run_id.strip() else None


def _checkpoint_value(
    checkpoint: object,
    field_name: str,
    *,
    allow_empty: bool = False,
) -> str:
    value = checkpoint.get(field_name) if isinstance(checkpoint, dict) else None
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise RuntimeError(f"Agent Server Thread state omitted {field_name}")
    return value


def _parse_remote_checkpoint(payload: object) -> RemoteCheckpoint:
    checkpoint_map = (
        payload.get("checkpoint_map", {}) if isinstance(payload, dict) else None
    )
    if checkpoint_map is None:
        checkpoint_map = {}
    if not isinstance(checkpoint_map, dict):
        raise RuntimeError(
            "Agent Server Thread state returned an invalid checkpoint_map"
        )
    normalized_map: dict[str, str] = {}
    for namespace, checkpoint_id in checkpoint_map.items():
        if not isinstance(namespace, str):
            raise RuntimeError(
                "Agent Server checkpoint_map contains an invalid namespace"
            )
        if not isinstance(checkpoint_id, str) or not checkpoint_id.strip():
            raise RuntimeError(
                "Agent Server checkpoint_map contains an invalid checkpoint id"
            )
        normalized_map[namespace] = checkpoint_id.strip()
    return RemoteCheckpoint(
        thread_id=_checkpoint_value(payload, "thread_id"),
        checkpoint_ns=_checkpoint_value(payload, "checkpoint_ns", allow_empty=True),
        checkpoint_id=_checkpoint_value(payload, "checkpoint_id"),
        checkpoint_map=normalized_map,
    )


def _parse_remote_interrupt(
    payload: object,
    *,
    checkpoint: RemoteCheckpoint,
) -> RemoteInterrupt:
    if not isinstance(payload, dict):
        raise RuntimeError("Agent Server returned an invalid interrupt")
    interrupt_id = payload.get("id")
    value = payload.get("value")
    if not isinstance(interrupt_id, str) or not interrupt_id.strip():
        raise RuntimeError("Agent Server interrupt omitted id")
    if not isinstance(value, dict):
        raise RuntimeError("Agent Server interrupt value must be an object")
    return RemoteInterrupt(
        interrupt_id=interrupt_id.strip(),
        namespace=checkpoint.checkpoint_ns,
        checkpoint_id=checkpoint.checkpoint_id,
        value=value,
    )


def _normalize_resume_mapping(
    *,
    interrupt_set: RemoteInterruptSet,
    responses: Mapping[str, Mapping[str, Any]] | None,
    checkpoint: RemoteCheckpoint | None,
    response: Mapping[str, Any] | None,
    checkpoint_id: str | None,
) -> dict[str, dict[str, Any]]:
    if checkpoint is not None and checkpoint != interrupt_set.checkpoint:
        raise RuntimeError("Agent Server resume checkpoint is no longer current")
    if checkpoint is not None and checkpoint_id is not None:
        raise TypeError("checkpoint and checkpoint_id cannot be combined")
    if responses is not None and response is not None:
        raise TypeError("responses and response cannot be combined")

    aggregate_responses: Mapping[str, Any] | None = responses
    if aggregate_responses is None and response is not None and checkpoint_id is None:
        aggregate_responses = response
    if aggregate_responses is None:
        if response is None or checkpoint_id is None:
            raise TypeError("resume requires aggregate responses and a checkpoint")
        if len(interrupt_set) != 1:
            raise RuntimeError(
                "Legacy single-interrupt resume cannot resume an interrupt set"
            )
        member = interrupt_set[0]
        if checkpoint_id != member.checkpoint_id:
            raise RuntimeError("Legacy resume checkpoint is no longer current")
        aggregate_responses = {member.interrupt_id: response}

    member_ids = {member.interrupt_id for member in interrupt_set}
    normalized: dict[str, dict[str, Any]] = {}
    for interrupt_id, canonical_response in aggregate_responses.items():
        if not isinstance(interrupt_id, str) or not interrupt_id.strip():
            raise TypeError(
                "Agent Server resume mapping contains an invalid interrupt id"
            )
        normalized_interrupt_id = interrupt_id.strip()
        if normalized_interrupt_id not in member_ids:
            raise RuntimeError(
                "Agent Server resume mapping contains an unknown interrupt id"
            )
        if not isinstance(canonical_response, Mapping):
            raise TypeError("Agent Server canonical response must be an object")
        normalized[normalized_interrupt_id] = dict(canonical_response)
    if not normalized:
        raise ValueError("Agent Server resume mapping cannot be empty")
    if set(normalized) != member_ids:
        raise RuntimeError(
            "Agent Server resume mapping must exactly match the current interrupt set"
        )
    return normalized


__all__ = [
    "AgentServerRunner",
    "RemoteCancelOutcome",
    "RemoteCancelResult",
    "RemoteCheckpoint",
    "RemoteInterrupt",
    "RemoteInterruptSet",
    "RemoteResumeIndeterminateError",
    "RemoteRunHandle",
    "RemoteRunResult",
    "RemoteRunState",
    "RemoteRunStatus",
]
