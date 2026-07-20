"""Root/nested interrupt routing proof against a licensed Agent Server.

Hermetic namespace parsing is already covered by the AgentServerRunner contract
suite.  This module supplies the missing live boundary: the official Runtime,
the Product adapter metadata/idempotency pattern, and the public Thread/Run APIs.
It intentionally skips unless the licensed proof gate from test_run_durability
is fully configured.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

from crypto_alert_v2.api.agent_server import RemoteRunHandle
from tests.integration.test_run_durability import (
    LicensedRuntimeHarness,
    RuntimeProofManifest,
    _matching_product_runs,
    create_acknowledged_interrupt,
    licensed_harness_or_skip,
)


@pytest.mark.asyncio
async def test_licensed_runtime_routes_root_and_nested_interrupts_atomically() -> None:
    phase = os.environ.get("LICENSED_AGENT_SERVER_PROOF_PHASE", "controller")
    expected_phase = "verify" if phase == "verify" else "controller"
    harness = licensed_harness_or_skip(expected_phase)
    manifest = await create_acknowledged_interrupt(harness)
    try:
        await _prove_interrupt_routing(harness, manifest)
    finally:
        await harness.delete_thread(manifest.thread_id)


async def _prove_interrupt_routing(
    harness: LicensedRuntimeHarness,
    manifest: RuntimeProofManifest,
) -> None:
    runner = harness.runner(assistant_id=manifest.assistant_id)
    original = harness.fresh_handle(manifest)
    interrupt_set = await runner.get_interrupts(original)

    namespaces = {item.namespace for item in interrupt_set.interrupts}
    assert "" in namespaces
    nested = namespaces - {""}
    assert len(nested) == 1
    nested_namespace = nested.pop()
    assert nested_namespace.startswith("nested_review:")
    assert interrupt_set.checkpoint.checkpoint_map[""] == manifest.checkpoint_id
    assert interrupt_set.checkpoint.checkpoint_map[nested_namespace] == next(
        item.checkpoint_id
        for item in interrupt_set.interrupts
        if item.namespace == nested_namespace
    )

    root = next(item for item in interrupt_set.interrupts if item.namespace == "")
    child = next(
        item for item in interrupt_set.interrupts if item.namespace == nested_namespace
    )
    partial_product_run_id = f"{manifest.resume_product_run_id}-partial"
    with pytest.raises(RuntimeError, match="exactly match"):
        await runner.resume(
            actor=harness.config.actor,
            handle=original,
            task_id=manifest.task_id,
            product_run_id=partial_product_run_id,
            responses={root.interrupt_id: {"action": "approve"}},
            checkpoint=interrupt_set.checkpoint,
        )
    partial_manifest = manifest.__class__(
        version=manifest.version,
        assistant_id=manifest.assistant_id,
        durability=manifest.durability,
        thread_id=manifest.thread_id,
        run_id=manifest.run_id,
        task_id=manifest.task_id,
        submit_product_run_id=manifest.submit_product_run_id,
        resume_product_run_id=partial_product_run_id,
        checkpoint_id=manifest.checkpoint_id,
        checkpoint_map=manifest.checkpoint_map,
        history_checkpoint_ids=manifest.history_checkpoint_ids,
        interrupts=manifest.interrupts,
    )
    assert await _matching_product_runs(harness, partial_manifest) == []

    responses: dict[str, dict[str, Any]] = {
        root.interrupt_id: {"action": "approve", "comment": "root-approved"},
        child.interrupt_id: {"action": "approve", "comment": "nested-approved"},
    }
    resumed = await runner.resume(
        actor=harness.config.actor,
        handle=original,
        task_id=manifest.task_id,
        product_run_id=manifest.resume_product_run_id,
        responses=responses,
        checkpoint=interrupt_set.checkpoint,
    )
    output = await runner.join(
        RemoteRunHandle(
            assistant_id=resumed.assistant_id,
            thread_id=resumed.thread_id,
            run_id=resumed.run_id,
            authorization=harness.authorization(),
        )
    )
    assert output.get("root_review") == {
        "action": "approve",
        "edits": None,
        "comment": "root-approved",
    }
    assert output.get("nested_review") == {
        "action": "approve",
        "edits": None,
        "comment": "nested-approved",
    }
    assert output.get("completion_count") == 1

    replay = await harness.runner(assistant_id=manifest.assistant_id).resume(
        actor=harness.config.actor,
        handle=harness.fresh_handle(manifest),
        task_id=manifest.task_id,
        product_run_id=manifest.resume_product_run_id,
        responses=responses,
        checkpoint=interrupt_set.checkpoint,
    )
    assert replay.run_id == resumed.run_id
    assert len(await _matching_product_runs(harness, manifest)) == 1

    conflicting_product_run_id = f"{manifest.resume_product_run_id}-conflict"
    with pytest.raises(RuntimeError, match="belongs to another Run"):
        await harness.runner(assistant_id=manifest.assistant_id).resume(
            actor=harness.config.actor,
            handle=harness.fresh_handle(manifest),
            task_id=manifest.task_id,
            product_run_id=conflicting_product_run_id,
            responses={
                root.interrupt_id: {"action": "reject", "comment": "duplicate"},
                child.interrupt_id: {"action": "approve"},
            },
            checkpoint=interrupt_set.checkpoint,
        )
    conflict_manifest = manifest.__class__(
        version=manifest.version,
        assistant_id=manifest.assistant_id,
        durability=manifest.durability,
        thread_id=manifest.thread_id,
        run_id=manifest.run_id,
        task_id=manifest.task_id,
        submit_product_run_id=manifest.submit_product_run_id,
        resume_product_run_id=conflicting_product_run_id,
        checkpoint_id=manifest.checkpoint_id,
        checkpoint_map=manifest.checkpoint_map,
        history_checkpoint_ids=manifest.history_checkpoint_ids,
        interrupts=manifest.interrupts,
    )
    assert await _matching_product_runs(harness, conflict_manifest) == []
