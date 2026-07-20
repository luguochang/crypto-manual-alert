# 2026-07-18 Key Rotation Rehearsal

## Result

`tools/v2/key_rotation_drill.sh --profile local-rehearsal` completed against a
temporary PostgreSQL container. The current Product database was not used or
modified.

```text
status: passed
Product migrations: 0001 -> 0018
notification rows: 4
rows rewrapped: 4
old-version rows remaining: 0
delivery before/overlap/after retirement: delivered/delivered/delivered
duplicate deliveries: 0
JWT overlap old/new accepted: true/true
retired old token rejected: true
process interrupted and resumed: true/true
secret scan findings: 0
```

The drill covers versioned decrypt-only overlap keys, bounded CAS rewrap,
resumption after a killed process, internal JWT key overlap and retirement, and
notification idempotency.

## Boundary

Proof level is `local-key-rotation-rehearsal` with a dirty source tree. It does
not prove hosted secret-manager custody, database password rotation, OIDC
client-secret rotation, provider API-key rotation, production zero-downtime
rollout or release attestation. V2 remains `PARTIAL`; `Production Ready: NO`.

