# Task 8 Protocol V2 and Persistent Runtime Harness

Date: 2026-07-18

Evidence correction: 2026-07-19

Phase: `M2/M4` Product/Agent protocol and durability acceptance harness

## Verdict

The official Protocol v2 contracts, SDK serialization tests and restart-proof
harness exist. The live Protocol capability is not GREEN: the development root
`checkpoints` channel does not deliver the required lightweight envelope, and
the official `getState` fallback is diagnostic only. The licensed persistent
Runtime proof was not run.

```text
Task 8 harness: RED / PARTIAL
Root checkpoints channel: RED
state.fork: unknown_command / PROPOSED EXCEPTION / NOT ACCEPTED
Licensed persistent restart proof: RED / UNPROVED
durability="exit" server-effective proof: UNPROVED
V2: PARTIAL
Production Ready: NO
```

No `langgraph dev` or in-memory Runtime result is counted as persistence proof.
Static schema or SDK serialization tests are not counted as live server
capability proof.

## Architecture Boundary

Task 8 deliberately hosts Product routes as the Agent Server `/app` custom
application. `backend/langgraph.json` owns the custom app registration and
`crypto_alert_v2.http.app` mounts Product at `/app`. A separate `product-api`
service is prohibited by the approved deployment contract.

The whole Agent process therefore owns one failure domain. During a complete
Agent outage, the expected browser behavior is the bounded, redacted Product BFF
502. Product is not required to remain independently available under the
current ADR and Task 8 plan.

## Retained REDs

The Task 8 audit first found that the six planned protocol/durability artifacts
did not exist:

- `tools/v2/probe_product_api.sh`
- `tools/v2/probe_protocol_v2.mjs`
- `backend/tests/contract/test_agent_server_protocol.py`
- `backend/tests/contract/test_protocol_v2_capabilities.py`
- `backend/tests/integration/test_run_durability.py`
- `backend/tests/integration/test_agent_server_interrupt_routing.py`

The first parallel implementation was not accepted as written. Review retained
and corrected these additional REDs:

1. The shell probe referenced six obsolete/nonexistent test modules, so it
   could not reach a real test run.
2. It required mounted `/app` routes to appear in the Agent Server root
   OpenAPI document. FastAPI mounts correctly expose a separate route space and
   are not merged into that root schema.
3. It ran licensed tests without configuring a restart phase; all durability
   tests could skip while the script still printed `passed`.
4. The production image verifier correctly required exactly one canonical
   Graph, but the Task 8 QA image needs one additional explicit
   `multi_interrupt_fixture`. Without a scoped verifier mode, the QA image could
   never start.
5. The first optional verifier-argument implementation used an empty Bash array.
   macOS Bash 3.2 with `set -u` raised an unbound-variable error before Compose
   startup.
6. The initial implementation described Product/Agent process separation as a
   missing requirement. The approved plan says the opposite: Product is the
   Agent Server custom app.

None of these failures was hidden by removing assertions or counting skips.
The historical implementation review improved the harness, but it did not
produce an overall Task 8 GREEN. Later live evidence retained the root
`checkpoints` capability RED described below.

## Official Protocol Contracts

The current version boundaries are deliberately split:

| Surface | Locked version | Evidence boundary |
|---|---|---|
| Development Agent Server | `langgraph-api 0.11.1` | Live root checkpoint capability is RED. |
| Development graph runtime | `langgraph 1.2.9` | Full `StateSnapshot` shape reaches a boundary that expects a lightweight Protocol checkpoint envelope. |
| Python SDK / Protocol | `langgraph-sdk 0.4.2`, `langchain-protocol 0.0.18` | Static schema and transport evidence only where noted. |
| Frontend SDK / Protocol / React | `@langchain/langgraph-sdk 1.9.25`, `@langchain/protocol 0.0.18`, `@langchain/react 1.0.26` | Official live client is used by the Protocol probe. |
| Licensed image verifier | `langgraph-api 0.11.0` | Licensed live behavior, restart and `durability="exit"` are UNPROVED. |

The development `0.11.1` result must not be projected onto the licensed
`0.11.0` image, and the image verifier's version assertion is not live
capability evidence.

They verify the official assistants, threads, runs, Protocol command and event
stream routes remain present while Product stays namespaced under `/app`.

Python SDK transport tests use the official client with `httpx.MockTransport`
to inspect the actual outbound request body. They prove serialization, not
server-effective durability:

- Runs API `durability="sync"` and `durability="exit"` are top-level fields;
- resume uses the official `command={resume, update, goto}` shape;
- checkpoint fork uses the Python SDK's top-level `checkpoint_id=` argument;
- a retained `config.configurable.checkpoint_id` cannot replace that top-level
  argument; and
- frontend `forkFrom` is not emitted to the Python client.

Protocol bindings validate `run.start`, single and batch `input.respond`,
subscription commands, `agent.getTree`, `input.inject`, `state.get`,
`state.listCheckpoints` and the declared `state.fork` shape. Development
`langgraph-api 0.11.1` returns the exact `unknown_command` response for
`state.fork`. Product admission therefore translates an authorized fork into an
official Runs API create with top-level `checkpoint_id=`. That Product fallback
does not prove Protocol `state.fork` conformance.

Protocol `0.0.18`, the development runtime and the graph transformer all
declare or admit `checkpoints`, while the locked root OpenAPI fixed-channel enum
omits it. More importantly, the live root stream is RED: the upstream full
`StateSnapshot` shape is discarded where the Protocol envelope requires
`id`, optional `parent_id`, `step` and `source`, so the official client receives
no usable lightweight root checkpoint event.

Both versioned records are proposed and explicitly not accepted:

- `docs/v2/compatibility-exceptions/langgraph-api-0.11.0-checkpoints.md`
- `docs/v2/compatibility-exceptions/langgraph-api-0.11.0-state-fork.md`

## Official JavaScript Probe

`probe_protocol_v2.mjs` loads only the installed official
`@langchain/langgraph-sdk`. It does not implement a second protocol client.

Using an explicitly supplied Agent URL, short-lived token and assistant, it:

- opens the root `values/checkpoints/lifecycle/input/messages/tools` channels;
- seeds the canonical Graph at the HITL boundary through the official state API,
  avoiding provider/model cost in a protocol capability probe;
- sends real `run.start`, single `input.respond` and batch `input.respond`;
- reconnects with `since` and verifies ordered replay with no duplicate event
  IDs;
- validates the observed `state.fork -> unknown_command` boundary; and
- closes streams/transports and deletes temporary Threads in `finally`.

Timeouts are bounded. Endpoint, usage and configuration failures have stable
exit codes, and emitted errors redact Bearer and common model-key shapes.
When no lightweight root checkpoint event arrives, the probe reads the official
Thread state only so later diagnostics can continue, records
`official-state-fallback`, and exits `EX_DATAERR` (`65`) with a capability gap.
That fallback cannot satisfy the channel assertion or make the probe pass.

## Persistent Restart Proof

The live harness uses the official Python SDK and the existing
`AgentServerRunner`. It reads no Agent Server internal table.

The default pytest execution is skip-gated, not fail-closed acceptance: without
explicit licensed opt-in, Runtime kind, URL and authorization/restart inputs,
live tests skip with `UNPROVED` reasons. A hermetic test rejects an explicitly
selected in-memory Runtime, while the outer acceptance harness is intended to
reject licensed JUnit skips. No successful licensed outer-harness run exists.

Two live modes are supported:

- `controller`: an external licensed restart controller returns a receipt bound
  to the Agent URL and different before/after generations; renewable JWT signing
  inputs are mandatory.
- staged `prepare -> verify`: prepare persists only public Thread, Run,
  Checkpoint, history and hashed Interrupt evidence; external orchestration
  restarts the process; verify requires a restart receipt and a fresh short-lived
  token.

A successful licensed execution is designed to require the same Thread,
acknowledged Run, root and nested Interrupt IDs/namespaces, Checkpoint map and
prior history after restart. Concurrent resume contenders may return the same
reconciled handle or one official conflict, but exactly one official Run may
match the Product `task_id + product_run_id`. Final fixture output must have one
completion and one committed Artifact. These conditions remain UNPROVED.

The nested routing test is designed to require that a partial response creates
no Run, root and nested responses bind to their namespaces, replay returns the
same Run, and a conflicting post-consumption response creates no second Run.
Its licensed execution remains UNPROVED.

## Probe Orchestration

`probe_product_api.sh` contains the intended zero-skip acceptance sequence:

1. Refuse an existing same-name Compose project and require an entitlement.
2. Build the official pinned Agent image with
   `langgraph.multi-interrupt.json`.
3. Verify the exact canonical Graph plus the one allowlisted QA fixture; normal
   production builds still require only the canonical Graph.
4. Verify official root OpenAPI separately from authenticated Agent extension
   and Product readiness routes.
5. Run all current Product/Agent/Protocol contracts and reject any JUnit skip,
   error or failure.
6. Run the official JavaScript Protocol probe.
7. Run the licensed `prepare` test and require its public manifest.
8. Restart the real `langgraph-api` Compose container and record its before and
   after container generation.
9. Wait for Agent and Product readiness recovery, issue a fresh 60-second JWT,
   and run `verify` plus root/nested routing.
10. Reject any live JUnit skip/error/failure and tear down the owned stack and
    volumes through the earliest-installed trap.

This is a designed acceptance path, not completed evidence. The development
JavaScript Protocol probe currently stops the sequence with the root checkpoint
capability gap, and the licensed `0.11.0` sequence has not run. Therefore there
is no valid zero-skip Task 8 acceptance result.

`--expect-contract-failure` remains available for a genuine pre-GREEN RED, but
it accepts only assertion failures after capability prerequisites pass. A
collection, setup, missing-file or connection failure is not a valid RED.

## Verification

Historical implementation evidence retained from 2026-07-18:

```text
Adjacent Product/Agent/Protocol/HITL suite:
193 passed, 5 skipped

New Task 8 focused suite after review:
26 passed, 5 skipped

Historical official development Server OpenAPI coexistence:
1 passed

Task 8/start/image deployment contracts:
28 passed

Bash syntax, Node syntax, Ruff check, focused Ruff format and git diff check:
passed
```

The five default skips were one explicit live OpenAPI gate and four licensed
persistent tests. The live OpenAPI gate was separately executed against the
development Server; the four licensed tests remain unproved. Those counts
preserve the historical harness review but do not establish Task 8 GREEN,
zero-skip acceptance, a valid root checkpoint event, licensed restart, or
server-effective `durability="exit"`.

Current compatibility evidence supersedes only the stale verdict, not those
historical command results: the development Protocol probe is RED because no
lightweight root checkpoint envelope is delivered. Its official `getState`
fallback is diagnostic only. The isolated `state.fork` validator still observes
`unknown_command`, and neither exception record is accepted.

## Harness Hardening Follow-up

The current working tree now contains a stricter outer harness implementation,
but it has not produced licensed live evidence. The implementation:

- requires an explicit, empty `--evidence-dir` and retains redacted logs,
  JUnit, OpenAPI/version files, Product admission payloads, container
  before/after identities, restart receipt, runtime state manifests and file
  hashes after temporary cleanup;
- binds the target URL to the owned Compose `langgraph-api:8000` published port
  and verifies the Compose labels and built image identity;
- stops the bound container, requires a negative HTTP observation, starts the
  same service, then requires health, URL and Product recovery;
- admits a real Product Task, waits for its official Thread/Run binding, and
  verifies the same Product and Agent identifiers after restart;
- creates separate `durability="sync"` and `durability="exit"` Runs through the
  official Python SDK adapter, records both acknowledged interrupt states, and
  selects explicit post-restart server-effective verification tests;
- validates restart receipts against the Compose service, target outage and
  recovery, verified image digest and locked base image rather than accepting
  only self-declared `licensed/restarted` booleans; and
- makes `--expect-contract-failure` continue through Node, Product admission,
  prepare, stop/start and verify. It succeeds only after an explicit
  `CAPABILITY GAP` and zero-skip live phases.

Fresh non-licensed verification for this hardening is:

```text
Task 8 deployment/static contracts: 14 passed
Agent/Protocol/graph/durability focused suite: 95 passed, 8 skipped
Formal document contracts combined with Task 8 deployment contracts: 32 passed
Complete backend suite: 925 passed, 174 skipped, 1 warning
Root structure/deployment suite: exit 0
Frontend: 30 files / 374 unit tests passed; typecheck, lint and build passed
Ruff check and focused format check: passed after formatting
Bash syntax and git diff check: passed
```

The eight focused skips are one live merged-OpenAPI capability test and seven
licensed Runtime cases. They remain unproved. The current process has neither
`LANGGRAPH_CLOUD_LICENSE_KEY` nor `LANGSMITH_API_KEY`, and the Task 8 Compose
project is occupied by the existing Product PostgreSQL container. The live
licensed harness was therefore not executed and the existing stack was not
stopped. These facts do not change the Task 8 verdict.

The existing local frontend, Agent Server, Agent readiness monitor and Worker
all remained reachable. A read-only Browser/DOM audit covered Work, Home, Runs,
Inbox, Library and Settings at `1280x720` and Pixel 7 `412x915`; it found zero
horizontal overflow, clipped text, duplicate IDs, unnamed visible controls,
raw JSON signals or console warnings/errors. This is current frontend rendering
evidence against the preserved local stack. The no-reload Agent/Worker
processes predate this Task 8 hardening and were not restarted because their
ephemeral model/auth material belongs to the running parent process. Therefore
the browser result is not current-source licensed durability evidence.

## Remaining Gate

The actual licensed `langgraph-api 0.11.0` sequence was not executed. No
persistent Agent container, restart receipt, post-restart checkpoint evidence,
or server-effective `durability="exit"` evidence was produced. Separately, the
development `0.11.1` root `checkpoints` channel must be fixed or upgraded and
pass the live probe without its state fallback.

Task 8 therefore remains `partial`. Hosted OIDC/HTTPS, approved production Web
Search, hosted observability receipts, real notification receipts and release
attestation are separate open gates.

No commit, stage or push was performed.
