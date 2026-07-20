# Cancel Stream Teardown

Date: 2026-07-18 Asia/Shanghai
Phase: M5 Product Task lifecycle and official stream ownership
Status: local zero-mock Product browser gate green; hosted acceptance open

## Problem

A fresh current-source `real-cancel` execution reached the durable Product
`cancelled` state on Desktop and Pixel 7, removed the cancel command and showed
the terminal stage history, but both projects failed the requirement that
`official-run-stream` leave the DOM. The retained RED was `2 failed`.

The component eligibility condition was already terminal-aware. Inspection
found that the official `@langchain/react useStream` component and its
Product-owned durable fallback both rendered through `ExecutionProgressPanel`
with the same `data-testid="official-run-stream"`. React had unmounted the live
component correctly; Playwright was finding the terminal durable progress
panel under an incorrect live-stream identity.

## Implementation

- `OfficialRunStream` exclusively owns `data-testid="official-run-stream"`.
- `DurableRunProgress` exclusively owns `data-testid="durable-run-progress"`.
- `shouldAttachOfficialStream` is the single pure eligibility rule used by the
  Work surface. It rejects historical selection, a persisted cancel request,
  missing Task state and every terminal Product status.
- The real cancel profile now requires the official stream to leave the DOM,
  requires durable progress to replace it, and observes a bounded interval
  after cancellation for any new `/api/agent/` reads.
- The profile reloads the cancelled Task and repeats both assertions. A terminal
  recovery must not remount the official stream or issue Agent reads.

No Product or Agent write assertion was weakened. Cancellation still requires
exactly one Product cancel POST and forbids browser-side Run writes.

## Verification

```text
Initial real-cancel RED, Desktop + Pixel 7:          2 failed
Frontend complete unit suite after correction:      30 files / 364 passed
Frontend typecheck:                                  passed
Focused ESLint:                                      passed
Frontend production build:                          passed
First corrected real-cancel Desktop + Pixel 7:       2 passed (22.6s)
Strengthened lifecycle real-cancel Desktop + Pixel:  2 passed (27.8s)
```

Both final projects prove `running -> cancel requested -> cancelled`, exactly
one Product cancellation command, no browser-side official Run write, no 5xx,
no raw JSON block and no horizontal overflow. The official stream is absent at
the terminal boundary; Product durable progress is visible; no new Agent read
starts during the post-terminal observation window or after terminal reload.

## Remaining Boundary

This is a zero-route-injection local Product flow using the current PostgreSQL,
Product Worker and official local development Agent Server. The Agent Server is
still an in-memory development Runtime. This result does not prove licensed
restart durability, hosted OIDC/HTTPS multi-user behavior, approved production
Web Search, or release acceptance. V2 remains `PARTIAL`; `Production Ready: NO`.
No commit or push was performed.
