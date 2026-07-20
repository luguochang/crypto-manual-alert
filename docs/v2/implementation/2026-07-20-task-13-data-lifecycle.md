---
slice_id: task13-data-lifecycle-20260720
phase: Task 13 / local vertical slice
status: local_slice_green_task_partial
authority_class: implementation-note
evidence_boundary: local-development-only
---

# Task 13 Data Lifecycle Vertical Slice

## Objective

Close one complete Product-owned lifecycle path before expanding Task 13 to Memory,
Outcome and the remaining commercial controls:

```text
Settings -> export admission -> durable lifecycle worker -> versioned/hash-verified
bundle -> persisted status -> reload/rejoin

Settings -> user-data deletion admission -> durable worker -> Product DB deletion
-> explicit pending_external systems -> persisted status -> reload/rejoin
```

The slice is intentionally Product-owned. It does not create a second Agent Runtime,
Graph, queue or checkpoint authority.

## Normative Defaults

| Data class | Default policy |
| --- | --- |
| Product Task/Run/Decision/Usage | 365 days |
| Artifact/Evidence | 365 days |
| Completed checkpoint/technical projection | 30 days |
| Application logs | 30 days |
| Online backups | 35 days |
| Raw prompt/response | not stored by default |

The policy is workspace-scoped, actor-readable, and must not be confused with the
future hosted retention settings of LangSmith, Langfuse, Agent Store, or object
storage.

## API Contract

The mounted Product API owns these resources:

- `GET /api/v2/data-lifecycle/policy`
- `PUT /api/v2/data-lifecycle/policy`
- `POST /api/v2/data-lifecycle/exports`
- `GET /api/v2/data-lifecycle/exports/{export_id}`
- `GET /api/v2/data-lifecycle/exports/{export_id}/manifest`
- `GET /api/v2/data-lifecycle/exports/{export_id}/bundle`
- `POST /api/v2/data-lifecycle/deletions`
- `GET /api/v2/data-lifecycle/deletions/{deletion_id}`

Export and deletion admission use the existing `Idempotency-Key` boundary. Every
response is strict typed JSON. Export manifests include a schema version, ordered
section descriptors, row counts and SHA-256 hashes; a bundle is accepted only after
its manifest hash verifies against the stored bundle. Secret-bearing notification
credentials and raw prompts/responses are excluded.

Deletion currently exposes `user_data` as the only admitted scope. The confirmation
string is exact and the operation is owner-scoped. Product-owned rows are processed by
the lifecycle worker. Checkpoint, Store, search-index, LangSmith, Langfuse, log and
backup removal are represented as explicit external system statuses; without a real
adapter and receipt they remain `pending_external`. The API must never report those
systems as deleted merely because the local Product row was removed.

## Verification Gates

- backend strict schemas, permission boundaries, idempotency, manifest tamper detection,
  legal-hold blocking, pending-external truthfulness and lease recovery;
- reversible Alembic migration on an isolated PostgreSQL database;
- unified WorkerRuntime recovery, not a one-off lifecycle process;
- Settings UI with loading, empty, error, queued, success, pending-external and legal-hold
  states;
- zero-route-override Desktop and Pixel 7 Playwright with DOM, axe, overflow, raw-JSON,
  console, request-failure and reload/rejoin assertions.

## Migration Rehearsal Record

The shared development database produced an explicit RED when
`alembic upgrade head` attempted `0022_data_lifecycle`: the lifecycle integration
fixture had already called `Base.metadata.create_all`, so PostgreSQL rejected the
migration with `DuplicateTable` for `data_lifecycle_policies`. The existing lifecycle
tables and indexes were then inspected against migration `0022`; after confirming that
they matched, the shared development database was stamped at `0022_data_lifecycle` to
preserve its existing test data. That stamp records the reconciled local revision; it
is not evidence that Alembic executed the migration on that database.

A separate clean temporary PostgreSQL database completed the `0022` upgrade and
downgrade rehearsal successfully. This GREEN proves the migration is reversible in
that isolated local rehearsal only. Neither the clean-database rehearsal nor the
shared-database stamp is production migration, hosted rollout, backup/restore, or
rollback evidence.

## Evidence Boundary

Passing local tests or a local Product Worker does not prove hosted OIDC/HTTPS,
licensed Agent Server persistence, object-storage durability, checkpoint/Store deletion,
LangSmith/Langfuse deletion receipts, backup propagation, or production release
acceptance. Those remain open in the execution ledger.

## 2026-07-20 Execution Record

### Real local chain

The mounted Product boundary initially returned
`401 resource_token_invalid`: Next preferred the loopback Agent Server token, while the
inner Product API correctly required either its explicit development actor or a scoped
user resource token. The local stack was restarted with the repository's
`development/local-proof` bootstrap and the existing `dev-user` membership context.
Agent `/ok`, Worker `/readyz`, frontend `/settings`, and the lifecycle BFF policy route
then all returned `200`; no auth bypass or client-owned tenant header was added.

The real BFF admitted export `a1bce70d-d750-4119-a89d-d7de1ddd2794` with HTTP `202`.
The unified Worker claimed it once and persisted `succeeded`, released its lease, stored
the manifest and bundle, and left `last_error=null`. Both manifest and bundle reads
returned `200`; each contained 23 actor-scoped record groups, and an independent call to
the lifecycle canonical validator verified the persisted manifest and bundle SHA-256.
The shared development actor had three watchlist records, so this was not an empty
fixture response.

The frontend now persists only the latest export UUID in an owner-UUID-scoped browser
key. Reload reads policy first, then re-fetches the job, manifest and bundle through the
same owner-scoped Product API. An invalid UUID, storage denial, `404`, or actor mismatch
fails closed and clears or ignores the local pointer; bundle data is never stored in
browser storage.

### Browser RED and GREEN

The first isolated production-build Playwright run retained four honest failures:

- Desktop and Pixel 7 failed axe `color-contrast` for three lifecycle panel
  descriptions on `--sd-surface-raised`;
- Desktop and Pixel 7 deletion tests timed out because the decorative switch track
  intercepted the pointer intended for the native switch input.

The text now uses the higher-contrast secondary text token, and the decorative track no
longer participates in hit testing. The tests were not weakened with axe exclusions,
forced clicks, route interception or mocked responses.

The corrected run used a fresh PostgreSQL database migrated from `0001` through
`0022`, an isolated bootstrap tenant/workspace/user, the official development Agent
Server, the unified Worker, and a production Next build. It passed all four cases:

```text
real-data-lifecycle-desktop export/reload       passed
real-data-lifecycle-desktop hold/deletion       passed
real-data-lifecycle-pixel-7 export/reload       passed
real-data-lifecycle-pixel-7 hold/deletion       passed
aggregate                                      4 passed (10.0s)
```

The zero-route-override suite validates strict Zod responses, idempotency headers,
Worker polling, independently recomputed canonical hashes, parsed download equality,
reload/rejoin, UI and API legal-hold blocking, deletion `pending_external`, axe, a
single main landmark, duplicate IDs, accessible names, raw JSON, leaked sentinel text,
overflow, clipping, console/page errors, failed requests and HTTP `5xx`. The receipt is:

`/tmp/crypto-alert-real-lifecycle-e2e-20260720-after-contrast-fix`

It contains JUnit, JSON, HTML, four traces and ten full-page screenshots. The final
isolated database contained two blocked legal-hold jobs and two actual deletion jobs.
Both actual jobs had `product_db=succeeded`, `langsmith=pending_external`, one Worker
attempt and the explicit error `external deletion adapters are not configured`; both
export bundles were scrubbed after Product deletion. The original legal-hold policy was
restored to inactive. Database state was inspected before the isolated stack and
database were removed.

### Regression matrix

```text
backend unit + contract                 975 passed, 1 skipped
isolated PostgreSQL integration         220 passed, 7 skipped
frontend unit                           40 files, 453 passed
frontend lint / typecheck / build       passed
root structure + deployment             passed
backend Ruff / git diff --check         passed
```

The one backend contract skip remains the explicit live Agent Server Protocol probe.
The seven PostgreSQL skips remain licensed persistent Agent Server restart,
authorization and durability capabilities. None are counted as successful evidence.

This closes only the local Product-owned retention/export/deletion vertical slice.
External deletion adapters and receipts, hosted OIDC/HTTPS, licensed restart/replay,
Memory controls, Outcome maturation, complete entitlement/usage reconciliation,
webhooks, PITR/DR/SLO/security and release attestation remain open. Task 13 remains
`partial`; V2 remains `PARTIAL`; `Production Ready: NO`. No files were staged,
committed or pushed.
