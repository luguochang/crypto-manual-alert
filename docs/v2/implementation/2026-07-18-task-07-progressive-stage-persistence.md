# Task 7 Official Stream Progressive Persistence Record

Date: 2026-07-18 Asia/Shanghai
Phase: Task 7 / official Run stream and progressive Product persistence
Status: local official-stream slice complete; licensed hosted durability open

## Objective

Persist paid market, research, analysis, Evidence Verdict and Risk Verdict
stages as they complete, before the terminal Product transaction. The source
must be the official `langgraph-sdk==0.4.2` Run stream. Product PostgreSQL must
own the durable projection, cursor and immutable payload; the implementation
must not create a private SSE protocol, second Graph, second checkpointer or
second worker runtime.

## Architecture Audit

Three parallel read-only audits inspected the installed SDK, the existing
Product/Agent boundary and the `0017` ledger. They confirmed:

- `RunsClient.join_stream(thread_id, run_id, ..., last_event_id=...)` returns
  official v1 `StreamPart(event, data, id)` values and is an async iterator,
  not an awaitable result;
- resumability must be enabled when each submit, resume or fork Run is created;
- `updates` is the correct mode because `values` on a fork can contain inherited
  checkpoint state that was not newly completed by the fork Run;
- the Product command loop must drain a bounded stream slice and then retain the
  existing `get/get_interrupts/join/cancel` authority paths;
- `(run_id, event_type)` and `MAX(sequence)+1` in `0017` were unsafe for node
  retries, conflicting replays and concurrent Runs sharing one Thread.

## RED Sequence

The first focused run failed during collection because
`progressive_event_specs` did not exist. After the first implementation, the
focused matrix retained three concrete failures: resume Run creation lacked
resumable stream options, the JSONB schema contract omitted immutable event
payloads, and the migration drill still ended at `0017`.

The first complete fresh PostgreSQL integration run after stream integration
was `185 passed, 2 failed`. Both failures were real protocol-harness gaps: the
process-recovery Fake Agent Server returned 404 for the official
`GET /threads/{thread}/runs/{run}/stream` endpoint. The harness was extended to
serve a valid SSE `end` event; both SIGKILL scenarios then passed.

The first real Desktop browser run exposed a more important runtime gap.
Although the official Run was created with `stream_resumable=true`, the initial
0.5-second live subscription ended before the queued Run emitted its market
update. A later subscription with no `Last-Event-ID` did not replay that event,
so Product stored only terminal-reconstructed events. Directly calling the
official endpoint with `last_event_id="0"` replayed four persisted update
events with official IDs. The adapter now uses the official start cursor `0`
when Product has no committed cursor and uses the exact persisted event ID on
subsequent connections.

The next real Desktop run produced a second RED: the progressive market model
dump retained nested null fields while the terminal DTO recursively excluded
them. The semantically identical market snapshot therefore had two hashes and
two events. Progressive Pydantic serialization now uses
`exclude_none=True`, matching the terminal DTO; a contract test locks that
normalization.

## Implementation

- Submit, resume and fork `runs.create` calls explicitly set
  `stream_mode=["updates"]` and `stream_resumable=True`.
- `AgentServerRunner.join_stream` is a thin official SDK adapter. It fixes
  `cancel_on_disconnect=False`, forwards authorization, sends Product's last
  committed event ID, and uses `0` only for the first replay from the start.
- `CommandDispatcher` drains at most 64 official events or 0.5 seconds per
  command lease. It then returns to the existing polling/HITL/cancel path, so
  an idle stream cannot monopolize the only command loop.
- Every update is allowlisted by canonical node name and validated with the
  existing Pydantic domain models. Request state, runtime objects, messages,
  credentials and unknown node payloads are never persisted.
- A stage payload, Domain Event and `official_stream_last_event_id` commit in
  the same fenced Product transaction. A crash cannot advance the cursor
  without its payload or commit a payload without the matching cursor.
- Alembic `0018_progressive_events` adds the Run cursor/timestamp, immutable
  event payload and source identity, and a Thread-local atomic sequence
  counter. Domain Event scope now includes `thread_id` in the Run foreign key.
- Idempotency uses a stable source-event key. Same source and same hash is a
  no-op; same source and different hash raises
  `DomainEventProjectionConflict`. A later source event may append a new
  version of the same event type.
- Thread sequence ranges use one atomic `UPDATE ... RETURNING`, removing the
  `MAX(sequence)+1` race across different Runs.
- ArtifactVersion, Decision, notification planning and `run.terminal` remain
  in the existing terminal Product transaction. HITL still uses the complete
  official root/nested checkpoint inspection path.

## Verification

```text
official adapter/schema/migration focused:       104 passed
real PostgreSQL dispatcher regression:            68 passed
real worker SIGKILL recovery after contention:      2 passed
fresh isolated PostgreSQL integration:            187 passed
backend hermetic current worktree:                  809 passed, 160 skipped
root structure/deployment/tooling:                 227 passed
frontend unit:                          29 files / 319 tests passed
frontend typecheck, lint, production build:         passed
focused Ruff format/lint and diff check:             passed
```

The real migration drill passed:

```text
0018_progressive_events
  -> 0015_observability_delivery
  -> 0018_progressive_events
```

It directly verified the source-key uniqueness, immutable payload columns,
Thread-inclusive Run scope and Thread sequence counter and reported zero secret
findings.

Real local official-runtime/browser evidence:

- official `langgraph dev` logged `stream_mode=['updates']`,
  `stream_resumable=True` and `resumable=True` for the created Run;
- a Desktop failure after successful market and research but invalid model
  Structured Output retained exactly market, research and terminal events;
  both paid-stage events had official source IDs and the Run cursor was set;
- a fresh Pixel 7 zero-mock Product flow passed in `1.4m`, including real OKX,
  Web Search, model Structured Output, Product API, PostgreSQL, worker,
  official Agent Server, DOM, accessibility, network and responsive checks;
- direct PostgreSQL verification of that successful Run found exactly seven
  ordered events. The first five market/research/analysis/evidence/risk events
  had official stream event IDs; artifact and terminal were committed by the
  Product terminal transaction. There were no duplicate stage event types.

Three Desktop provider/model failures remain retained evidence rather than
being retried until hidden: two Web Search citation/timeout failures and one
invalid Structured Output failure. Their UI failed closed with a user-facing
diagnosis and no success Artifact.

## Evidence Boundary

This proves progressive persistence with the installed official SDK and local
official development Runtime, including a real successful mobile Product flow,
a real later-stage failure, cursor replay, immutable payload conflict,
two-connection Thread ordering and controlled worker SIGKILL recovery. It does
not prove that a licensed persistent Agent Server preserves stream history and
checkpoints across an Agent Server process or database restart. It also does
not prove hosted OIDC/HTTPS, hosted SLO/alerting, production database failover
or release attestation. Those gates remain open. V2 remains `PARTIAL`;
`Production Ready: NO`. No commit or push was performed.
