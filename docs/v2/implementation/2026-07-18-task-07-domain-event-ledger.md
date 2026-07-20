# Task 7 Domain Event Ledger Foundation Record

Date: 2026-07-18 Asia/Shanghai
Phase: Task 7 / Product persistence and recovery foundation
Status: terminal projection complete; progressive stage persistence open

## Objective

Add a durable, tenant-scoped Product Domain Event ledger for the eight event
types required by Task 7. The ledger must be idempotent, ordered within a
Thread, recoverable after a terminal projection gap, and remain subordinate to
the official LangGraph Run/checkpoint identity. This slice deliberately does
not introduce a second graph, checkpointer, runtime, SSE endpoint, or private
Agent event protocol.

## RED

The first focused contract run failed during collection because
`DomainEvent` and `domain_event_specs` did not exist. Subsequent focused REDs
exposed SQLAlchemy table-constraint assertion mismatches and missing worker
assembly behavior. Those failures were corrected in the schema and worker
contract; no assertion was removed or weakened to obtain GREEN.

A first complete real PostgreSQL integration run against the existing,
long-lived Product database produced:

```text
179 passed, 5 failed
```

The five failures came from pre-existing user/local rows: tests that asserted a
global Outbox count of `0` or `1` observed `14` or `15`, and old notification
credential versions changed global rewrap counts. The database was not
deleted, reset, or modified to conceal that contamination. A separate fresh
PostgreSQL 16 container was migrated from zero and used for isolated evidence.

## Implementation

- Alembic revision `0017_domain_events` creates `app.domain_events` after the
  `0016_repair_fork_scope` repair.
- Every row carries tenant, workspace, owner, Task, Run and Thread scope, an
  optional official Run/checkpoint identity, schema version, payload reference,
  deterministic SHA-256 payload hash, Thread-global sequence and timestamp.
- Unique `(run_id, event_type)` makes the current eight terminal projections
  idempotent. Unique `(thread_id, sequence)` provides Thread-global ordering.
- Composite foreign keys keep every event inside the owning Task/Run scope;
  checks reject unsupported event types and non-positive sequence values.
- `append_domain_events` derives the exact terminal event set from committed
  Product rows and appends only missing event types in the caller's existing
  transaction.
- Successful Runs without a notification append seven events. Successful Runs
  with a planned notification append all eight required event types.
- `DomainEventProjectionWorker` locks terminal Runs with
  `FOR UPDATE SKIP LOCKED` and repairs Runs missing `run.terminal`. Existing
  uniqueness constraints make worker retries idempotent.
- The worker is registered in the existing `python -m crypto_alert_v2.workers`
  process. No second worker entrypoint or persistence authority was added.

## Files

- `backend/alembic/versions/0017_domain_events.py`
- `backend/src/crypto_alert_v2/persistence/models.py`
- `backend/src/crypto_alert_v2/persistence/__init__.py`
- `backend/src/crypto_alert_v2/projections/domain_events.py`
- `backend/src/crypto_alert_v2/commands/dispatcher.py`
- `backend/src/crypto_alert_v2/workers/__main__.py`
- `backend/tests/contract/test_domain_event_contract.py`
- `backend/tests/contract/test_persistence_schema.py`
- `backend/tests/contract/test_projection_reconciler_runtime.py`
- `backend/tests/contract/test_upgrade_rollback_runtime.py`
- `backend/tests/integration/test_command_dispatcher.py`
- `tools/v2/upgrade_rollback_drill.sh`

## Verification

```text
focused contract groups:                  72 passed; 67 passed
fresh isolated PostgreSQL integration:   184 passed
backend hermetic suite:                  805 passed, 157 skipped, 1 warning
root structure/deployment suite:         153 passed
focused Ruff lint/format:                passed (11 files)
git diff --check:                        passed
```

The isolated database was migrated from zero to `0017_domain_events` and was
removed after the run. The existing Product database and all of its rows were
preserved.

The real migration drill completed:

```text
0017_domain_events
  -> 0015_observability_delivery
  -> 0017_domain_events
```

It directly reverified the six-column fork foreign-key and unique constraints,
reported `secret findings=0`, and retained proof level
`local-migration-upgrade-rollback-rehearsal`.

## Evidence Boundary

This is a durable **terminal** Domain Event projection and crash-repair
foundation. It does not yet persist paid stages as they complete. If a Run
fails before the existing terminal transaction, successful market, research,
agent, evidence or risk stages are not yet guaranteed to remain queryable in
Product PostgreSQL.

The next implementation slice must consume supported official
`langgraph-sdk` Run stream channels and commit each completed stage through
this ledger with official Run/checkpoint identity and resumable deduplication.
The terminal worker remains recovery, not the primary progressive writer. A
licensed persistent Agent Server restart and hosted SLO evidence are still
required for production acceptance. V2 remains `PARTIAL`; `Production Ready:
NO`. No commit or push was performed.
