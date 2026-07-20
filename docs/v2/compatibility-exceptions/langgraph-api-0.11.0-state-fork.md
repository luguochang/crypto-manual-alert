# LangGraph API State Fork Compatibility Exception

Date: 2026-07-19

Authority: informative compatibility record; does not amend the V2 normative
specification or implementation plan.

Status: `PROPOSED / NOT ACCEPTED`

Current capability verdict: `RED / unknown_command`

## Decision

No exception is accepted. Protocol `0.0.18` declares `state.fork`, but the
observed development Agent Server dispatch returns `unknown_command`. Product
fork remains available only through Product-owned admission translated to the
official Runs REST/SDK checkpoint boundary. That fallback is valid Product
behavior, not proof that Protocol `state.fork` is implemented.

The filename retains the `langgraph-api 0.11.0` name required by the Task 8
plan. Development contracts now execute against `0.11.1`; the licensed image
verifier remains at `0.11.0` and its live behavior is unproved.

## Version Matrix

| Surface | Version or lock | Observed result | Evidence status |
|---|---|---|---|
| Development Agent Server | `langgraph-api 0.11.1` | `state.fork` is absent from the known-command set and dispatch returns the exact `unknown_command` error. | `RED` |
| Development graph runtime | `langgraph 1.2.9` | No separate graph-runtime behavior can make an unsupported Agent Server command available. | Boundary fact |
| Python Protocol binding | `langchain-protocol 0.0.18` | Declares `state.fork` with required `checkpoint_id` and optional `input`/`config`; declares a fork result containing `run_id` and `thread_id`. | Static contract only |
| JavaScript Protocol client | `@langchain/langgraph-sdk 1.9.25`, `@langchain/protocol 0.0.18` | Official `stream.state.fork()` reaches the server and receives `ProtocolError(code="unknown_command")`. | Known RED boundary |
| Python Runs adapter | `langgraph-sdk 0.4.2` | Supports top-level keyword-only `checkpoint_id=` on Runs create; transport contracts verify serialization. | Product fallback contract only |
| Licensed image verifier | `langgraph-api 0.11.0` | The verifier still asserts `0.11.0`; no licensed live Protocol or restart run was completed. | `UNPROVED` |

The observed `0.11.1` dispatch result does not prove the behavior of the
licensed `0.11.0` image. It does prove that the current development Protocol
capability is not GREEN.

## Expected And Actual

Expected command and result:

```text
request.method = state.fork
request.params.checkpoint_id = <checkpoint id>
result = { run_id: <new run>, thread_id: <fork thread> }
```

Actual development response:

```json
{
  "type": "error",
  "id": 73,
  "error": "unknown_command",
  "message": "Unknown protocol command: state.fork"
}
```

This is a compatibility defect between the declared Protocol command union and
the observed Agent Server command implementation. Recording the exact response
prevents drift from being hidden; it does not approve the defect.

## Validator And Probe

`backend/tests/contract/test_protocol_v2_capabilities.py` locks all of the
following:

- Protocol `0.0.18` still declares `state.fork` and `checkpoint_id`;
- the installed development Agent Server known-command set still omits it; and
- an isolated official `ThreadRunManager.handle_command()` dispatch returns the
  exact error above.

`tools/v2/probe_protocol_v2.mjs` performs the live official-client check through
`stream.state.fork()`. It accepts only the known `ProtocolError` with
`code="unknown_command"` as the recorded boundary and fails on unexpected
success or any other error. The current overall Protocol probe remains RED
because the root `checkpoints` event is missing, so this sub-check cannot be
used to claim that either compatibility exception has been accepted.

`backend/tests/contract/test_agent_server_protocol.py` verifies that the Python
Runs client exposes and serializes top-level `checkpoint_id=`. This is a
transport/fallback contract, not a `state.fork` capability probe.

## Fallback Boundary

The only supported Product fork path is:

```text
owner-scoped Product fork admission
  -> selected Product source Run and checkpoint validation
  -> durable Product command
  -> official Python Runs create(checkpoint_id=<id>, durability="sync")
  -> new Product lineage Run
```

Boundary rules:

- the browser does not send a direct Protocol `state.fork` command;
- frontend `forkFrom` is normalized into Product admission and is not emitted
  to the Python client;
- `config.configurable.checkpoint_id` may be retained for correlation but does
  not replace the Runs client's top-level `checkpoint_id=` argument;
- Product authorization, idempotency, lineage, and reconciliation remain in
  force; and
- a successful Product-owned checkpoint fork proves only this admitted Runs
  path, not Protocol `state.fork`, licensed persistence, or restart recovery.

No private Agent Server endpoint, table, or second checkpoint state machine is
permitted as a workaround.

## Acceptance, Removal, And Upgrade Triggers

This proposed exception can be considered for acceptance only when the exact
licensed compatibility group completes the Task 8 live probes and governance
review. It is not accepted merely because Product has a bounded fallback.

Re-evaluate immediately when any of these changes:

- `langgraph-api`, `langgraph`, `langchain-protocol`,
  `@langchain/langgraph-sdk`, `@langchain/protocol`, or `langgraph-sdk` version;
- the licensed base image or image-verifier version assertion;
- the Agent Server known-command set or `state.fork` response;
- the Protocol `StateForkParams`/result schema; or
- Python Runs `checkpoint_id=` or frontend fork semantics.

If `state.fork` begins to succeed, the exact-error validator must fail first.
Then compare its authorization, checkpoint selection, idempotency, lineage, and
durability semantics with Product admission before changing the supported path.
Remove this record only after the chosen official path passes live development
and licensed probes, restart/durability evidence, zero-skip acceptance, and the
required review. If an upgrade preserves `unknown_command`, create or revise a
version-specific record; do not silently inherit this proposed exception.
