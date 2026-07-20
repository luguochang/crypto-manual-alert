# 2026-07-18 Upgrade/Rollback Rehearsal

## Result

`tools/v2/upgrade_rollback_drill.sh --profile local-rehearsal` passed against a
temporary PostgreSQL container:

```text
initial upgrade: 0018_progressive_events
downgrade target: 0015_observability_delivery
final upgrade: 0018_progressive_events
domain event base: 0017_domain_events
fork scope constraints: verified
progressive event schema: verified
secret scan findings: 0
```

The drill directly checked the final fork source-checkpoint scope, Domain Event
source identity uniqueness, Thread-scoped event foreign keys, immutable payload
columns and progressive event sequence columns after rollback and re-upgrade.

## Boundary

Proof level is `local-migration-upgrade-rollback-rehearsal` with a dirty source
tree. It does not prove hosted image rollback, production zero-downtime rollout,
production database failover or release attestation. V2 remains `PARTIAL`;
`Production Ready: NO`.

