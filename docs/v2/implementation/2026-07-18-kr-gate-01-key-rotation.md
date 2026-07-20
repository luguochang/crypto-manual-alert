# KR-GATE-01 Key Rotation Record

Date: 2026-07-18 Asia/Shanghai
Phase: M6 / KR-GATE-01
Status: local rehearsal complete; production acceptance remains open

## Objective

Prove that notification credentials and internal JWT verification keys can rotate
with an overlap window, that notification delivery remains usable during the
window, and that a killed credential rewrap process can resume without leaving
old credential versions or publishing sensitive material.

## Implementation

- `backend/src/crypto_alert_v2/notifications/credentials.py` now has a versioned
  decrypt-only keyring. Encryption always uses the active key. Unknown, retired,
  malformed, or AAD-mismatched versions fail closed without returning key,
  plaintext, or ciphertext material. `supports_decryption()` lets Product
  settings distinguish an active overlap from a retired version.
- `backend/src/crypto_alert_v2/api/service.py` allows an existing destination to
  be disabled and re-enabled while its version remains in the decrypt-only
  keyring. It requires re-entry only after that version is retired.
- `backend/src/crypto_alert_v2/config.py` merges internal JWT public keys from
  the configured keyring and public-key file. Same-kid identical material is
  idempotent; conflicting material fails closed. Old and new tokens overlap
  until the old kid is intentionally removed.
- `backend/src/crypto_alert_v2/notifications/rotation.py` rewraps bounded
  batches under `FOR UPDATE SKIP LOCKED` and an `UPDATE ... RETURNING` CAS. A
  concurrent miss is recoverable, completed batches remain committed, and a
  max-batch boundary fails closed rather than claiming retirement.
- `backend/src/crypto_alert_v2/notifications/rotate_credentials.py` writes
  reports through a unique temporary file, `0600` permissions, file and
  directory `fsync`, and atomic `os.replace`.
- `backend/alembic/versions/0016_repair_fork_scope.py` repairs a previously
  applied five-column fork constraint by restoring the six-column unique key
  and foreign key that includes `forked_from_checkpoint_id`. It has a tested
  downgrade path.
- `docker-compose.yml` passes notification decrypt-only keys and JWT overlap
  keys to both `langgraph-api` (the current combined Product API and Agent
  Server process) and `command-worker`. No nonexistent independent
  `product-api` service was invented.
- `tools/v2/key_rotation_drill.sh` creates a pinned, isolated PostgreSQL 16
  target, seeds four tenant-scoped destinations, captures delivery at each
  rotation phase, kills the first rewrap process after a committed batch,
  resumes it, checks JWT overlap/retirement, and performs a secret-safe report
  scan. The drill rejects hosted profile claims.

## Verification

Focused contract/security/unit suite:

```text
64 passed
```

Targeted real local PostgreSQL notification integration:

```text
7 passed
```

Full real PostgreSQL integration after the migration repair:

```text
184 passed
```

The first full integration run also retained a real migration RED: the fork
lineage test could insert a mismatched source checkpoint because the existing
database had an old five-column foreign key. The first repair attempt then
reported the missing six-column unique key, followed by an Alembic revision-id
length error from the database's `varchar(32)` version column. `0016` now
conditionally restores the unique key, uses the bounded revision id
`0016_repair_fork_scope`, and passes a downgrade/upgrade round trip. The final
database constraint was queried directly and contains all six scope columns.

The real Docker/PostgreSQL drill initially produced a genuine RED: the seed
transaction had no ORM relationship between `NotificationDestination` and its
tenant objects, so the database attempted the destination insert before the
referenced tenants. The script now explicitly flushes Tenant/User/Workspace
before adding the destination. The fresh rerun is GREEN:

```json
{
  "status": "passed",
  "proof_level": "local-key-rotation-rehearsal",
  "notification": {
    "total_rows": 4,
    "rows_rewrapped": 4,
    "old_version_rows_remaining": 0,
    "delivery_before_rotation": "delivered",
    "delivery_during_overlap": "delivered",
    "delivery_after_retirement": "delivered",
    "duplicate_deliveries": 0
  },
  "jwt": {
    "overlap_old_token_accepted": true,
    "overlap_new_token_accepted": true,
    "retired_old_token_rejected": true,
    "retired_new_token_accepted": true
  },
  "process_recovery": {
    "interrupted_once": true,
    "resumed_successfully": true
  },
  "secret_scan": {"findings": 0}
}
```

The published report was `0600` and contained no key, canary, plaintext, or
ciphertext. `bash -n` and Ruff lint passed. Compose rendering and deployment
contracts passed with the overlap variables present in both runtime services.
The repair migration was also exercised through `downgrade 0015` and
`upgrade head`; the final version is `0016_repair_fork_scope` and the database
again exposes the six-column fork scope constraint.

## Evidence Boundary

This is a local, pinned-container rehearsal. It proves the application keyring,
database rewrap transaction, Product settings overlap behavior, local adapter
delivery path, JWT verifier overlap, process interruption recovery, and
secret-safe reporting. It does not prove hosted secret-manager custody,
production database password rotation, OIDC client-secret rotation, provider
API-key rotation, a zero-downtime production rollout, hosted Agent Server
durability, or release attestation. Those remain M6 open gates. No commit or
push was performed.
