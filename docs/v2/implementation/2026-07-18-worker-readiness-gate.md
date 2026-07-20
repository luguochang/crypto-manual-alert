# Worker Readiness Gate

Date: 2026-07-18 (Asia/Shanghai)

Phase: `M5/M6` mainline operational reliability

## Change

- `WorkerRuntime` now exposes standard-library HTTP probes at `/livez`, `/readyz`
  and `/healthz` when configured.
- Consecutive durable-loop failures still move Worker readiness to false; a
  successful iteration restores readiness. Shutdown closes the health listener
  before lease release completes.
- Product exposes `/api/v2/readiness` separately from the liveness-only
  `/api/v2/health`. Production/staging fail closed when the Product database check
  or Worker readiness URL is absent/unhealthy; local profiles retain the existing
  development behavior.
- Compose starts the frontend only after `command-worker` is `service_healthy`,
  and the frontend healthcheck now calls Product readiness instead of liveness.

## Verification

- Worker health-server lifecycle contract passed.
- Deployment topology and Compose healthcheck contracts passed.
- Full backend suite: `850 passed, 164 skipped, 1 warning`.
- Frontend unit suite: `368 passed` in `30 files`.
- Frontend typecheck and lint passed; Ruff passed.
- Current local stack after source restart returned Worker `/livez=200`,
  `/readyz=200`, frontend `200`, Agent docs `200`, and frontend BFF Product
  readiness `200`.

## Boundary

This closes the false-health/start-order gap for the local and Compose topology.
It does not prove a licensed persistent Agent Runtime, hosted OIDC/HTTPS,
production failover, or the current real Web Search success gate. The Product
mainline remains fail-closed when external market/search dependencies are
unavailable.
