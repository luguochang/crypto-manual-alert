# 2026-07-18 Partial-State Playwright Body

## Coverage Added

The failure-injection profile now has a real Product browser body for the
cross-layer partial state:

1. OKX HTTP failures exhaust the normal retry budget.
2. The Web market fallback returns one typed market snapshot and one persisted
   Evidence record.
3. The later `research_events` stage fails.
4. Product remains `failed` with no Artifact, while the UI retains the source
   card and renders `已保留 1 条来源，研究未完成`.

The body asserts Product API state, error endpoint/provider/type, Evidence
lineage, reload persistence, no raw JSON, DOM overflow, unnamed controls and
axe violations in Desktop and Pixel 7 projects.

## Verification

Playwright discovery completed with two instances:

```text
[failure-injection-desktop] renders retained Web market evidence when later research fails
[failure-injection-pixel-7] renders retained Web market evidence when later research fails
```

The body was then executed against an isolated local stack using separate
Agent Server/frontend ports and a shared but unchanged Product PostgreSQL
schema. The normal 3001/8123 development stack was kept out of the test's
worker lease path and restored after the run:

```text
2 passed (17.3s)
failure-injection-desktop: passed
failure-injection-pixel-7: passed
```

The observed Product state was `failed + one web_evidence + no artifact`, with
the error attributed to `research_events`; both viewports retained the source
card, passed DOM/axe/overflow/unnamed-control checks and preserved the state
after reload. The original real browser partial state remains separately
recorded as evidence of the external dependency failure path.

The controlled body must be run through
`tools/v2/run_failure_injection_e2e.sh` (or an equivalent isolated stack) with
the explicit non-production failure-injection environment. This result is
controlled-dependency QA evidence and cannot close hosted provider, licensed
Runtime or production release gates.
