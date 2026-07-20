# Internal Alpha SLO Contract Evaluator

Date: 2026-07-18 Asia/Shanghai
Phase: M6 / SLO contract foundation
Status: synthetic source-candidate contract complete; real SLO evidence open

## Implementation

- `tools/v2/run_slo_probe.py` evaluates a complete, versioned measurement
  manifest for the accepted Internal Alpha thresholds in ADR 0006.
- The manifest must contain one positive-sample measurement and a bounded
  query ID for every metric: availability measurement, request confirmation
  p95, first visible event p95, analysis p95/deadline, reconnect, duplicate
  event rate, Structured Output, Evidence completeness, checkpoint recovery,
  cross-tenant leakage and secret leakage.
- Missing/extra fields, zero samples, non-finite values, invalid ratios/counts,
  invalid windows or an out-of-threshold metric fail closed. Duplicate event
  rate uses the required exclusive `< 0.1%` comparison.
- Input content is represented in the report by SHA-256; raw measurement
  payloads are not copied. Output uses `0600`, fsync and atomic replacement.
- Hosted profile execution returns `78` until hosted source/governance/image,
  public HTTPS and measurement-provenance gates exist.

## Verification

`backend/tests/performance/test_slo_contract.py` supplies deterministic
synthetic source-candidate manifests only. It proves threshold/evaluator
behavior, not runtime SLO quality. Combined load/SLO performance tests:

```text
8 passed
```

The passing synthetic report uses proof level
`synthetic-source-candidate-slo-contract`. A failed reconnect value, missing
metric, zero sample, NaN and hosted profile all fail as intended.

## Evidence Boundary

No complete Product-flow measurement manifest exists yet. Real local and
hosted acceptance still require actual Task admission, first stream event,
market analysis duration, reconnect, event deduplication, Structured Output,
Evidence and recovery samples with time windows and query provenance. Monthly
hosted availability and production alert receipts also remain open. V2 remains
`PARTIAL`; `Production Ready: NO`. No commit or push was performed.
