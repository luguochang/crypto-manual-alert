# Playwright Profile Discovery Gate Record

Date: 2026-07-18 Asia/Shanghai
Phase: M5/M6 browser test discovery and admission
Status: local discovery gate complete; real profile execution is tracked separately

## Objective

Every browser acceptance command must collect exactly the spec and projects it
claims to execute. Default fixture tests must not silently include real-provider
or failure-injection suites, and a real profile missing its environment gate
must fail before collection instead of returning a skipped or zero-test green.

## Retained RED Evidence

A read-only QA audit used Playwright `--list` and found that the default config
collected 52 tests from seven files: 36 route-fixture tests, two real-provider
tests and 14 failure-injection tests. At the same time, written official-stream,
cancel, HITL, Inbox, Library and Fork specs were not owned by any active
`testMatch`; their intended commands returned `No tests found`.

The first executable discovery contract retained `14 failed`. This was a real
test-admission defect: file-existence checks had allowed non-executable browser
coverage to look present. No real test body was executed during this RED/GREEN
sequence.

## Implementation

- `playwright.config.ts` maps each explicit `V2_E2E_PROFILE` to an owned spec
  list and rejects unknown profiles.
- With no profile, only the four fixture specs are collected. Real provider,
  failure injection, pre-seeded HITL/Inbox/Fork and other environment-dependent
  suites cannot enter the default run.
- Each non-fixture profile validates its required environment gate while the
  Playwright config loads. Missing admission now fails rather than producing a
  zero-test or all-skipped result.
- Dedicated npm commands select the real-provider, official stream, cancel,
  HITL, Inbox, Library, Fork and multi-interrupt profiles and their exact spec.
- `tests/deployment/test_playwright_discovery.py` executes local Playwright
  `--list`, parses every `(project, spec)` pair and requires an exact matrix for
  profiles and npm commands. It also verifies missing gates and unknown
  profiles fail closed.

## Discovery Matrix

```text
fixture:                38 tests / 4 files
real-provider:           2 tests / 1 file
failure-injection:      18 tests / 2 files
real-official-stream:    2 tests / 1 file
real-cancel:             2 tests / 1 file
real-hitl:               2 tests / 1 file
real-inbox:              2 tests / 1 file
real-library:            2 tests / 1 file
real-fork:               2 tests / 1 file
real-multi-interrupt:    2 tests / 1 file
m4-security:             6 tests / 1 file
```

Desktop and Pixel 7 are collected for each profile. Real-provider and
failure-injection retain explicit project names. Several pre-existing real
specs still require the historical `fixture-desktop/fixture-pixel-7` project
names internally; profile ownership prevents them from entering the default
fixture suite, but renaming those projects remains a cleanup opportunity.

## Verification

```text
initial executable discovery RED:       14 failed
profile/script/environment gate:         29 passed
current profile/script discovery:        29 passed
frontend typecheck:                      passed
focused ESLint:                          passed
Ruff check/format:                       passed
git diff --check:                        passed
```

All Playwright commands in this slice used `--list`. They did not submit an
analysis, call a failure-injection control endpoint, mutate Product PostgreSQL
or execute browser assertions.

## Evidence Boundary

This proves that intended browser suites are discoverable, isolated by profile
and fail closed when environment admission is absent. Discovery itself does not
prove any test body passes. Real official-stream, cancel, HITL, Inbox, Library
and Fork results are recorded in their own implementation notes; failure
injection additions, licensed durability, hosted identity and release browser
acceptance remain separate gates. V2 remains `PARTIAL`; `Production Ready: NO`.
No commit or push was performed.
