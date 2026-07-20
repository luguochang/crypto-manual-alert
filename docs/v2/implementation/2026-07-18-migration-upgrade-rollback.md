# Local Migration Upgrade and Rollback Record

Date: 2026-07-18 Asia/Shanghai
Phase: M6 / migration compatibility and rollback rehearsal
Status: local rehearsal complete; hosted deployment rollback remains open

## Scope

This slice verifies the database migration lifecycle that matters for the
current fork-lineage repair:

```text
upgrade head (0016_repair_fork_scope)
  -> downgrade 0015_observability_delivery
  -> upgrade head (0016_repair_fork_scope)
```

The drill runs against a pinned PostgreSQL 16 Alpine container with temporary
storage and an ephemeral published port. It does not modify the repository or
the developer Product database.

## Implementation

- `tools/v2/upgrade_rollback_drill.sh` validates an empty external output root,
  refuses the `hosted-production` profile, starts the pinned database, runs
  Alembic commands, queries the version table and checks the fork scope
  constraints directly.
- The report is written to a unique `0600` temporary file and atomically moved
  into the output root. It contains only bounded versions, counts, status and
  an explicit `does_not_prove` list.
- `backend/tests/contract/test_upgrade_rollback_runtime.py` covers executable
  mode, Bash syntax, hosted refusal, required migration steps and secret-safe
  output fields.
- `backend/alembic/versions/0016_repair_fork_scope.py` repairs both known
  database states: a stale five-column fork foreign key without the six-column
  unique constraint, and a correctly migrated database that already has that
  unique constraint. Its downgrade preserves the normative six-column scope.

## Verification

The first real drill run retained a genuine RED: `run_alembic` passed the
compound string `upgrade head` as one argument, so Alembic failed after the
temporary database started. The script was corrected to pass action and target
as separate arguments. The fresh rerun is GREEN:

```json
{
  "status": "passed",
  "proof_level": "local-migration-upgrade-rollback-rehearsal",
  "migration": {
    "initial_upgrade": "0016_repair_fork_scope",
    "downgrade_target": "0015_observability_delivery",
    "final_upgrade": "0016_repair_fork_scope",
    "fork_scope_columns": 6,
    "constraint_verified": true
  },
  "secret_scan": {"findings": 0}
}
```

The focused contract suite is `4 passed`. `bash -n`, Ruff and `git diff
--check` passed. The report was `0600`; no connection URL, password or
application secret was printed or persisted.

## Evidence Boundary

This proves local Alembic migration compatibility and the six-column fork
constraint after a rollback round trip. It does not prove production image
rollback, expand/contract behavior across a live multi-instance deployment,
production database failover, zero-downtime traffic draining, backup/PITR,
operator approval or release attestation. V2 remains `PARTIAL` and production
readiness remains `NO`. No commit or push was performed.
