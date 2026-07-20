# Local Product Health Load Preflight

Date: 2026-07-18 Asia/Shanghai
Phase: M6 / local load preflight
Status: local Product health probe complete; ADR 0006 SLO remains open

## Implementation

- `tools/v2/run_load_probe.py` performs bounded concurrent HTTP requests using
  the Python standard library. The local profile accepts loopback origins only,
  rejects credentials/query fragments and caps requests, concurrency and
  timeout.
- Every response must be HTTP 200 with the Product health contract
  `{"status":"ok","version":"2.0.0"}`. Timeout, transport, status and payload
  failures are counted with bounded categories; exception text is not written
  to the report.
- Reports use unique temporary files, `0600` permissions, fsync and atomic
  replacement. Hosted profile execution is explicitly rejected until the
  complete source/governance/image/HTTPS gate exists.
- `backend/tests/performance/test_concurrency_stream_load.py` covers real
  loopback concurrency, unhealthy responses, hosted refusal, credentials and
  unbounded concurrency.

## Fresh Evidence

A fresh Product HTTP process served the real FastAPI route
`/app/api/v2/health` on loopback. The probe then executed:

```text
requests=200
concurrency=20
success=200
failure=0
p50=3.446ms
p95=22.852ms
p99=25.523ms
max=27.039ms
```

Focused performance contracts: `4 passed`. The report mode was `0600` and
`secret_scan.findings=0`.

## Evidence Boundary

The report deliberately contains `slo_claims=[]`. Health latency is not the
ADR 0006 request-confirmation metric and does not exercise task admission,
first visible stream event, model/search/market analysis, reconnect, duplicate
event detection, Structured Output, Evidence completeness, checkpoint recovery
or hosted availability. The proof level is
`local-http-load-preflight`, not production load or SLO acceptance. V2 remains
`PARTIAL`; `Production Ready: NO`. No commit or push was performed.
