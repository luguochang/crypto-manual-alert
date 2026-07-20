# Task 7 Product Stage History Recovery Record

Date: 2026-07-18 Asia/Shanghai
Phase: Task 7 / durable Product progress recovery
Status: Product API and frontend recovery implementation complete; fresh real
running-reload browser execution open

## Objective

The official `@langchain/react` stream remains the live execution source, but
it cannot be the only UI memory. Refresh, SSE disconnect, terminal state and a
selected historical Run must reconstruct completed stages from Product
PostgreSQL without exposing Domain Event payloads or creating another stream
protocol.

## Retained RED Evidence

Two read-only audits found that progressive Domain Events were durable while
`TaskView` had no stage history or cursor. The Work surface rendered progress
only from the in-memory official stream and hid the component at terminal.
Backend TDD retained `3 failed, 7 passed` before the DTO/repository projection
existed.

The real official-stream browser spec previously reloaded only after terminal.
It could not prove a running Task retained completed stages. The revised test
now fails if the Run reaches terminal before a nonterminal persisted stage is
captured; it cannot silently substitute the old terminal-only reload.

## Product Contract

`TaskView.stage_history` targets the explicit selected Run or latest-attempt
Run and contains only:

- `run_id` for contract correlation, never rendered in the interface;
- ordered `sequence`, stage name, status, timestamp and safe source class;
- the last Product Domain Event sequence;
- a paired opaque official stream cursor and cursor timestamp.

Allowed stages are market snapshot, Web Evidence, analysis, Evidence Verdict,
Risk Verdict, Artifact, notification and terminal Run. Sources are only
`official_stream` or `product_projection`.

The repository query is bound to tenant, workspace, owner, Task and Run and
selects only event type, sequence, created time and whether an official source
event ID exists. It never selects Domain Event payload/ref/hash, checkpoint,
source key/event ID, model content, authorization or provider response.
Sequence uniqueness/order, Product cursor equality and paired official cursor
fields are validated on both Python and TypeScript boundaries.

## Frontend Recovery

- Product history is the durable baseline; official `useStream` values remain
  the live enhancement. No private SSE client was added.
- Multiple versions of one stage collapse to the greatest Product sequence and
  render in canonical stage order.
- A durable committed/terminal stage cannot be regressed by stale live active,
  warning or failure values. A same-tone live value may enrich the human detail.
- Before live stream attachment, after SSE failure, at terminal and for a
  selected historical Run, the saved Product stages remain visible.
- The UI does not render Product Run ID, Product cursor or official cursor.
- The real official-stream spec now reloads after a persisted stage while the
  Product status is nonterminal, requires the same Task and complete stream
  binding, requires all earlier stages after reload and forbids a second
  analysis POST. It then retains the terminal reload proof.

## Verification

```text
backend stage contract RED:                    3 failed, 7 passed
Product focused contracts:                    138 passed
Product + persistence contracts:              194 passed
real PostgreSQL Product service:               34 passed
real PostgreSQL Product service + dispatcher: 105 passed
backend hermetic current worktree:             835 passed, 164 skipped, 1 warning
frontend focused schema/merge/Work tests:      112 passed
frontend full current worktree:                29 files / 335 tests passed
frontend typecheck and lint:                   passed
official stream Playwright discovery:          2 tests / Desktop and Pixel 7
```

After a coordinated current-code restart, the live local Product API returned
the retained real failed Task's three database events as:

```text
1 market_snapshot committed official_stream
2 web_evidence    committed official_stream
3 run             failed    product_projection
```

The API Product cursor was `3` and matched the last stage. The actual opaque
official cursor was present and paired, but is intentionally omitted from this
record and the user interface.

## Evidence Boundary

The backend real PostgreSQL contract, current shared-stack API projection and
frontend unit/type/static gates are fresh. The in-app browser rejected the
post-restart reload under its URL security policy; no alternate browser/CDP
workaround was used. Therefore the new real running-stage reload Playwright
body remains **not executed** in this slice and is not claimed as browser
acceptance. Licensed persistent Agent Server restart, hosted stream durability,
OIDC/HTTPS and production SLO evidence also remain open. V2 remains `PARTIAL`;
`Production Ready: NO`. No commit or push was performed.
