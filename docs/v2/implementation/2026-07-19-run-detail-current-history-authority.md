# Run Detail Current and Historical Authority

Date: 2026-07-19 Asia/Shanghai
Phase: M2/M5 Product API and rendered main-flow consistency
Status: local implementation and current-source browser proof green; production gates open

## Problem

A real persisted Task exposed a resolved first-attempt Run with this response shape:

```text
run.status              = waiting_human
task.status             = waiting_human
task.pending_interrupts = null
```

The Run status was correct and immutable. The nested Task was not a coherent current
Task: its pause had been resolved by a later successful resume Run. The frontend
correctly rejected the response as an invalid Run detail. The same historical status
also made the page poll forever, advertise cancellation for a superseded attempt and
label the Work action as an active review.

## Contract Correction

Run Detail now separates the two authorities instead of overloading one `task` field:

```text
run             immutable summary of the requested execution attempt
task            current Task projection and current action authority
run_projection  evidence, report, errors and stages scoped to the requested Run
is_current_run  server-owned indication that the requested Run is the latest attempt
```

`TaskView.projection_scope` distinguishes `latest` from `selected_run`. A current
`waiting_human` Task still requires an active pending/responding pause. A selected
historical Run projection may preserve an immutable `waiting_human` boundary after its
pause has resolved, but it must carry the selected Product Run ID. Run Detail validates
that both projections belong to the same Task and that the selected projection matches
the requested Run.

The Product UI uses current Task authority for polling, cancellation and review
navigation, while rendering the selected Run projection. A resolved historical review:

- keeps the Run heading `等待人工确认` without rewriting history;
- discloses that a later Run handled the review;
- renders the selected content state as `历史审核节点`;
- hides cancellation and stops polling after the current Task becomes terminal;
- links to the current Task as `查看任务最新状态`;
- never synthesizes an active pause or exposes raw JSON.

## RED and GREEN

RED was reproduced against the persisted first-attempt Run. Its Product API response
was HTTP 200 but failed the strict frontend Run Detail schema. The first visual GREEN
then failed axe `color-contrast` on both Desktop and Pixel 7. The warning text was moved
to the established high-contrast warning token; axe was not disabled or relaxed.

Fresh local evidence after correction:

```text
Backend full:                         936 passed, 174 skipped, 1 warning
Backend focused API/projection:       181 passed
Real PostgreSQL lifecycle regression: 1 passed
Frontend unit:                        32 files / 397 tests passed
Frontend typecheck / lint / build:    passed / passed / passed
Run Detail Playwright:                6 passed (Desktop + Pixel 7)
Ruff check:                           passed
```

The real PostgreSQL regression covers the waiting Run, accepted response, created
resume Run, resolved pause, later terminal Task and old Run Detail schema validation.
All 174 default skips remain unproved.

## Current-Source Browser Proof

The preserved `8123/9090/9091/3001` stack was not restarted because its parent owns
ephemeral provider and signing material. A separate current-source Agent Server was
therefore started on `8124` with an explicit local development profile and a separate
frontend copy on `3002`. It reused Product PostgreSQL only for read verification.

The known historical Run returned:

```text
HTTP 200
run.status              = waiting_human
task.status             = succeeded
task.pending_interrupts = null
run_projection.status   = waiting_human
is_current_run          = false
```

The real BFF-rendered Run Detail passed Desktop `1280x720` and Pixel 7 `412x915` DOM
scans with zero horizontal overflow, duplicate IDs, unnamed controls, clipped text,
raw JSON signals or current-page console warnings/errors. It had no cancellation
button and exactly one current-Task link. Following that link loaded the persisted
successful Task with seven durable stages, eight Web Evidence cards, the expired but
readable analysis, source provenance and two model-call audit records. The mobile Work
scan again had zero overflow, duplicate IDs, unnamed controls, `<pre>` blocks, raw JSON
signals or current-page console warnings/errors.

An isolated production-mode startup using deliberately invalid placeholder model
credentials failed closed on missing `tool_calling`, `structured_output`, `streaming`
and `usage_reporting` capabilities. The later `8124/3002` proof is explicitly local
development evidence and does not replace that production gate.

## Remaining Boundary

This closes one Product API/UI consistency defect. It does not close approved built-in
Web Search, licensed Agent Server persistence/restart, hosted OIDC/HTTPS, hosted
LangSmith/Langfuse traces, real notification receipts, Deep Research integration,
production recovery/SLO/security or release attestation. V2 remains `PARTIAL` and
`Production Ready: NO`.

No code was staged, committed or pushed.
