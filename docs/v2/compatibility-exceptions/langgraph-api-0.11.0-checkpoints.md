# LangGraph API Checkpoints Channel Compatibility Exception

Date: 2026-07-19

Authority: informative compatibility record; does not amend the V2 normative
specification or implementation plan.

Status: `PROPOSED / NOT ACCEPTED`

Current capability verdict: `RED`

## Decision

No exception is accepted. Protocol `0.0.18` declares the root `checkpoints`
channel and its lightweight checkpoint envelope, but the live development
probe does not receive that envelope. The official Thread `getState` read can
recover a checkpoint ID for downstream diagnosis; it is not a substitute for
the missing Protocol event and cannot turn the probe GREEN.

The filename retains the `langgraph-api 0.11.0` name required by the Task 8
plan. The development compatibility group has since moved to `0.11.1`, while
the licensed image verifier remains pinned to `0.11.0`; both boundaries are
recorded separately below.

## Version Matrix

| Surface | Version or lock | Observed result | Evidence status |
|---|---|---|---|
| Development Agent Server | `langgraph-api 0.11.1` | Root subscription is admitted, but no valid lightweight root checkpoint envelope reaches the official client. | `RED` |
| Development graph runtime | `langgraph 1.2.9` | The upstream checkpoint path supplies the full `StateSnapshot`-shaped object where the Protocol boundary expects the lightweight checkpoint shape; that event is discarded at the incompatible boundary. | `RED` |
| Python Protocol binding | `langchain-protocol 0.0.18` | Declares `checkpoints` and requires checkpoint data containing `id`, `step`, `source`, and optional `parent_id`. | Static contract only |
| JavaScript Protocol client | `@langchain/langgraph-sdk 1.9.25`, `@langchain/protocol 0.0.18` | The official client opens the root channel set, but the live capability probe must use the diagnostic state fallback because the expected event is absent. | `RED` |
| Licensed image verifier | `langgraph-api 0.11.0` | The verifier still asserts `0.11.0`; no licensed live capability or restart run was completed. | `UNPROVED` |

The `0.11.1` development result must not be projected onto the `0.11.0`
licensed image. Conversely, a static `0.11.0` image-version check is not live
evidence that the channel works.

## Expected And Actual

Expected root event:

```text
method = checkpoints
params.namespace = []
params.data = {
  id: <checkpoint id>,
  parent_id?: <parent checkpoint id>,
  step: <superstep number>,
  source: input | loop | update | fork
}
```

Actual development behavior:

1. The server and Protocol bindings advertise or admit `checkpoints`.
2. `langgraph 1.2.9` produces the full upstream `StateSnapshot` representation
   for the checkpoint stream path.
3. The Protocol event boundary expects the lightweight `id/parent_id/step/source`
   envelope, so the incompatible full snapshot is discarded.
4. The root official client therefore observes no usable `checkpoints` event.

The locked OpenAPI fixed-channel enum also omits `checkpoints`. That schema lag
is a separate static mismatch. Runtime channel admission, graph transformer
registration, and the OpenAPI exception test do not prove a valid event was
delivered on the wire.

## Validator And Probe

The authoritative live validator is `tools/v2/probe_protocol_v2.mjs`:

- it subscribes to the root
  `values/checkpoints/lifecycle/input/messages/tools` channel set;
- `protocolCheckpointId()` accepts only a root `checkpoints` event with a
  non-empty `params.data.id`;
- when that event is absent, it calls the official
  `client.threads.getState()` only to continue downstream diagnosis;
- it records `root checkpoints channel emitted no lightweight Protocol
  checkpoint envelope`; and
- it exits with `EX_DATAERR` (`65`) rather than reporting capability success.

Supporting static validators are
`backend/tests/contract/test_protocol_v2_capabilities.py` and
`backend/tests/contract/test_agent_server_protocol.py`. They lock versions,
channel declarations, transformer registration, OpenAPI drift, and official
route shapes. They cannot replace the live JavaScript probe.

`tools/v2/probe_product_api.sh` is the outer licensed acceptance harness. No
successful zero-skip run of that harness exists for this capability.

## Fallback Boundary

Allowed diagnostic fallback:

- read the root checkpoint ID through the official Thread `getState` API;
- continue cleanup and independent downstream diagnostics; and
- report `official-state-fallback` in probe output while preserving the
  capability failure.

The fallback is not allowed to support any of these claims:

- Protocol `checkpoints` channel conformance;
- checkpoint-event ordering or `since` replay coverage;
- acceptance of this compatibility exception;
- licensed checkpoint persistence or restart recovery;
- server-effective `durability="exit"`; or
- V2 production readiness.

Product code must not add a private wire parser or reconstruct the missing
Protocol envelope from a full `StateSnapshot`. State/history reads remain
official diagnostic and Product-adapter APIs, not a second Protocol client.

## Acceptance, Removal, And Upgrade Triggers

This record may be considered for acceptance only after the Task 8 plan's live
capability requirements pass against the exact licensed compatibility group.
Until then it remains proposed and RED.

Re-evaluate immediately when any of these changes:

- `langgraph-api`, `langgraph`, `langchain-protocol`,
  `@langchain/langgraph-sdk`, or `@langchain/protocol` version;
- the licensed base image or `tools/v2/verify_agent_image.sh` version assertion;
- the Protocol checkpoint envelope or OpenAPI channel schema;
- `CheckpointsTransformer`, Protocol event normalization, or server event
  retention/replay behavior; or
- `probe_protocol_v2.mjs` fallback or checkpoint validation logic.

Remove this record when the official root stream emits the required lightweight
checkpoint envelope without the state fallback, the JavaScript probe exits
zero, and the licensed `prepare -> restart -> verify` sequence passes with zero
skips for the same source and version matrix. Any upgrade that still requires
the fallback keeps the capability RED and requires a new version-specific
record rather than silently carrying this one forward.

