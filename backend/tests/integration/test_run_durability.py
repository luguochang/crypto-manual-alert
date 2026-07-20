"""Licensed Agent Server restart proof for Task 8.

The pure tests in this module are hermetic gating contracts.  The live tests are
release evidence only when an external probe explicitly supplies a licensed,
persistent Agent Server and a restart controller.  ``langgraph dev`` and the
in-memory Runtime are deliberately incapable of satisfying that gate.

External orchestration can run the proof in one process with ``controller`` or
in two invocations with ``prepare`` and ``verify``.  The staged flow writes only
public Agent Server identifiers and hashes; it never reads the Agent database.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Any, Literal
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from langgraph_sdk import get_client
from langgraph_sdk.errors import ConflictError
import pytest

from crypto_alert_v2.api.agent_server import (
    AgentServerRunner,
    RemoteInterruptSet,
    RemoteRunHandle,
)
from crypto_alert_v2.api.schemas import AnalysisSubmission
from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.auth.internal_token import InternalTokenIssuer


ProofPhase = Literal["controller", "prepare", "verify"]
RunDurability = Literal["sync", "exit"]
RUNTIME_KIND = "licensed-persistent"
MANIFEST_VERSION = 2


class RuntimeProofUnavailable(ValueError):
    """The process was not explicitly configured for licensed proof."""


@dataclass(frozen=True, slots=True)
class LicensedRuntimeConfig:
    agent_server_url: str
    restart_controller_url: str | None
    restart_controller_token: str | None = field(repr=False)
    assistant_id: str
    durability: RunDurability
    phase: ProofPhase
    state_file: Path | None
    restart_receipt_file: Path | None
    timeout_seconds: float
    authorization_token: str | None = field(repr=False)
    jwt_private_key_file: Path | None = field(repr=False)
    jwt_key_id: str | None
    jwt_issuer: str | None
    jwt_audience: str | None
    actor: ActorContext


@dataclass(frozen=True, slots=True)
class InterruptProof:
    interrupt_id: str
    namespace: str
    checkpoint_id: str
    value_sha256: str


@dataclass(frozen=True, slots=True)
class RuntimeProofManifest:
    version: int
    assistant_id: str
    durability: RunDurability
    thread_id: str
    run_id: str
    task_id: str
    submit_product_run_id: str
    resume_product_run_id: str
    checkpoint_id: str
    checkpoint_map: dict[str, str]
    history_checkpoint_ids: tuple[str, ...]
    interrupts: tuple[InterruptProof, ...]

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(asdict(self), sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def read(cls, path: Path) -> "RuntimeProofManifest":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("version") != MANIFEST_VERSION:
            raise AssertionError("licensed Runtime proof manifest version is invalid")
        interrupts = payload.get("interrupts")
        if (
            not isinstance(interrupts, list)
            or not interrupts
            or not all(isinstance(item, dict) for item in interrupts)
        ):
            raise AssertionError(
                "licensed Runtime proof manifest interrupts are invalid"
            )
        return cls(
            version=MANIFEST_VERSION,
            assistant_id=_required_payload_string(payload, "assistant_id"),
            durability=_required_durability(payload),
            thread_id=_required_payload_string(payload, "thread_id"),
            run_id=_required_payload_string(payload, "run_id"),
            task_id=_required_payload_string(payload, "task_id"),
            submit_product_run_id=_required_payload_string(
                payload, "submit_product_run_id"
            ),
            resume_product_run_id=_required_payload_string(
                payload, "resume_product_run_id"
            ),
            checkpoint_id=_required_payload_string(payload, "checkpoint_id"),
            checkpoint_map=_string_mapping(payload.get("checkpoint_map")),
            history_checkpoint_ids=tuple(
                _required_string_sequence(
                    payload.get("history_checkpoint_ids"),
                    "history_checkpoint_ids",
                )
            ),
            interrupts=tuple(
                InterruptProof(
                    interrupt_id=_required_payload_string(item, "interrupt_id"),
                    namespace=_payload_string(item, "namespace"),
                    checkpoint_id=_required_payload_string(item, "checkpoint_id"),
                    value_sha256=_required_payload_string(item, "value_sha256"),
                )
                for item in interrupts
            ),
        )


@dataclass(frozen=True, slots=True)
class RestartReceipt:
    runtime_kind: str
    agent_server_url: str
    compose_project: str
    compose_service: str
    container_id_before: str
    container_id_after: str
    image_id: str
    locked_base_image: str
    generation_before: str
    generation_after: str

    @classmethod
    def validate(
        cls,
        payload: object,
        *,
        expected_agent_server_url: str,
    ) -> "RestartReceipt":
        if not isinstance(payload, dict):
            raise AssertionError("restart controller did not return a JSON object")
        if payload.get("restarted") is not True:
            raise AssertionError("restart controller did not acknowledge a restart")
        if payload.get("licensed") is not True:
            raise AssertionError("restart controller did not attest a licensed Runtime")
        runtime_kind = _required_payload_string(payload, "runtime_kind")
        agent_server_url = _required_payload_string(payload, "agent_server_url")
        compose_project = _required_payload_string(payload, "compose_project")
        compose_service = _required_payload_string(payload, "compose_service")
        container_id_before = _required_payload_string(payload, "container_id_before")
        container_id_after = _required_payload_string(payload, "container_id_after")
        image_id = _required_payload_string(payload, "image_id")
        locked_base_image = _required_payload_string(payload, "locked_base_image")
        before = _required_payload_string(payload, "generation_before")
        after = _required_payload_string(payload, "generation_after")
        if runtime_kind != RUNTIME_KIND:
            raise AssertionError(
                "restart controller did not attest licensed-persistent Runtime"
            )
        if agent_server_url.rstrip("/") != expected_agent_server_url.rstrip("/"):
            raise AssertionError(
                "restart receipt belongs to a different Agent Server URL"
            )
        if compose_service != "langgraph-api":
            raise AssertionError(
                "restart receipt is not bound to the langgraph-api Compose service"
            )
        if payload.get("target_unavailable_observed") is not True:
            raise AssertionError(
                "restart receipt did not prove the bound URL became unavailable"
            )
        if payload.get("target_recovered_observed") is not True:
            raise AssertionError(
                "restart receipt did not prove the bound URL recovered"
            )
        if payload.get("image_verifier_exit_code") != 0:
            raise AssertionError(
                "restart receipt did not bind the successful image verifier"
            )
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
            raise AssertionError("restart receipt image identity is invalid")
        if not re.fullmatch(
            r"langchain/langgraph-api@sha256:[0-9a-f]{64}", locked_base_image
        ):
            raise AssertionError("restart receipt locked base image is invalid")
        if before == after:
            raise AssertionError("restart controller generation did not change")
        return cls(
            runtime_kind=runtime_kind,
            agent_server_url=agent_server_url,
            compose_project=compose_project,
            compose_service=compose_service,
            container_id_before=container_id_before,
            container_id_after=container_id_after,
            image_id=image_id,
            locked_base_image=locked_base_image,
            generation_before=before,
            generation_after=after,
        )

    @classmethod
    def read(
        cls,
        path: Path,
        *,
        expected_agent_server_url: str,
    ) -> "RestartReceipt":
        return cls.validate(
            json.loads(path.read_text(encoding="utf-8")),
            expected_agent_server_url=expected_agent_server_url,
        )


def load_licensed_runtime_config(
    environment: Mapping[str, str],
) -> LicensedRuntimeConfig:
    phase_value = environment.get("LICENSED_AGENT_SERVER_PROOF_PHASE", "controller")
    if phase_value not in {"controller", "prepare", "verify"}:
        raise RuntimeProofUnavailable(
            "LICENSED_AGENT_SERVER_PROOF_PHASE must be controller, prepare, or verify"
        )
    phase: ProofPhase = phase_value  # type: ignore[assignment]
    required = {
        "LICENSED_AGENT_SERVER_TESTS": "1",
        "LICENSED_AGENT_SERVER_LICENSE_ASSERTION": "1",
        "LICENSED_AGENT_SERVER_RUNTIME_KIND": RUNTIME_KIND,
    }
    missing = [
        name for name, value in required.items() if environment.get(name) != value
    ]
    value_names = ["LICENSED_AGENT_SERVER_URL"]
    if phase == "controller":
        value_names.append("LICENSED_AGENT_SERVER_RESTART_URL")
    if not environment.get("LICENSED_AGENT_SERVER_TOKEN", "").strip():
        value_names.extend(
            (
                "INTERNAL_JWT_PRIVATE_KEY_FILE",
                "INTERNAL_JWT_KID",
                "INTERNAL_JWT_ISSUER",
                "AGENT_SERVER_INTERNAL_JWT_AUDIENCE",
            )
        )
    if phase in {"prepare", "verify"}:
        value_names.append("LICENSED_AGENT_SERVER_PROOF_STATE_FILE")
    if phase == "verify":
        value_names.append("LICENSED_AGENT_SERVER_RESTART_RECEIPT_FILE")
    missing.extend(
        name for name in value_names if not environment.get(name, "").strip()
    )
    if missing:
        names = ", ".join(sorted(set(missing)))
        raise RuntimeProofUnavailable(
            "licensed persistent proof is unproved; explicit opt-in, URL, license "
            f"assertion, JWT signing inputs, or restart controller is missing: {names}"
        )

    state_file_value = environment.get("LICENSED_AGENT_SERVER_PROOF_STATE_FILE", "")
    receipt_file_value = environment.get(
        "LICENSED_AGENT_SERVER_RESTART_RECEIPT_FILE", ""
    )
    if phase in {"prepare", "verify"} and not state_file_value.strip():
        raise RuntimeProofUnavailable(
            "staged licensed proof requires LICENSED_AGENT_SERVER_PROOF_STATE_FILE"
        )
    if phase == "verify" and not receipt_file_value.strip():
        raise RuntimeProofUnavailable(
            "verify phase requires LICENSED_AGENT_SERVER_RESTART_RECEIPT_FILE"
        )

    restart_url = environment.get("LICENSED_AGENT_SERVER_RESTART_URL", "").strip()
    if phase == "controller" and not restart_url:
        raise RuntimeProofUnavailable(
            "controller proof requires LICENSED_AGENT_SERVER_RESTART_URL"
        )

    agent_server_url = environment["LICENSED_AGENT_SERVER_URL"].rstrip("/")
    _validate_http_url(agent_server_url, "LICENSED_AGENT_SERVER_URL")
    if restart_url:
        _validate_http_url(restart_url, "LICENSED_AGENT_SERVER_RESTART_URL")

    authorization_token = environment.get("LICENSED_AGENT_SERVER_TOKEN", "").strip()
    private_key_value = environment.get("INTERNAL_JWT_PRIVATE_KEY_FILE", "").strip()
    private_key_file = Path(private_key_value) if private_key_value else None
    jwt_key_id = environment.get("INTERNAL_JWT_KID", "").strip() or None
    jwt_issuer = environment.get("INTERNAL_JWT_ISSUER", "").strip() or None
    jwt_audience = (
        environment.get("AGENT_SERVER_INTERNAL_JWT_AUDIENCE", "").strip() or None
    )
    if authorization_token and len(authorization_token.split(".")) != 3:
        raise RuntimeProofUnavailable(
            "LICENSED_AGENT_SERVER_TOKEN must be a compact JWT without a Bearer prefix"
        )
    if private_key_file is not None and (
        private_key_file.name == ".env" or not private_key_file.is_file()
    ):
        raise RuntimeProofUnavailable(
            "INTERNAL_JWT_PRIVATE_KEY_FILE must name an existing key file, not .env"
        )
    signing_ready = all(
        value is not None
        for value in (private_key_file, jwt_key_id, jwt_issuer, jwt_audience)
    )
    if phase == "controller" and not signing_ready:
        raise RuntimeProofUnavailable(
            "controller proof requires complete JWT signing inputs so authorization "
            "can be renewed after restart"
        )
    if not authorization_token and not signing_ready:
        raise RuntimeProofUnavailable(
            "licensed proof requires LICENSED_AGENT_SERVER_TOKEN or complete JWT "
            "signing inputs"
        )
    try:
        timeout_seconds = float(
            environment.get("LICENSED_AGENT_SERVER_TIMEOUT_SECONDS", "120")
        )
    except ValueError as exc:
        raise RuntimeProofUnavailable(
            "LICENSED_AGENT_SERVER_TIMEOUT_SECONDS must be numeric"
        ) from exc
    if not 10 <= timeout_seconds <= 600:
        raise RuntimeProofUnavailable(
            "LICENSED_AGENT_SERVER_TIMEOUT_SECONDS must be between 10 and 600"
        )

    durability_value = environment.get("LICENSED_AGENT_SERVER_TEST_DURABILITY", "sync")
    if durability_value not in {"sync", "exit"}:
        raise RuntimeProofUnavailable(
            "LICENSED_AGENT_SERVER_TEST_DURABILITY must be sync or exit"
        )
    durability: RunDurability = durability_value  # type: ignore[assignment]

    return LicensedRuntimeConfig(
        agent_server_url=agent_server_url,
        restart_controller_url=restart_url or None,
        restart_controller_token=environment.get("LICENSED_AGENT_SERVER_RESTART_TOKEN"),
        assistant_id=environment.get(
            "LICENSED_AGENT_SERVER_TEST_ASSISTANT", "multi_interrupt_fixture"
        ),
        durability=durability,
        phase=phase,
        state_file=Path(state_file_value) if state_file_value else None,
        restart_receipt_file=(Path(receipt_file_value) if receipt_file_value else None),
        timeout_seconds=timeout_seconds,
        authorization_token=authorization_token or None,
        jwt_private_key_file=private_key_file,
        jwt_key_id=jwt_key_id,
        jwt_issuer=jwt_issuer,
        jwt_audience=jwt_audience,
        actor=ActorContext(
            tenant_id=environment.get(
                "LICENSED_AGENT_SERVER_TEST_TENANT", "task-08-proof-tenant"
            ),
            workspace_id=environment.get(
                "LICENSED_AGENT_SERVER_TEST_WORKSPACE", "task-08-proof-workspace"
            ),
            user_id=environment.get(
                "LICENSED_AGENT_SERVER_TEST_USER", "task-08-proof-user"
            ),
            identity_issuer=environment.get(
                "LICENSED_AGENT_SERVER_TEST_IDENTITY_ISSUER", "task-08-licensed-proof"
            ),
            roles=("analyst",),
            permissions=("analysis:read", "analysis:write"),
        ),
    )


class LicensedRuntimeHarness:
    def __init__(self, config: LicensedRuntimeConfig) -> None:
        self.config = config
        self.client = get_client(
            url=config.agent_server_url,
            timeout=httpx.Timeout(config.timeout_seconds),
        )

    def authorization(self) -> str:
        if self.config.authorization_token is not None:
            return f"Bearer {self.config.authorization_token}"
        assert self.config.jwt_private_key_file is not None
        assert self.config.jwt_key_id is not None
        assert self.config.jwt_issuer is not None
        assert self.config.jwt_audience is not None
        private_key = self.config.jwt_private_key_file.read_text(encoding="utf-8")
        issuer = InternalTokenIssuer(
            private_key=private_key,
            key_id=self.config.jwt_key_id,
            issuer=self.config.jwt_issuer,
            audience=self.config.jwt_audience,
            ttl_seconds=60,
        )
        token = issuer.issue(
            subject=self.config.actor.user_id,
            tenant_id=self.config.actor.tenant_id,
            workspace_id=self.config.actor.workspace_id,
            roles=self.config.actor.roles,
            permissions=self.config.actor.permissions,
            token_use="worker",
            identity_issuer=self.config.actor.identity_issuer,
        )
        return f"Bearer {token}"

    def headers(self) -> dict[str, str]:
        return {"authorization": self.authorization()}

    def runner(self, *, assistant_id: str | None = None) -> AgentServerRunner:
        return AgentServerRunner(
            client=self.client,
            assistant_id=assistant_id or self.config.assistant_id,
            authorization_provider=lambda _: self.authorization(),
            resume_reconciliation_delays=(0.1, 0.25, 0.5, 1.0),
        )

    def fresh_handle(self, manifest: RuntimeProofManifest) -> RemoteRunHandle:
        return RemoteRunHandle(
            assistant_id=manifest.assistant_id,
            thread_id=manifest.thread_id,
            run_id=manifest.run_id,
            authorization=self.authorization(),
        )

    async def wait_until_reachable(self) -> None:
        deadline = asyncio.get_running_loop().time() + self.config.timeout_seconds
        last_error: BaseException | None = None
        while asyncio.get_running_loop().time() < deadline:
            try:
                assistants = await self.client.assistants.search(
                    graph_id=self.config.assistant_id,
                    limit=10,
                    headers=self.headers(),
                )
                if any(
                    item.get("graph_id") == self.config.assistant_id
                    for item in assistants
                    if isinstance(item, dict)
                ):
                    return
            except Exception as exc:  # readiness must preserve the final cause
                last_error = exc
            await asyncio.sleep(0.5)
        raise AssertionError(
            "licensed Agent Server did not recover before the proof deadline"
        ) from last_error

    async def restart(self) -> RestartReceipt:
        if self.config.restart_controller_url is None:
            raise AssertionError("controller proof has no restart controller URL")
        headers = {}
        if self.config.restart_controller_token:
            headers["authorization"] = f"Bearer {self.config.restart_controller_token}"
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self.config.timeout_seconds)
        ) as client:
            response = await client.post(
                self.config.restart_controller_url,
                headers=headers,
                json={
                    "runtime_kind": RUNTIME_KIND,
                    "agent_server_url": self.config.agent_server_url,
                },
            )
        response.raise_for_status()
        receipt = RestartReceipt.validate(
            response.json(),
            expected_agent_server_url=self.config.agent_server_url,
        )
        await self.wait_until_reachable()
        return receipt

    async def delete_thread(self, thread_id: str) -> None:
        await self.client.threads.delete(thread_id, headers=self.headers())


def licensed_harness_or_skip(expected_phase: ProofPhase) -> LicensedRuntimeHarness:
    try:
        config = load_licensed_runtime_config(os.environ)
    except RuntimeProofUnavailable as exc:
        pytest.skip(str(exc))
    if config.phase != expected_phase:
        pytest.skip(
            f"licensed proof phase is {config.phase}; {expected_phase} phase is unproved"
        )
    return LicensedRuntimeHarness(config)


async def create_acknowledged_interrupt(
    harness: LicensedRuntimeHarness,
) -> RuntimeProofManifest:
    await harness.wait_until_reachable()
    runner = harness.runner()
    suffix = uuid4().hex
    task_id = f"task-08-durability-{suffix}"
    submit_product_run_id = f"task-08-submit-{suffix}"
    handle = await runner.start(
        actor=harness.config.actor,
        task_id=task_id,
        product_thread_id=None,
        product_run_id=submit_product_run_id,
        submission=AnalysisSubmission(
            symbol="BTC-USDT-SWAP",
            horizon="4h",
            query_text="Task 8 licensed persistent Runtime durability proof.",
            notify=False,
        ),
        review_policy="required",
        durability=harness.config.durability,
    )
    handle = RemoteRunHandle(
        assistant_id=handle.assistant_id,
        thread_id=handle.thread_id,
        run_id=handle.run_id,
        authorization=harness.authorization(),
    )
    await _wait_for_interrupt(harness, runner, handle)
    interrupt_set = await runner.get_interrupts(handle)
    history_ids = await _history_checkpoint_ids(harness, handle.thread_id)
    if interrupt_set.checkpoint.checkpoint_id not in history_ids:
        raise AssertionError("acknowledged checkpoint is absent from Thread history")
    return RuntimeProofManifest(
        version=MANIFEST_VERSION,
        assistant_id=handle.assistant_id,
        durability=harness.config.durability,
        thread_id=handle.thread_id,
        run_id=handle.run_id,
        task_id=task_id,
        submit_product_run_id=submit_product_run_id,
        resume_product_run_id=f"task-08-resume-{suffix}",
        checkpoint_id=interrupt_set.checkpoint.checkpoint_id,
        checkpoint_map=dict(interrupt_set.checkpoint.checkpoint_map),
        history_checkpoint_ids=history_ids,
        interrupts=_interrupt_proofs(interrupt_set),
    )


async def assert_acknowledged_state_survived(
    harness: LicensedRuntimeHarness,
    manifest: RuntimeProofManifest,
) -> RemoteInterruptSet:
    thread = await harness.client.threads.get(
        manifest.thread_id, headers=harness.headers()
    )
    if not isinstance(thread, dict) or thread.get("thread_id") != manifest.thread_id:
        raise AssertionError("acknowledged Thread was not recovered after restart")
    run = await harness.client.runs.get(
        manifest.thread_id,
        manifest.run_id,
        headers=harness.headers(),
    )
    if not isinstance(run, dict) or run.get("run_id") != manifest.run_id:
        raise AssertionError("acknowledged Run was not recovered after restart")

    observed = await harness.runner(assistant_id=manifest.assistant_id).get_interrupts(
        harness.fresh_handle(manifest)
    )
    assert observed.checkpoint.thread_id == manifest.thread_id
    assert observed.checkpoint.checkpoint_id == manifest.checkpoint_id
    assert observed.checkpoint.checkpoint_map == manifest.checkpoint_map
    assert _interrupt_proofs(observed) == manifest.interrupts

    recovered_history = set(await _history_checkpoint_ids(harness, manifest.thread_id))
    missing_history = set(manifest.history_checkpoint_ids) - recovered_history
    assert not missing_history, (
        "acknowledged Thread history was lost across restart: "
        f"{sorted(missing_history)}"
    )
    return observed


async def resume_with_one_winner(
    harness: LicensedRuntimeHarness,
    manifest: RuntimeProofManifest,
    interrupt_set: RemoteInterruptSet,
) -> RemoteRunHandle:
    responses = {
        item.interrupt_id: {"action": "approve"} for item in interrupt_set.interrupts
    }

    async def attempt() -> RemoteRunHandle:
        return await harness.runner(assistant_id=manifest.assistant_id).resume(
            actor=harness.config.actor,
            handle=harness.fresh_handle(manifest),
            task_id=manifest.task_id,
            product_run_id=manifest.resume_product_run_id,
            responses=responses,
            checkpoint=interrupt_set.checkpoint,
        )

    outcomes = await asyncio.gather(attempt(), attempt(), return_exceptions=True)
    winners = [item for item in outcomes if isinstance(item, RemoteRunHandle)]
    errors = [item for item in outcomes if isinstance(item, BaseException)]
    assert winners, (
        f"no resume contender won: {[type(error).__name__ for error in errors]}"
    )
    assert all(isinstance(error, ConflictError) for error in errors), (
        "resume contender failed for a reason other than the expected one-winner "
        f"conflict: {[type(error).__name__ for error in errors]}"
    )

    matching = await _matching_product_runs(harness, manifest)
    assert len(matching) == 1, (
        "resume one-winner invariant failed; expected exactly one official Run, "
        f"found {len(matching)}"
    )
    winner_id = _required_payload_string(matching[0], "run_id")
    assert {winner.run_id for winner in winners} == {winner_id}

    replay = await harness.runner(assistant_id=manifest.assistant_id).find(
        actor=harness.config.actor,
        task_id=manifest.task_id,
        product_thread_id=manifest.thread_id,
        product_run_id=manifest.resume_product_run_id,
    )
    assert replay is not None and replay.run_id == winner_id
    completed = RemoteRunHandle(
        assistant_id=manifest.assistant_id,
        thread_id=manifest.thread_id,
        run_id=winner_id,
        authorization=harness.authorization(),
    )
    output = await harness.runner(assistant_id=manifest.assistant_id).join(completed)
    assert output.get("terminal_status") == "succeeded"
    assert output.get("completion_count") == 1
    artifact = output.get("artifact")
    assert isinstance(artifact, dict) and artifact.get("status") == "committed"
    return completed


async def _wait_for_interrupt(
    harness: LicensedRuntimeHarness,
    runner: AgentServerRunner,
    handle: RemoteRunHandle,
) -> None:
    deadline = asyncio.get_running_loop().time() + harness.config.timeout_seconds
    while asyncio.get_running_loop().time() < deadline:
        current = RemoteRunHandle(
            assistant_id=handle.assistant_id,
            thread_id=handle.thread_id,
            run_id=handle.run_id,
            authorization=harness.authorization(),
        )
        state = await runner.get(current)
        if state.status == "interrupted":
            return
        if state.status in {"error", "timeout"}:
            raise AssertionError(
                f"fixture Run became {state.status} before its interrupt was acknowledged"
            )
        await asyncio.sleep(0.25)
    raise AssertionError("fixture Run did not reach an acknowledged interrupt")


async def _history_checkpoint_ids(
    harness: LicensedRuntimeHarness,
    thread_id: str,
) -> tuple[str, ...]:
    history = await harness.client.threads.get_history(
        thread_id,
        limit=100,
        headers=harness.headers(),
    )
    ids: list[str] = []
    for item in history:
        if not isinstance(item, dict):
            raise AssertionError("Agent Server returned an invalid history entry")
        checkpoint = item.get("checkpoint")
        if not isinstance(checkpoint, dict):
            raise AssertionError("Agent Server history entry omitted its checkpoint")
        checkpoint_id = checkpoint.get("checkpoint_id")
        if isinstance(checkpoint_id, str) and checkpoint_id:
            ids.append(checkpoint_id)
    if not ids:
        raise AssertionError("Agent Server returned empty acknowledged Thread history")
    return tuple(ids)


async def _matching_product_runs(
    harness: LicensedRuntimeHarness,
    manifest: RuntimeProofManifest,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for offset in range(0, 10_000, 100):
        page = await harness.client.runs.list(
            manifest.thread_id,
            limit=100,
            offset=offset,
            headers=harness.headers(),
        )
        for item in page:
            if not isinstance(item, dict):
                raise AssertionError("Agent Server returned an invalid Run listing")
            metadata = item.get("metadata")
            if isinstance(metadata, dict) and (
                metadata.get("task_id") == manifest.task_id
                and metadata.get("product_run_id") == manifest.resume_product_run_id
            ):
                matches.append(item)
        if len(page) < 100:
            return matches
    raise AssertionError("Agent Server Run listing exceeded the proof scan limit")


def _interrupt_proofs(interrupt_set: RemoteInterruptSet) -> tuple[InterruptProof, ...]:
    return tuple(
        InterruptProof(
            interrupt_id=item.interrupt_id,
            namespace=item.namespace,
            checkpoint_id=item.checkpoint_id,
            value_sha256=sha256(
                json.dumps(
                    item.value,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest(),
        )
        for item in interrupt_set.interrupts
    )


def _validate_http_url(value: str, name: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise RuntimeProofUnavailable(f"{name} must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password:
        raise RuntimeProofUnavailable(f"{name} must not embed credentials")


def _required_payload_string(payload: Mapping[str, Any], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value:
        raise AssertionError(f"proof payload omitted {name}")
    return value


def _required_durability(payload: Mapping[str, Any]) -> RunDurability:
    value = payload.get("durability")
    if value not in {"sync", "exit"}:
        raise AssertionError("licensed Runtime proof manifest durability is invalid")
    return value  # type: ignore[return-value]


def _payload_string(payload: Mapping[str, Any], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str):
        raise AssertionError(f"proof payload returned invalid {name}")
    return value


def _required_string_sequence(value: object, name: str) -> list[str]:
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item for item in value)
    ):
        raise AssertionError(f"proof payload returned invalid {name}")
    return value


def _string_mapping(value: object) -> dict[str, str]:
    if not isinstance(value, dict) or not all(
        isinstance(key, str) and isinstance(item, str) and item
        for key, item in value.items()
    ):
        raise AssertionError("proof payload returned invalid checkpoint_map")
    return dict(value)


def test_licensed_runtime_gate_is_closed_by_default() -> None:
    with pytest.raises(RuntimeProofUnavailable, match="unproved") as error:
        load_licensed_runtime_config({})

    reason = str(error.value)
    assert "LICENSED_AGENT_SERVER_TESTS" in reason
    assert "LICENSED_AGENT_SERVER_URL" in reason
    assert "LICENSED_AGENT_SERVER_LICENSE_ASSERTION" in reason
    assert "LICENSED_AGENT_SERVER_RESTART_URL" in reason


def test_in_memory_runtime_cannot_claim_licensed_durability(tmp_path: Path) -> None:
    private_key = tmp_path / "private.pem"
    private_key.write_text("test-only-key", encoding="utf-8")
    environment = {
        "LICENSED_AGENT_SERVER_TESTS": "1",
        "LICENSED_AGENT_SERVER_LICENSE_ASSERTION": "1",
        "LICENSED_AGENT_SERVER_RUNTIME_KIND": "in-memory-development",
        "LICENSED_AGENT_SERVER_URL": "http://127.0.0.1:8123",
        "LICENSED_AGENT_SERVER_RESTART_URL": "http://127.0.0.1:9999/restart",
        "INTERNAL_JWT_PRIVATE_KEY_FILE": str(private_key),
        "INTERNAL_JWT_KID": "test-key",
        "INTERNAL_JWT_ISSUER": "test-issuer",
        "AGENT_SERVER_INTERNAL_JWT_AUDIENCE": "test-audience",
    }

    with pytest.raises(RuntimeProofUnavailable, match="RUNTIME_KIND"):
        load_licensed_runtime_config(environment)


def test_staged_proof_accepts_an_explicit_short_lived_token(tmp_path: Path) -> None:
    config = load_licensed_runtime_config(
        {
            "LICENSED_AGENT_SERVER_TESTS": "1",
            "LICENSED_AGENT_SERVER_LICENSE_ASSERTION": "1",
            "LICENSED_AGENT_SERVER_RUNTIME_KIND": RUNTIME_KIND,
            "LICENSED_AGENT_SERVER_URL": "https://agent.example.com",
            "LICENSED_AGENT_SERVER_PROOF_PHASE": "prepare",
            "LICENSED_AGENT_SERVER_PROOF_STATE_FILE": str(tmp_path / "state.json"),
            "LICENSED_AGENT_SERVER_TOKEN": "header.payload.signature",
        }
    )

    assert config.phase == "prepare"
    assert config.restart_controller_url is None
    assert config.authorization_token == "header.payload.signature"
    assert "header.payload.signature" not in repr(config)


def test_controller_proof_requires_renewable_authorization() -> None:
    environment = {
        "LICENSED_AGENT_SERVER_TESTS": "1",
        "LICENSED_AGENT_SERVER_LICENSE_ASSERTION": "1",
        "LICENSED_AGENT_SERVER_RUNTIME_KIND": RUNTIME_KIND,
        "LICENSED_AGENT_SERVER_URL": "https://agent.example.com",
        "LICENSED_AGENT_SERVER_RESTART_URL": "https://controller.example.com/restart",
        "LICENSED_AGENT_SERVER_TOKEN": "header.payload.signature",
    }

    with pytest.raises(RuntimeProofUnavailable, match="complete JWT signing inputs"):
        load_licensed_runtime_config(environment)


def test_restart_receipt_is_bound_to_license_url_and_generation() -> None:
    payload = {
        "restarted": True,
        "licensed": True,
        "runtime_kind": RUNTIME_KIND,
        "agent_server_url": "https://agent.example.com",
        "compose_project": "crypto-manual-alert-v2",
        "compose_service": "langgraph-api",
        "container_id_before": "a" * 64,
        "container_id_after": "a" * 64,
        "image_id": "sha256:" + "b" * 64,
        "locked_base_image": "langchain/langgraph-api@sha256:" + "c" * 64,
        "image_verifier_exit_code": 0,
        "target_unavailable_observed": True,
        "target_recovered_observed": True,
        "generation_before": "generation-1",
        "generation_after": "generation-2",
    }

    receipt = RestartReceipt.validate(
        payload,
        expected_agent_server_url="https://agent.example.com/",
    )
    assert receipt.generation_before == "generation-1"
    assert receipt.generation_after == "generation-2"

    with pytest.raises(AssertionError, match="different Agent Server"):
        RestartReceipt.validate(
            payload,
            expected_agent_server_url="https://other.example.com",
        )
    with pytest.raises(AssertionError, match="generation did not change"):
        RestartReceipt.validate(
            {**payload, "generation_after": "generation-1"},
            expected_agent_server_url="https://agent.example.com",
        )
    with pytest.raises(AssertionError, match="became unavailable"):
        RestartReceipt.validate(
            {**payload, "target_unavailable_observed": False},
            expected_agent_server_url="https://agent.example.com",
        )


@pytest.mark.asyncio
async def test_licensed_runtime_controller_restart_preserves_durable_state() -> None:
    harness = licensed_harness_or_skip("controller")
    manifest: RuntimeProofManifest | None = None
    try:
        manifest = await create_acknowledged_interrupt(harness)
        await harness.restart()
        recovered = await assert_acknowledged_state_survived(harness, manifest)
        await resume_with_one_winner(harness, manifest, recovered)
    finally:
        if manifest is not None:
            await harness.delete_thread(manifest.thread_id)


@pytest.mark.asyncio
async def test_licensed_runtime_prepare_acknowledged_restart_state() -> None:
    harness = licensed_harness_or_skip("prepare")
    assert harness.config.state_file is not None
    manifest = await create_acknowledged_interrupt(harness)
    manifest.write(harness.config.state_file)


@pytest.mark.asyncio
async def test_licensed_runtime_verify_state_after_external_restart() -> None:
    await _verify_licensed_runtime_state_after_external_restart()


async def _verify_licensed_runtime_state_after_external_restart(
    expected_durability: RunDurability | None = None,
) -> None:
    harness = licensed_harness_or_skip("verify")
    if (
        expected_durability is not None
        and harness.config.durability != expected_durability
    ):
        raise AssertionError(
            "licensed Runtime proof selected the wrong durability mode: "
            f"expected {expected_durability}, got {harness.config.durability}"
        )
    assert harness.config.state_file is not None
    assert harness.config.restart_receipt_file is not None
    RestartReceipt.read(
        harness.config.restart_receipt_file,
        expected_agent_server_url=harness.config.agent_server_url,
    )
    manifest = RuntimeProofManifest.read(harness.config.state_file)
    assert manifest.durability == harness.config.durability
    try:
        await harness.wait_until_reachable()
        recovered = await assert_acknowledged_state_survived(harness, manifest)
        await resume_with_one_winner(harness, manifest, recovered)
    finally:
        await harness.delete_thread(manifest.thread_id)


@pytest.mark.asyncio
async def test_live_server_effective_sync_durability_after_restart() -> None:
    await _verify_licensed_runtime_state_after_external_restart("sync")


@pytest.mark.asyncio
async def test_live_server_effective_exit_durability_after_restart() -> None:
    await _verify_licensed_runtime_state_after_external_restart("exit")


@pytest.mark.asyncio
async def test_live_product_admission_survives_agent_server_restart() -> None:
    harness = licensed_harness_or_skip("verify")
    config = harness.config
    token = os.environ.get(
        "LICENSED_AGENT_SERVER_PRODUCT_AUTHORIZATION_TOKEN", ""
    ).strip()
    task_id = os.environ.get("LICENSED_AGENT_SERVER_PRODUCT_TASK_ID", "").strip()
    thread_id = os.environ.get("LICENSED_AGENT_SERVER_PRODUCT_THREAD_ID", "").strip()
    run_id = os.environ.get("LICENSED_AGENT_SERVER_PRODUCT_RUN_ID", "").strip()
    if not all((token, task_id, thread_id, run_id)):
        raise AssertionError(
            "live Product admission proof requires its token and persisted identifiers"
        )
    if len(token.split(".")) != 3:
        raise AssertionError("live Product admission proof token is not a compact JWT")

    headers = {"authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(
        base_url=config.agent_server_url,
        timeout=httpx.Timeout(config.timeout_seconds),
    ) as product_client:
        task_response = await product_client.get(
            f"/app/api/v2/tasks/{task_id}",
            headers=headers,
        )
        task_response.raise_for_status()
        task = task_response.json()
    assert task.get("task_id") == task_id
    stream = task.get("agent_stream")
    assert isinstance(stream, dict)
    assert stream.get("protocol") == "langgraph-v2"
    assert stream.get("thread_id") == thread_id
    assert stream.get("run_id") == run_id

    client = get_client(
        url=config.agent_server_url,
        timeout=httpx.Timeout(config.timeout_seconds),
    )
    thread = await client.threads.get(thread_id, headers=headers)
    run = await client.runs.get(thread_id, run_id, headers=headers)
    assert isinstance(thread, dict) and thread.get("thread_id") == thread_id
    assert isinstance(run, dict) and run.get("run_id") == run_id
