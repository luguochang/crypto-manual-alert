from __future__ import annotations

import argparse
import asyncio
from collections.abc import Mapping
import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from langgraph_sdk import get_client
from langgraph_sdk.errors import APIStatusError

from crypto_alert_v2.api.agent_server import AgentServerRunner, RemoteRunHandle
from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.auth.internal_token import InternalTokenIssuer
from crypto_alert_v2.commands.seed_hitl_e2e import GRAPH_STATE


TERMINAL_FAILURES = frozenset({"error", "timeout", "interrupted"})


def _required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def _issuer() -> InternalTokenIssuer:
    key_file = Path(_required_environment("AEGRA_PROBE_PRIVATE_KEY_FILE"))
    if key_file.name == ".env" or not key_file.is_file():
        raise RuntimeError("AEGRA_PROBE_PRIVATE_KEY_FILE must be a key file, not .env")
    return InternalTokenIssuer(
        private_key=key_file.read_text(encoding="utf-8"),
        key_id=_required_environment("AEGRA_PROBE_JWT_KID"),
        issuer=_required_environment("AEGRA_PROBE_JWT_ISSUER"),
        audience=_required_environment("AEGRA_PROBE_JWT_AUDIENCE"),
        ttl_seconds=60,
    )


def _authorization(
    issuer: InternalTokenIssuer,
    *,
    subject: str | None = None,
    tenant_id: str | None = None,
    workspace_id: str | None = None,
) -> str:
    token = issuer.issue(
        subject=subject or _required_environment("AEGRA_PROBE_USER_ID"),
        tenant_id=tenant_id or _required_environment("AEGRA_PROBE_TENANT_ID"),
        workspace_id=workspace_id
        or _required_environment("AEGRA_PROBE_WORKSPACE_ID"),
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
        token_use="worker",
        identity_issuer=_required_environment("AEGRA_PROBE_IDENTITY_ISSUER"),
    )
    return f"Bearer {token}"


def _headers(issuer: InternalTokenIssuer) -> dict[str, str]:
    return {"authorization": _authorization(issuer)}


def _user_authorization(
    issuer: InternalTokenIssuer,
    *,
    subject: str,
    context_id: str,
) -> str:
    token = issuer.issue_scoped(
        issuer=_required_environment("AEGRA_PROBE_IDENTITY_ISSUER"),
        subject=subject,
        context_id=context_id,
    )
    return f"Bearer {token}"


async def _thread_read_status(
    client: Any,
    thread_id: str,
    authorization: str,
) -> int:
    try:
        await client.threads.get(
            thread_id,
            headers={"authorization": authorization},
        )
    except APIStatusError as exc:
        return exc.status_code
    return 200


def _required_string(payload: Mapping[str, Any], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value:
        raise AssertionError(f"proof payload omitted {name}")
    return value


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _actor() -> ActorContext:
    return ActorContext(
        tenant_id=_required_environment("AEGRA_PROBE_TENANT_ID"),
        workspace_id=_required_environment("AEGRA_PROBE_WORKSPACE_ID"),
        user_id=_required_environment("AEGRA_PROBE_USER_ID"),
        identity_issuer=_required_environment("AEGRA_PROBE_IDENTITY_ISSUER"),
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )


async def _assistant_id(
    client: Any,
    issuer: InternalTokenIssuer,
    graph_id: str,
) -> str:
    assistants = await client.assistants.search(
        graph_id=graph_id,
        limit=10,
        headers=_headers(issuer),
    )
    assistant = next(
        (
            item
            for item in assistants
            if isinstance(item, dict) and item.get("graph_id") == graph_id
        ),
        None,
    )
    if assistant is None:
        raise AssertionError(f"Aegra did not register {graph_id}")
    return _required_string(assistant, "assistant_id")


async def _wait_for_runner_status(
    runner: AgentServerRunner,
    handle: RemoteRunHandle,
    expected: frozenset[str],
    *,
    timeout_seconds: float = 30,
) -> str:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    last = "missing"
    while loop.time() < deadline:
        state = await runner.get(handle)
        last = state.status
        if last in expected:
            return last
        if last in TERMINAL_FAILURES or last == "success":
            raise AssertionError(f"Run reached unexpected status {last!r}")
        await asyncio.sleep(0.2)
    raise AssertionError(f"Run did not reach {sorted(expected)} (last={last})")


async def _matrix() -> None:
    issuer = _issuer()
    client = get_client(
        url=_required_environment("AEGRA_PROBE_URL"),
        timeout=httpx.Timeout(30.0),
    )
    actor = _actor()
    authorization = _authorization(issuer)
    durability_assistant = await _assistant_id(
        client,
        issuer,
        "aegra_durability_fixture",
    )
    interrupt_assistant = await _assistant_id(
        client,
        issuer,
        "single_interrupt_fixture",
    )
    owned_threads: list[str] = []
    result: dict[str, Any] = {
        "schema_version": "1.0",
        "runtime": "aegra-0.9.24",
        "scope": "local-qa-official-sdk-cancel-fork-provisioned-actor-matrix",
    }
    try:
        cancel_thread = await client.threads.create(headers=_headers(issuer))
        cancel_thread_id = _required_string(cancel_thread, "thread_id")
        owned_threads.append(cancel_thread_id)
        cancel_run = await client.runs.create(
            cancel_thread_id,
            durability_assistant,
            input={
                "proof_id": f"cancel-{uuid4()}",
                "sleep_seconds": 5.0,
            },
            stream_mode=["values", "custom"],
            headers=_headers(issuer),
        )
        cancel_run_id = _required_string(cancel_run, "run_id")
        cancel_handle = RemoteRunHandle(
            assistant_id=durability_assistant,
            thread_id=cancel_thread_id,
            run_id=cancel_run_id,
            authorization=authorization,
        )
        cancel_runner = AgentServerRunner(
            client=client,
            assistant_id=durability_assistant,
        )
        await _wait_for_runner_status(
            cancel_runner,
            cancel_handle,
            frozenset({"running"}),
        )
        cancel_result = await cancel_runner.cancel(cancel_handle)
        if cancel_result.outcome != "confirmed" or cancel_result.state is None:
            raise AssertionError(
                f"Aegra cancel was not confirmed: {cancel_result.outcome}"
            )
        await asyncio.sleep(6)
        cancel_state = await client.threads.get_state(
            cancel_thread_id,
            headers=_headers(issuer),
        )
        cancel_values = cancel_state.get("values") or {}
        if not isinstance(cancel_values, dict):
            raise AssertionError("cancel Thread state values are invalid")
        if cancel_values.get("completion_count") not in (None, 0):
            raise AssertionError("cancelled fixture committed its finish node")
        result["cancel"] = {
            "thread_id": cancel_thread_id,
            "run_id": cancel_run_id,
            "outcome": cancel_result.outcome,
            "status": cancel_result.state.status,
            "completion_count": cancel_values.get("completion_count"),
        }

        source_thread = await client.threads.create(headers=_headers(issuer))
        source_thread_id = _required_string(source_thread, "thread_id")
        owned_threads.append(source_thread_id)
        source_run = await client.runs.create(
            source_thread_id,
            interrupt_assistant,
            input={},
            stream_mode=["values", "updates", "custom"],
            headers=_headers(issuer),
        )
        source_run_id = _required_string(source_run, "run_id")
        source_handle = RemoteRunHandle(
            assistant_id=interrupt_assistant,
            thread_id=source_thread_id,
            run_id=source_run_id,
            authorization=authorization,
        )
        fork_runner = AgentServerRunner(
            client=client,
            assistant_id=interrupt_assistant,
        )
        await _wait_for_runner_status(
            fork_runner,
            source_handle,
            frozenset({"interrupted"}),
        )
        interrupt_set = await fork_runner.get_interrupts(source_handle)
        checkpoint_id = interrupt_set.checkpoint.checkpoint_id
        forked = await fork_runner.fork(
            actor=actor,
            handle=source_handle,
            task_id=str(uuid4()),
            product_run_id=str(uuid4()),
            checkpoint_id=checkpoint_id,
        )
        if forked.run_id == source_run_id:
            raise AssertionError("checkpoint fork reused the source Run ID")
        fork_status = await _wait_for_runner_status(
            fork_runner,
            forked,
            frozenset({"interrupted", "success"}),
        )
        runs = await client.runs.list(
            source_thread_id,
            limit=100,
            headers=_headers(issuer),
        )
        fork_record = next(
            (
                item
                for item in runs
                if isinstance(item, dict) and item.get("run_id") == forked.run_id
            ),
            None,
        )
        if fork_record is None:
            raise AssertionError("checkpoint fork Run is absent from official list")
        fork_metadata = fork_record.get("metadata") or {}
        fork_context = fork_record.get("context") or {}
        lineage = (
            fork_context.get("crypto_alert_lineage")
            if isinstance(fork_context, dict)
            else None
        )
        if not isinstance(lineage, dict):
            lineage = fork_metadata
        if not isinstance(lineage, dict):
            raise AssertionError("checkpoint fork lineage is invalid")
        if lineage.get("forked_from_checkpoint_id") != checkpoint_id:
            raise AssertionError("checkpoint fork metadata lost source checkpoint")
        if lineage.get("forked_from_official_run_id") != source_run_id:
            raise AssertionError("checkpoint fork metadata lost source Run")
        result["checkpoint_fork"] = {
            "thread_id": source_thread_id,
            "source_run_id": source_run_id,
            "fork_run_id": forked.run_id,
            "checkpoint_id": checkpoint_id,
            "fork_status": fork_status,
            "source_checkpoint_preserved": True,
            "lineage_source": "context.crypto_alert_lineage"
            if isinstance(fork_context, dict)
            and isinstance(fork_context.get("crypto_alert_lineage"), dict)
            else "metadata",
        }

        owner_authorization = _user_authorization(
            issuer,
            subject=_required_environment("AEGRA_PROBE_USER_ID"),
            context_id=_required_environment("AEGRA_PROBE_CONTEXT_ID"),
        )
        peer_authorization = _user_authorization(
            issuer,
            subject=_required_environment("AEGRA_PROBE_PEER_USER_ID"),
            context_id=_required_environment("AEGRA_PROBE_PEER_CONTEXT_ID"),
        )
        cross_tenant_authorization = _user_authorization(
            issuer,
            subject=_required_environment("AEGRA_PROBE_CROSS_USER_ID"),
            context_id=_required_environment("AEGRA_PROBE_CROSS_CONTEXT_ID"),
        )
        mismatched_context_authorization = _user_authorization(
            issuer,
            subject=_required_environment("AEGRA_PROBE_PEER_USER_ID"),
            context_id=_required_environment("AEGRA_PROBE_CONTEXT_ID"),
        )
        user_thread = await client.threads.create(
            metadata={
                "tenant_id": "client-forged-tenant",
                "workspace_id": "client-forged-workspace",
                "user_id": "client-forged-user",
                "identity_issuer": "client-forged-issuer",
                "context_id": "client-forged-context",
                "probe_kind": "provisioned-actor-matrix",
            },
            headers={"authorization": owner_authorization},
        )
        user_thread_id = _required_string(user_thread, "thread_id")
        try:
            owner_thread = await client.threads.get(
                user_thread_id,
                headers={"authorization": owner_authorization},
            )
            metadata = owner_thread.get("metadata") or {}
            if not isinstance(metadata, dict):
                raise AssertionError("owner Thread metadata is invalid")
            expected_authority = {
                "tenant_id": _required_environment("AEGRA_PROBE_TENANT_ID"),
                "workspace_id": _required_environment("AEGRA_PROBE_WORKSPACE_ID"),
                "user_id": _required_environment("AEGRA_PROBE_USER_ID"),
                "identity_issuer": _required_environment(
                    "AEGRA_PROBE_IDENTITY_ISSUER"
                ),
                "context_id": _required_environment("AEGRA_PROBE_CONTEXT_ID"),
            }
            if any(metadata.get(key) != value for key, value in expected_authority.items()):
                raise AssertionError("Aegra did not overwrite client authority metadata")
            same_tenant_peer_status = await _thread_read_status(
                client,
                user_thread_id,
                peer_authorization,
            )
            cross_tenant_status = await _thread_read_status(
                client,
                user_thread_id,
                cross_tenant_authorization,
            )
            mismatched_context_status = await _thread_read_status(
                client,
                user_thread_id,
                mismatched_context_authorization,
            )
            if same_tenant_peer_status != 404:
                raise AssertionError(
                    "provisioned same-tenant peer was not resource-hidden "
                    f"({same_tenant_peer_status})"
                )
            if cross_tenant_status != 404:
                raise AssertionError(
                    "provisioned cross-tenant actor was not resource-hidden "
                    f"({cross_tenant_status})"
                )
            if mismatched_context_status != 401:
                raise AssertionError(
                    "subject/context mismatch was not rejected by Aegra auth "
                    f"({mismatched_context_status})"
                )
            result["provisioned_actor_matrix"] = {
                "thread_id": user_thread_id,
                "owner_status": 200,
                "same_tenant_peer_status": same_tenant_peer_status,
                "cross_tenant_status": cross_tenant_status,
                "mismatched_context_status": mismatched_context_status,
                "authority_metadata_overwritten": True,
                "auth_forbidden_normalized_to_401": True,
                "membership_bootstrap": True,
                "token_use": "user",
            }
        finally:
            try:
                await client.threads.delete(
                    user_thread_id,
                    headers={"authorization": owner_authorization},
                )
            except Exception:
                pass
    finally:
        for thread_id in reversed(owned_threads):
            try:
                await client.threads.delete(thread_id, headers=_headers(issuer))
            except Exception:
                pass

    _write_json(
        Path(_required_environment("AEGRA_PROBE_MATRIX_FILE")),
        result,
    )


def _canonical_checkpoint_state() -> dict[str, Any]:
    path = Path(_required_environment("AEGRA_CANONICAL_STATE_FILE"))
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != "1.0":
        raise AssertionError("canonical checkpoint receipt is invalid")
    return payload


async def _canonical_prepare() -> None:
    issuer = _issuer()
    client = get_client(
        url=_required_environment("AEGRA_PROBE_URL"),
        timeout=httpx.Timeout(30.0),
    )
    assistant_id = await _assistant_id(client, issuer, "crypto_analysis")
    thread = await client.threads.create(
        graph_id="crypto_analysis",
        headers=_headers(issuer),
    )
    thread_id = _required_string(thread, "thread_id")
    try:
        await client.threads.update_state(
            thread_id,
            GRAPH_STATE,
            as_node="build_artifact",
            headers=_headers(issuer),
        )
        run = await client.runs.create(
            thread_id,
            assistant_id,
            command={"goto": "review_policy"},
            stream_mode=["values", "updates", "custom"],
            headers=_headers(issuer),
        )
        handle = RemoteRunHandle(
            assistant_id=assistant_id,
            thread_id=thread_id,
            run_id=_required_string(run, "run_id"),
            authorization=_authorization(issuer),
        )
        runner = AgentServerRunner(client=client, assistant_id=assistant_id)
        await _wait_for_runner_status(
            runner,
            handle,
            frozenset({"interrupted"}),
            timeout_seconds=60,
        )
        interrupts = await runner.get_interrupts(handle)
        if len(interrupts) != 1:
            raise AssertionError("canonical seeded Graph did not expose one interrupt")
        item = next(iter(interrupts))
        _write_json(
            Path(_required_environment("AEGRA_CANONICAL_STATE_FILE")),
            {
                "schema_version": "1.0",
                "assistant_id": assistant_id,
                "thread_id": thread_id,
                "run_id": handle.run_id,
                "checkpoint_id": interrupts.checkpoint.checkpoint_id,
                "interrupt_id": item.interrupt_id,
                "namespace": list(item.namespace),
                "status_before_restart": "interrupted",
                "seed_boundary": "post-provider-controlled-state",
                "run_command": {"goto": "review_policy"},
            },
        )
    except BaseException:
        try:
            await client.threads.delete(thread_id, headers=_headers(issuer))
        except Exception:
            pass
        raise


async def _canonical_verify() -> None:
    before = _canonical_checkpoint_state()
    issuer = _issuer()
    client = get_client(
        url=_required_environment("AEGRA_PROBE_URL"),
        timeout=httpx.Timeout(30.0),
    )
    handle = RemoteRunHandle(
        assistant_id=_required_string(before, "assistant_id"),
        thread_id=_required_string(before, "thread_id"),
        run_id=_required_string(before, "run_id"),
        authorization=_authorization(issuer),
    )
    runner = AgentServerRunner(client=client, assistant_id=handle.assistant_id)
    try:
        await _wait_for_runner_status(
            runner,
            handle,
            frozenset({"interrupted"}),
            timeout_seconds=60,
        )
        interrupts = await runner.get_interrupts(handle)
        if interrupts.checkpoint.checkpoint_id != _required_string(
            before, "checkpoint_id"
        ):
            raise AssertionError("canonical checkpoint changed across server restart")
        if len(interrupts) != 1:
            raise AssertionError("canonical interrupt count changed across restart")
        item = next(iter(interrupts))
        if item.interrupt_id != _required_string(before, "interrupt_id"):
            raise AssertionError("canonical interrupt identity changed across restart")
        resumed = await runner.resume(
            actor=_actor(),
            handle=handle,
            task_id=str(uuid4()),
            product_run_id=str(uuid4()),
            checkpoint=interrupts.checkpoint,
            responses={item.interrupt_id: {"action": "approve"}},
        )
        await _wait_for_runner_status(
            runner,
            resumed,
            frozenset({"success"}),
            timeout_seconds=60,
        )
        state = await client.threads.get_state(
            resumed.thread_id,
            headers=_headers(issuer),
        )
        values = state.get("values") or {}
        if not isinstance(values, dict):
            raise AssertionError("canonical resumed state values are invalid")
        if values.get("terminal_status") != "succeeded":
            raise AssertionError("canonical Graph did not succeed after restart resume")
        artifact = values.get("artifact") or {}
        if not isinstance(artifact, dict) or artifact.get("status") != "committed":
            raise AssertionError("canonical Graph did not commit its approved artifact")
        _write_json(
            Path(_required_environment("AEGRA_CANONICAL_RESULT_FILE")),
            {
                "schema_version": "1.0",
                "assistant_id": resumed.assistant_id,
                "thread_id": resumed.thread_id,
                "source_run_id": handle.run_id,
                "resume_run_id": resumed.run_id,
                "checkpoint_id": interrupts.checkpoint.checkpoint_id,
                "interrupt_id": item.interrupt_id,
                "checkpoint_preserved": True,
                "interrupt_preserved": True,
                "terminal_status": values.get("terminal_status"),
                "artifact_status": artifact.get("status"),
                "seed_boundary": before.get("seed_boundary"),
            },
        )
    finally:
        try:
            await client.threads.delete(handle.thread_id, headers=_headers(issuer))
        except Exception:
            pass


def _ha_state() -> dict[str, Any]:
    path = Path(_required_environment("AEGRA_HA_STATE_FILE"))
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != "1.0":
        raise AssertionError("Aegra HA state receipt is invalid")
    return payload


def _ha_handle(payload: Mapping[str, Any], issuer: InternalTokenIssuer) -> RemoteRunHandle:
    return RemoteRunHandle(
        assistant_id=_required_string(payload, "assistant_id"),
        thread_id=_required_string(payload, "thread_id"),
        run_id=_required_string(payload, "run_id"),
        authorization=_authorization(issuer),
    )


async def _ha_prepare() -> None:
    issuer = _issuer()
    client = get_client(
        url=_required_environment("AEGRA_PROBE_URL"),
        timeout=httpx.Timeout(30.0),
    )
    assistant_id = await _assistant_id(client, issuer, "single_interrupt_fixture")
    thread = await client.threads.create(headers=_headers(issuer))
    thread_id = _required_string(thread, "thread_id")
    run = await client.runs.create(
        thread_id,
        assistant_id,
        input={},
        stream_mode=["values", "updates", "custom"],
        headers=_headers(issuer),
    )
    handle = RemoteRunHandle(
        assistant_id=assistant_id,
        thread_id=thread_id,
        run_id=_required_string(run, "run_id"),
        authorization=_authorization(issuer),
    )
    runner = AgentServerRunner(client=client, assistant_id=assistant_id)
    await _wait_for_runner_status(runner, handle, frozenset({"interrupted"}))
    interrupts = await runner.get_interrupts(handle)
    _write_json(
        Path(_required_environment("AEGRA_HA_STATE_FILE")),
        {
            "schema_version": "1.0",
            "assistant_id": assistant_id,
            "thread_id": thread_id,
            "run_id": handle.run_id,
            "checkpoint_id": interrupts.checkpoint.checkpoint_id,
            "interrupt_ids": sorted(item.interrupt_id for item in interrupts),
            "status": "interrupted",
            "prepared_via": _required_environment("AEGRA_PROBE_URL"),
        },
    )


async def _ha_observe() -> None:
    before = _ha_state()
    issuer = _issuer()
    client = get_client(
        url=_required_environment("AEGRA_PROBE_URL"),
        timeout=httpx.Timeout(30.0),
    )
    handle = _ha_handle(before, issuer)
    runner = AgentServerRunner(client=client, assistant_id=handle.assistant_id)
    await _wait_for_runner_status(runner, handle, frozenset({"interrupted"}))
    interrupts = await runner.get_interrupts(handle)
    checkpoint_id = interrupts.checkpoint.checkpoint_id
    if checkpoint_id != _required_string(before, "checkpoint_id"):
        raise AssertionError("cross-instance checkpoint identity changed")
    interrupt_ids = sorted(item.interrupt_id for item in interrupts)
    if interrupt_ids != before.get("interrupt_ids"):
        raise AssertionError("cross-instance interrupt identity changed")
    _write_json(
        Path(_required_environment("AEGRA_HA_OBSERVATION_FILE")),
        {
            "schema_version": "1.0",
            "thread_id": handle.thread_id,
            "run_id": handle.run_id,
            "checkpoint_id": checkpoint_id,
            "interrupt_ids": interrupt_ids,
            "status": "interrupted",
            "observed_via": _required_environment("AEGRA_PROBE_URL"),
        },
    )


async def _ha_resume() -> None:
    before = _ha_state()
    issuer = _issuer()
    client = get_client(
        url=_required_environment("AEGRA_PROBE_URL"),
        timeout=httpx.Timeout(30.0),
    )
    actor = _actor()
    handle = _ha_handle(before, issuer)
    runner = AgentServerRunner(client=client, assistant_id=handle.assistant_id)
    interrupts = await runner.get_interrupts(handle)
    resumed = await runner.resume(
        actor=actor,
        handle=handle,
        task_id=str(uuid4()),
        product_run_id=str(uuid4()),
        checkpoint=interrupts.checkpoint,
        responses={
            item.interrupt_id: {"action": "approve"} for item in interrupts
        },
    )
    await _wait_for_runner_status(
        runner,
        resumed,
        frozenset({"success"}),
        timeout_seconds=60,
    )
    state = await client.threads.get_state(
        resumed.thread_id,
        headers=_headers(issuer),
    )
    values = state.get("values") or {}
    if not isinstance(values, dict):
        raise AssertionError("resumed HA Thread values are invalid")
    if values.get("terminal_status") != "succeeded":
        raise AssertionError("resumed HA Thread did not reach succeeded")
    if values.get("completion_count") != 1:
        raise AssertionError("resumed HA Thread did not commit exactly once")
    _write_json(
        Path(_required_environment("AEGRA_HA_RESUME_FILE")),
        {
            "schema_version": "1.0",
            "assistant_id": resumed.assistant_id,
            "thread_id": resumed.thread_id,
            "source_run_id": handle.run_id,
            "resume_run_id": resumed.run_id,
            "checkpoint_id": interrupts.checkpoint.checkpoint_id,
            "terminal_status": values.get("terminal_status"),
            "completion_count": values.get("completion_count"),
            "resumed_via": _required_environment("AEGRA_PROBE_URL"),
        },
    )


async def _ha_final() -> None:
    before = _ha_state()
    resume_path = Path(_required_environment("AEGRA_HA_RESUME_FILE"))
    resumed = json.loads(resume_path.read_text(encoding="utf-8"))
    if not isinstance(resumed, dict) or resumed.get("schema_version") != "1.0":
        raise AssertionError("Aegra HA resume receipt is invalid")
    issuer = _issuer()
    client = get_client(
        url=_required_environment("AEGRA_PROBE_URL"),
        timeout=httpx.Timeout(30.0),
    )
    thread_id = _required_string(before, "thread_id")
    resume_run_id = _required_string(resumed, "resume_run_id")
    current = await client.runs.get(
        thread_id,
        resume_run_id,
        headers=_headers(issuer),
    )
    if current.get("status") != "success":
        raise AssertionError("final cross-instance Run is not successful")
    state = await client.threads.get_state(thread_id, headers=_headers(issuer))
    history = await client.threads.get_history(
        thread_id,
        limit=100,
        headers=_headers(issuer),
    )
    values = state.get("values") or {}
    if not isinstance(values, dict):
        raise AssertionError("final HA Thread values are invalid")
    checkpoint_ids = {
        str((item.get("checkpoint") or {}).get("checkpoint_id"))
        for item in history
        if isinstance(item, dict)
    }
    if _required_string(before, "checkpoint_id") not in checkpoint_ids:
        raise AssertionError("original HA checkpoint disappeared from history")
    if values.get("completion_count") != 1:
        raise AssertionError("final HA Thread completion count changed")
    _write_json(
        Path(_required_environment("AEGRA_HA_FINAL_FILE")),
        {
            "schema_version": "1.0",
            "thread_id": thread_id,
            "source_run_id": _required_string(before, "run_id"),
            "resume_run_id": resume_run_id,
            "status": current.get("status"),
            "terminal_status": values.get("terminal_status"),
            "completion_count": values.get("completion_count"),
            "checkpoint_before_preserved": True,
            "history_count": len(history),
            "observed_via": _required_environment("AEGRA_PROBE_URL"),
        },
    )
    await client.threads.delete(thread_id, headers=_headers(issuer))


async def _prepare() -> None:
    issuer = _issuer()
    client = get_client(
        url=_required_environment("AEGRA_PROBE_URL"),
        timeout=httpx.Timeout(30.0),
    )
    assistants = await client.assistants.search(
        graph_id="aegra_durability_fixture",
        limit=10,
        headers=_headers(issuer),
    )
    assistant = next(
        (
            item
            for item in assistants
            if isinstance(item, dict)
            and item.get("graph_id") == "aegra_durability_fixture"
        ),
        None,
    )
    if assistant is None:
        raise AssertionError("Aegra did not register the durability fixture")
    assistant_id = _required_string(assistant, "assistant_id")
    thread = await client.threads.create(headers=_headers(issuer))
    thread_id = _required_string(thread, "thread_id")
    run = await client.runs.create(
        thread_id,
        assistant_id,
        input={
            "proof_id": _required_environment("AEGRA_PROBE_ID"),
            "sleep_seconds": float(os.environ.get("AEGRA_PROBE_SLEEP_SECONDS", "90")),
        },
        stream_mode=["values", "custom"],
        headers=_headers(issuer),
    )
    run_id = _required_string(run, "run_id")

    loop = asyncio.get_running_loop()
    deadline = loop.time() + 30.0
    checkpoint_id = ""
    prepared_count: Any = None
    while loop.time() < deadline:
        state = await client.threads.get_state(thread_id, headers=_headers(issuer))
        current = await client.runs.get(thread_id, run_id, headers=_headers(issuer))
        values = state.get("values") or {}
        if not isinstance(values, dict):
            raise AssertionError("Thread state values are invalid")
        status = current.get("status")
        checkpoint = state.get("checkpoint") or {}
        if values.get("stage") == "checkpoint_committed" and status == "running":
            checkpoint_id = _required_string(checkpoint, "checkpoint_id")
            prepared_count = values.get("prepared_count")
            break
        if status in TERMINAL_FAILURES or status == "success":
            raise AssertionError(f"Run became {status!r} before the kill checkpoint")
        await asyncio.sleep(0.2)
    if not checkpoint_id:
        raise AssertionError("checkpoint_committed was not observed before deadline")
    if prepared_count != 1:
        raise AssertionError("prepare node did not commit exactly once before kill")

    _write_json(
        Path(_required_environment("AEGRA_PROBE_STATE_FILE")),
        {
            "schema_version": "1.0",
            "proof_id": _required_environment("AEGRA_PROBE_ID"),
            "assistant_id": assistant_id,
            "thread_id": thread_id,
            "run_id": run_id,
            "checkpoint_id_before": checkpoint_id,
            "prepared_count_before": prepared_count,
            "status_before": "running",
        },
    )


async def _verify() -> None:
    issuer = _issuer()
    state_file = Path(_required_environment("AEGRA_PROBE_STATE_FILE"))
    before = json.loads(state_file.read_text(encoding="utf-8"))
    if not isinstance(before, dict) or before.get("schema_version") != "1.0":
        raise AssertionError("Aegra prepare manifest is invalid")
    thread_id = _required_string(before, "thread_id")
    run_id = _required_string(before, "run_id")
    checkpoint_before = _required_string(before, "checkpoint_id_before")

    client = get_client(
        url=_required_environment("AEGRA_PROBE_URL"),
        timeout=httpx.Timeout(30.0),
    )
    loop = asyncio.get_running_loop()
    deadline = loop.time() + float(os.environ.get("AEGRA_PROBE_VERIFY_TIMEOUT", "150"))
    while loop.time() < deadline:
        current = await client.runs.get(thread_id, run_id, headers=_headers(issuer))
        status = current.get("status")
        if status == "success":
            break
        if status in TERMINAL_FAILURES:
            raise AssertionError(f"Recovered Run became {status!r}")
        await asyncio.sleep(0.5)
    else:
        raise AssertionError("Recovered Run did not complete before deadline")

    state = await client.threads.get_state(thread_id, headers=_headers(issuer))
    history = await client.threads.get_history(
        thread_id,
        limit=100,
        headers=_headers(issuer),
    )
    checkpoint_ids = [
        item.get("checkpoint", {}).get("checkpoint_id")
        for item in history
        if isinstance(item, dict) and isinstance(item.get("checkpoint"), dict)
    ]
    values = state.get("values") or {}
    if not isinstance(values, dict):
        raise AssertionError("Recovered Thread state values are invalid")
    output = current.get("output") or {}
    if not isinstance(output, dict):
        raise AssertionError("Recovered Run output is invalid")
    result = {
        "schema_version": "1.0",
        "proof_id": before.get("proof_id"),
        "thread_id": thread_id,
        "run_id": run_id,
        "status_after": current.get("status"),
        "checkpoint_id_after": _required_string(
            state.get("checkpoint") or {}, "checkpoint_id"
        ),
        "checkpoint_before_preserved": checkpoint_before in checkpoint_ids,
        "history_count": len(checkpoint_ids),
        "prepared_count_after": values.get("prepared_count"),
        "completion_count_after": values.get("completion_count"),
        "stage_after": values.get("stage"),
        "terminal_status_after": output.get(
            "terminal_status", values.get("terminal_status")
        ),
    }
    if result["prepared_count_after"] != 1:
        raise AssertionError("prepare node replayed across worker recovery")
    if result["completion_count_after"] != 1:
        raise AssertionError("finish node did not commit exactly once")
    if result["checkpoint_before_preserved"] is not True:
        raise AssertionError("pre-kill checkpoint disappeared from public history")
    if result["terminal_status_after"] != "succeeded":
        raise AssertionError("Recovered graph did not reach succeeded terminal state")
    _write_json(Path(_required_environment("AEGRA_PROBE_RESULT_FILE")), result)


def _issue_token() -> None:
    print(_authorization(_issuer()).removeprefix("Bearer "))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "phase",
        choices=(
            "issue-token",
            "matrix",
            "canonical-prepare",
            "canonical-verify",
            "prepare",
            "verify",
            "ha-prepare",
            "ha-observe",
            "ha-resume",
            "ha-final",
        ),
    )
    phase = parser.parse_args().phase
    if phase == "issue-token":
        _issue_token()
        return
    if phase == "matrix":
        asyncio.run(_matrix())
        return
    phases = {
        "canonical-prepare": _canonical_prepare,
        "canonical-verify": _canonical_verify,
        "prepare": _prepare,
        "verify": _verify,
        "ha-prepare": _ha_prepare,
        "ha-observe": _ha_observe,
        "ha-resume": _ha_resume,
        "ha-final": _ha_final,
    }
    asyncio.run(phases[phase]())


if __name__ == "__main__":
    main()
