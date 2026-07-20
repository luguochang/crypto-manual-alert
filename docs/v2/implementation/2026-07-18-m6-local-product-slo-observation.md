# M6 Local Product SLO Observation

Date: 2026-07-18 Asia/Shanghai
Phase: M6 / Product-flow measurement foundation
Status: local Product database proxy observation complete; formal SLO open

## Decision

Two independent read-only audits reviewed ADR 0006, the 12-metric evaluator,
Product PostgreSQL timestamps and Domain Events. Their strict conclusion is
that Product PostgreSQL alone can recompute `0/12` formal ADR 0006 SLOs.

The database can produce useful server/storage proxy values, but it does not
contain edge request/ack timestamps, browser-render timestamps, stream
delivery attempts, reconnect attempts, normalized Structured Output attempts,
claim-to-Evidence relations, recovery attempts, hosted security observations
or live secret-scan findings. Those gaps are not filled with zeroes.

## RED

The first focused collection failed during test import:

```text
ModuleNotFoundError:
No module named 'crypto_alert_v2.evaluation.product_slo_observation'
```

The audit also found two pre-existing false-confidence paths in
`tools/v2/run_slo_probe.py`:

- caller-supplied `measurement_source=local-observed` values could pass without
  a database snapshot, query hash or sample provenance;
- the report hard-coded `secret_scan.findings=0` although no scanner ran, and
  availability without a threshold was emitted as `passed=true`.

## Implementation

- Added `crypto_alert_v2.evaluation.product_slo_observation` and the thin
  `tools/v2/collect_local_product_slo.py` CLI.
- The collector requires an explicit tenant plus workspace scope and a UTC
  half-open Task window. It selects initial Runs only; retry, resume and fork
  lineages are not silently mixed into the cohort.
- PostgreSQL collection runs in one `REPEATABLE READ, READ ONLY` transaction
  with a statement timeout. The three reviewed queries carry tenant/workspace
  predicates and read no payload, content, URL, decision, risk-verdict,
  provider-trace or failure-message columns.
- Output contains no raw actor/task/run IDs. It records a cohort SHA-256,
  database snapshot SHA-256, migration revision, query hashes, sample/missing/
  censored/invalid counts and machine-readable limitations.
- Reports are written with owner-only `0600`, fsync and atomic replacement.
  CLI failures emit only an error type and never the database URL or exception
  message.
- The 12 official metric keys are all present, but each is explicitly
  `proxy` or `unavailable`; `formal_slo_coverage` is fixed at `0/12`, and the
  report has no `passed` field.
- `run_slo_probe.py` now accepts only its deterministic
  `synthetic-contract` source. Unbound `local-observed` manifests fail closed,
  the fake secret-scan result was removed, and no-threshold availability now
  has `passed=null`.

## Fresh Verification

```text
Focused collector/evaluator contracts: 10 passed
Complete backend performance group:     14 passed
Focused Ruff lint/format:                passed
```

The real collector ran against the local `0018_progressive_events` Product
database over the settled UTC window `[04:00, 04:45)`. The cohort was explicitly
classified as local, unknown/mixed traffic on a dirty working tree:

```text
initial Runs:                         4
Product status:                       1 succeeded, 3 failed
formal ADR 0006 SLO measured:         0/12
first persisted stage p95 proxy:      36,986.381 ms (4/4)
first persisted agent output proxy:   78,056.762 ms (1/4; 3 missing)
Run execution max proxy:              90,224.340 ms (4/4)
persisted duplicate proxy:            0/15 events
successful projection-chain proxy:    1/1
```

The successful projection diagnostic means exactly one committed
ArtifactVersion, one Decision and at least one normalized WebEvidence row. It
does not prove allowed claim-level Evidence completeness. Likewise, the
persisted duplicate value does not measure consumer delivery duplication.

The owner-only report is staged outside the repository at:

```text
/Users/chase/Documents/面试/.v2-evidence-staging/
1432b30664adca638a23362a3a0ff681b2de4c17c4db1258d42ecb5b641b6137/
local-product-slo-observation.json
```

Report SHA-256:
`1432b30664adca638a23362a3a0ff681b2de4c17c4db1258d42ecb5b641b6137`.
The report mode is `0600`; the sensitive-pattern scan found no database URL,
raw scope IDs, source URL, failure message, authorization value or API-key
pattern.

## Open Production Work

This slice does not prove hosted availability, request confirmation, browser
visibility, reconnect quality, end-consumer event duplication, Structured
Output success, allowed Evidence completeness, checkpoint recovery,
cross-tenant isolation, secret-leak absence, alerts or release acceptance.

The next SLO implementation must add source-of-truth measurement events at the
actual boundaries instead of inferring them from Product projections:

- edge request-received and durable ack timestamps;
- frontend stable-event receive and rendered timestamps;
- stream delivery/reconnect attempt identities and outcomes;
- normalized structured-operation and recovery-attempt ledgers;
- immutable claim-to-Evidence relations;
- hosted monitor/security/secret-scan evidence with release identity.

V2 remains `PARTIAL`; `Production Ready: NO`. No commit or push was performed.
