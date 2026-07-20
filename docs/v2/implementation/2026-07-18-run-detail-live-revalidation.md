# Run Detail Navigation and Live Revalidation

> Provenance correction: this historical run used DDGS `backend="auto"`
> metasearch, not a guaranteed DuckDuckGo backend. Provider-identity claims in
> this note are superseded by
> `2026-07-18-readiness-provider-integrity-and-real-regression.md`; URLs,
> citations, timings and the recorded execution sequence remain valid.

Date: 2026-07-18 Asia/Shanghai
Phase: M5 Product interaction consistency
Status: local fixture and zero-mock Product browser gates green; hosted acceptance open

## Problem

The persisted Runs list linked each row directly into the Work surface. This
skipped the dedicated `/runs/[runId]` Product route and made history navigation
ambiguous. The Run detail surface also read an active Run only once, so a page
opened while `queued`, `running` or `waiting_human` could remain stale after the
worker reached a terminal state. Cancellation, Work actions and feedback were
therefore capable of disagreeing with the durable Product projection.

## Implementation

- Run rows now open `/runs/[runId]`; the detail page owns historical Run
  inspection and provides an explicitly Task/Run-scoped link back to Work.
- Active Runs revalidate every five seconds with one request in flight. Hidden
  pages pause the timer and refresh immediately when visible again. A request
  generation fence prevents stale responses from replacing a newer read.
- Background failures keep the last valid Product projection visible and expose
  a manual retry. They are not converted into a terminal or successful state.
- Active Runs expose cancellation. Waiting Human, failed/blocked and all other
  statuses receive status-specific Work action labels.
- Feedback is shown only when a saved feedback receipt already exists or a
  succeeded/blocked Run has an Artifact. A failed or cancelled Run without a
  report cannot collect misleading result feedback.
- `runId` changes remount the stateful detail content through a React key. This
  avoids synchronous effect resets and ensures one Run cannot leak state into
  another Run's route.

## RED and Correction

The first Playwright run retained two failures because the test used a global
`分析中` heading locator while the correct status appeared in both Run metadata
and the Task projection. The locator was scoped to `运行元数据`; no product
assertion was removed. The first complete ESLint run then rejected synchronous
state updates reached from the initial effect. Initial loading was changed to a
direct asynchronous subscription and Run identity now controls remounting.

## Verification

```text
Run detail focused unit tests:                    21 passed
Frontend complete unit suite:                     30 files / 356 tests passed
Frontend typecheck / ESLint / production build:   passed / passed / passed
Frontend route-boundary structure tests:          7 passed
Playwright Runs Desktop + Pixel 7:                 4 passed
git diff --check:                                  passed before documentation
```

The browser test returns `running` on the first real browser fetch and `failed`
on the next fetch. It verifies the initial and terminal labels, Task/Run-scoped
Work URL, cancellation disappearance, feedback suppression and at least two
GETs. Both projects execute axe, viewport overflow and unnamed-control checks,
and attach full-page screenshots to the execution report.

After the implementation gate, the complete local stack was restarted with one
ephemeral in-memory local token: current migrations on Product PostgreSQL,
official `langgraph dev --no-reload` 0.11.0, Product worker and current Next.js.
All four health/page probes returned HTTP 200. Fresh no-route-injection Product
Playwright created separate Desktop and Pixel 7 Tasks and passed both:

```text
Real Product Desktop: 1 passed (1.5m)
Real Product Pixel 7: 1 passed (51.5s)
Combined:             2 passed (2.5m)
```

Both latest Runs persisted as `succeeded` with a final action. The latest detail
rendered one committed Artifact, eight typed DuckDuckGo evidence cards, two
model audit calls and the status-consistent feedback panel. A fresh in-app
browser tab had zero console errors, no `<pre>`, no horizontal overflow and a
properly associated feedback textarea label. Fresh full-page Desktop and Pixel
7 screenshots were visually inspected; they are execution artifacts, not an
approved screenshot baseline.

## Remaining Boundary

The local zero-mock Product mainline is green with explicit
`SEARCH_PROVIDER=duckduckgo`, but this does not approve DuckDuckGo as the ADR
0002 production provider. It is not an approved visual baseline, hosted
multi-user or production durability proof. Licensed persistent Agent Server
restart, approved Web Search, OIDC/HTTPS and M6 release gates remain open. V2 remains `PARTIAL`;
`Production Ready: NO`. No commit or push was performed.
