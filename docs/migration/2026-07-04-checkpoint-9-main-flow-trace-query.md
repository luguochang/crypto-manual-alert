# Checkpoint 9 Main Flow Trace And Query Closure

Date: 2026-07-04

Scope:

- `RunExecutor` now requires every decision step to return an explicit `trace_id`; empty trace ids fail fast instead of falling back to recent trace lookup.
- `query_text` is documented and projected as `audit_note`: it is retained for operator audit context and does not drive LeadPlan, worker selection, tool budget, facts requirements, or final input.
- `controlled_shadow` is persisted as audit-only with trace finish, plan_run binding, API projection, frontend projection, and eval/case-builder readback.
- Formal docs 29/30/31 now describe the current worker owner model as 7 required shadow workers under `market_agents/`, with `agent_swarm/local_workers/` kept as compatibility re-export only.
- New/changed structure guards require `query_semantics` and `audit_note` to exist across producer projection, frontend schema/page, and runtime smoke checks.

Artifact guard:

Any new sidecar/artifact must ship the full chain before merge:

```text
producer -> persistence -> API projection -> frontend view -> runtime smoke assertion
```

It must also document raw/secret/redaction/ref/hash strategy.
