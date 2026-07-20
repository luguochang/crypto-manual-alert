# G0.3 Single Graph and Worker Entry

Date: 2026-07-18 Asia/Shanghai
Phase: G0.3 official framework boundary convergence
Status: local source/runtime boundary green; licensed durability remains open

## Problem

The official Agent Server already registered only `graph_factory`, but the
production Python package also compiled and exported a module-level `graph` at
import time. That object was not used by `langgraph.json`, yet it remained a
second directly executable Graph surface. The deployed process used
`python -m crypto_alert_v2.workers`, while `commands/worker.py` still contained
a second complete command-dispatch loop and `__main__` entry.

Both surfaces made the open-source production boundary harder to audit even
though Compose did not call them.

## Implementation

- `crypto_alert_v2.graph` now exports only `create_graph` and `graph_factory`.
  The production module no longer calls `create_graph()` at import time.
- Tests that need an in-process Graph explicitly call `create_graph()`. This
  remains a test harness and cannot be mistaken for the deployed registration.
- `commands/worker.py` was removed. Agent Server local-token/internal-JWT
  assembly moved to the non-executable `auth/worker_authorization.py` module.
- `workers/__main__.py` consumes that public authorization factory and remains
  the only Worker process entry. Command, projection, Domain Event,
  notification and observability loops still run under its existing
  `WorkerRuntime`; no business behavior was removed.
- Canonical boundary contracts now fail if a module-level compiled Graph or the
  old Worker file returns.

`AgentServerRunner` was deliberately not deleted in this slice. It contains
official SDK calls plus Product-owned idempotency, tenant metadata and
indeterminate-create reconciliation. Each concern needs replacement evidence
before code removal; deleting the adapter wholesale would weaken production
reliability rather than increase framework compliance.

## Verification

```text
Canonical Graph/Worker/security focused: 42 passed
Projection worker assembly focused:       1 passed
Deployment and route structures:          30 passed
Backend complete hermetic suite:           836 passed, 164 skipped, 1 warning
Ruff focused code check:                   passed
Formal documentation tests:               18 passed
git diff --check:                          passed
```

The complete local topology was then stopped and restarted from current source
with one new ephemeral token. Official `langgraph dev --no-reload` 0.11.0
loaded `graph/__init__.py:graph_factory`; Product Worker started with
`python -m crypto_alert_v2.workers`; Work, Runs, Product health and Agent docs
all returned HTTP 200. Runtime import inspection reported:

```text
legacy_worker_spec None
graph_exports ['create_graph', 'graph_factory']
factory_callable True
```

## Remaining Boundary

The running Agent Server explicitly remains the in-memory development Runtime.
This proves current-source loading, not licensed persistent restart or hosted
durability. The root V1 package cannot be deleted until the required parity and
data migration/zero-data attestations exist. The SDK adapter decomposition,
approved production Web Search, hosted OIDC/HTTPS and M6 release proof remain
open. V2 remains `PARTIAL`; `Production Ready: NO`. No commit or push was
performed.
