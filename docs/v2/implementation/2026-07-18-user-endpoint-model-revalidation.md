# User Endpoint Model Revalidation

> Provenance correction: this historical connectivity probe used DDGS
> `backend="auto"` metasearch, not a guaranteed DuckDuckGo backend.
> Provider-identity claims in this note are superseded by
> `2026-07-18-readiness-provider-integrity-and-real-regression.md`; the recorded
> connectivity and model-capability results remain valid.

Date: 2026-07-18 (Asia/Shanghai)

Phase: `G0.2` real model capability revalidation; Web Search acceptance remains open

## Scope

The configured model was rechecked against the user-provided OpenAI-compatible
endpoint using an ephemeral process environment. No credential was written to the
repository, emitted in logs, or included in this record.

## Evidence

- `tests/real/test_real_model_capabilities.py` and
  `tests/real/test_real_model_analysis.py` were executed with
  `REAL_MODEL_TESTS=1`.
- Ordinary model capability passed: tool calling, structured output, streaming,
  usage reporting, and a real `MarketAnalysis` structured response.
- Built-in Web Search did not produce an invoked tool call or citations. The
  capability probe returned a typed `ResearchUnavailable` result, so the strict
  capability assertion failed as intended.
- The final test result was `1 passed, 1 failed`: the failure is limited to the
  built-in Web Search capability assertion.
- Direct local connectivity checks to OKX and DuckDuckGo timed out in the current
  network environment. A request to the compatible model endpoint reached the
  service; the previously configured local credential was rejected, while the
  user-provided credential allowed the ordinary model checks above.

## Decision

The model endpoint is usable for the normal LangChain structured-agent path, but it
is not a verified Web Search provider for this product. The application must remain
fail-closed: it cannot treat model memory, uncited prices, or a missing search tool
as market evidence. The G0.2 success gate remains `RED / EXTERNAL DEPENDENCY` until
one approved Web Search path has reachable egress and returns verifiable HTTPS
citations, followed by the full Desktop and Pixel 7 Product flow.

## Next Action

Provide one of the following in the target runtime without committing secrets:

1. An OpenAI-compatible endpoint with a working Responses `web_search` tool and
   citation payloads; or
2. A valid Tavily credential plus reachable outbound HTTPS; or
3. A separately approved Web Search service and its documented integration contract.

After that capability preflight passes, rerun the existing real provider Product
flow and require a committed Artifact, persisted Evidence lineage, structured model
audit, and a succeeded Run on both required viewports. No production-ready claim is
made from this local revalidation.
