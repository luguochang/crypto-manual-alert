# Task 12 Market Fallback Matrix Record

Date: 2026-07-18 Asia/Shanghai
Phase: Task 12 / controlled dependency failure matrix
Status: local controlled full-chain scenarios complete; external-provider and
hosted failure acceptance open

## Objective

Prove both sides of the canonical market fallback path without mocking the
Product API:

1. OKX retries exhaust, cited Web Search market fallback succeeds, and the
   conservative result plus fallback Evidence/provenance persist and render.
2. OKX retries exhaust and Web Search market fallback also fails, producing one
   honest two-layer Product failure, no Artifact and the same result after
   refresh.

## Implementation

- Failure injection now includes `okx_web_fallback_success` and
  `okx_web_fallback_unavailable`.
- OKX failure remains at its HTTP transport. The real `OkxProvider` and existing
  `RetryPolicy` execute all three attempts before the canonical Graph calls its
  existing Web Search market fallback.
- A controlled `InjectingWebMarketCollector` wraps only the canonical fallback
  seam. Success returns a typed `web_search_verified` partial snapshot,
  `market_snapshot` Evidence and model audit. Failure raises a typed
  `builtin_web_search` provider error.
- The runtime still has one Graph and one fallback collector; no second Agent or
  alternate Product path was added.
- Product errors safely preserve bounded `endpoint`, `fallback_from` and
  `primary_attempt`. Raw URL, authorization, response and unbounded diagnostics
  remain excluded.
- The failure card maps this exact shape to a two-layer explanation and exposes
  first provider, first-provider attempts, fallback Provider and failed stage in
  the diagnostic disclosure. Error code and correlation ID remain visible.

## Full-Chain Assertions

The success scenario requires:

- terminal success with a committed, conservative Artifact;
- `market_snapshot.source_level=web_search_verified`;
- fallback Evidence with `evidence_relation=market_snapshot` and HTTPS URL;
- Artifact provenance `market_provider=web_search_market`;
- visible market disclosure, Evidence card and Library entry.

The double-failure scenario requires:

- terminal `failed/provider_unavailable` and no Artifact;
- provider `builtin_web_search`, fallback `okx`, endpoint
  `web_search_market`, primary attempt `3`;
- no market snapshot, no Web Evidence and no Library entry;
- the same Product DTO and visible two-layer diagnosis after refresh.

Neither browser scenario uses `page.route` to replace the Product API. Product
API, PostgreSQL, worker, canonical Graph and official local Agent Server are
real. External OKX/Web Search/model inputs are controlled by the explicit test
profile and must not be described as real-provider acceptance.

## Verification

```text
initial backend RED:                       missing InjectingWebMarketCollector
failure profile + Graph contracts:         39 passed
Product error UI RED:                       2 failed, 34 passed
Product error UI GREEN:                     36 passed
isolated fresh-stack Desktop A/B:           passed
focused Desktop fallback-success rerun:     1 passed in 9.9s
isolated fresh-stack Pixel 7 A/B:            2 passed in 20.7s
current Playwright discovery:               16 tests, 8 per viewport
Ruff, ESLint, TypeScript and diff checks:    passed
```

The isolated browser stack used a real PostgreSQL database and temporary local
Agent Server/frontend ports. Pixel 7 assertions included overflow, unnamed
controls and axe scans. Screenshots were captured as run artifacts, not approved
visual-regression baselines.

## Evidence Boundary

This proves local controlled-dependency behavior through the real Product and
official local Runtime boundary. It does not prove actual OKX or Web Search
outages, licensed persistent Runtime recovery, hosted network behavior or
production alerts. The current shared `3001/8123` stack is running the normal
profile; its complete failure-injection matrix was not rerun after restart.
V2 remains `PARTIAL`; `Production Ready: NO`. No commit or push was performed.
