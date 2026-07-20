# Compose BFF Bootstrap Authorization

Date: 2026-07-18

Phase: `G0.2` / Compose-style service-to-service mainline

## Finding

The local loopback stack and the Compose DNS topology did not exercise the same
authorization boundary. In Compose, the frontend calls the official Agent
Server Product app through `langgraph-api:8000`, while the frontend is a
development BFF without a browser session.

Two defects were found:

1. Product BFF attempted a scoped `token_use=user` token before checking
   `/api/v2/auth/contexts` and `/api/v2/auth/context/select`. Those routes
   require an identity discovery token.
2. Agent BFF imported `isDevelopmentBootstrapRuntime` from the runtime module,
   although that function is owned by the BFF auth module. The exception was
   caught by the transport boundary and surfaced as an opaque 502 when a
   complete non-loopback bootstrap configuration was first exercised.

The one-shot backend bootstrap also used a legacy ActorContext constructor,
which could seed a different identity issuer and no fixed context ID than the
production Product app used at runtime.

## Changes

- Added a server-owned, local-proof-only identity discovery token issuer in the
  frontend BFF auth boundary.
- Made Product BFF choose identity discovery authority for context discovery and
  selection before considering scoped resource authority.
- Kept ordinary Product and Agent routes on the scoped user token and the Agent
  audience.
- Restricted non-authenticated local Agent URLs to HTTP and retained loopback
  protection unless the complete development bootstrap signing configuration is
  present.
- Corrected the Agent BFF import so complete Compose bootstrap configuration is
  executable rather than hidden behind a generic 502.
- Changed the backend one-shot bootstrap to reuse
  `configured_development_actor`, including the configured identity issuer and
  context ID. This makes database membership seeding and runtime token scope
  use the same ActorContext contract.
- Added frontend JWT claim, BFF routing, non-loopback Agent, environment
  isolation, and Compose deployment contract coverage.

## Verification

- Frontend focused and full unit tests: `372 passed` in `30` files.
- Frontend typecheck: passed.
- Frontend ESLint: passed.
- Frontend production build: passed.
- Backend auth and deployment contracts: `41 passed`.
- Compose deployment contracts: passed.
- Complete backend hermetic suite: `850 passed, 164 skipped, 1 warning`.
- Ruff lint passed; all `179` backend files passed the format check.
- Current-source local runtime returned HTTP 200 for frontend Work, Product
  readiness, Agent docs, Worker liveness, and Worker readiness.
- Product BFF returned one authorization context with the configured fixed
  context ID; the same membership ID exists in PostgreSQL `app.memberships`.
- Live Playwright Desktop and Pixel 7 scans returned HTTP 200 with zero page
  errors, failed requests, raw `pre` blocks, unnamed controls, horizontal
  overflow, and axe violations. Both screenshots were manually inspected.
- The real-provider Desktop and Pixel 7 success-only tests were intentionally
  retained as RED. Both crossed Product API, PostgreSQL, Worker, official
  LangGraph development Runtime, and the real UI, then failed after three
  `builtin_web_search` `APITimeoutError` attempts at
  `collect_market_snapshot`. No Artifact or uncited market value was accepted.

## Boundary

This closes the local Compose-style BFF authorization defect. It does not close
the production release gate. The approved built-in Web Search provider still
fails at `collect_market_snapshot` after its bounded retries, and licensed
persistent Agent Server restart durability, hosted OIDC/HTTPS, external
notification receipts, and release-source proof remain open.

No commit, stage, or push was performed.
