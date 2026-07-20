# 2026-07-18 Real Provider Revalidation After Prompt Update

## Scope

The latest `market-analysis-v2` and `web-market-extraction-v2` contracts were
revalidated through the real Product UI after the local stack was restored.
The result is intentionally recorded as external-provider RED; no fallback or
uncited data was accepted to force a successful Artifact.

Provider identity correction: the diagnostic path below used DDGS
`backend="auto"` metasearch, not a guaranteed DuckDuckGo backend. The failure
sequence remains valid, but its provider label is superseded by
`ddgs_metasearch`.

## Diagnostic DDGS Metasearch Run

With the local diagnostic provider, Desktop and Pixel 7 both reached:

```text
OKX retry exhaustion -> DDGS Text metasearch fallback -> 8 persisted Web Evidence
-> research_events DDGS News metasearch timeout budget exhausted
```

Both tests failed the success-only assertion with the truthful UI state:
`后续研究检索未完成`, `本次运行已保留 8 条可验证 Web 来源`, and no final
analysis Artifact. Agent logs show DDGS automatic backend timeout attempts
1, 2 and 3 at `research_events`.

## Approved Built-in Web Search Run

The stack was then restarted with `SEARCH_PROVIDER=builtin_web_search`, and the
same Desktop/Pixel 7 real Product profile was executed. Both tests failed at
the market collection boundary:

```text
provider=builtin_web_search
endpoint=collect_market_snapshot
error_type=APITimeoutError
attempts=1,2,3
```

The Product UI correctly rendered the distinct two-layer failure message that
the exchange and Web Search market fallback were both unavailable. No model
analysis or Artifact was generated. This proves the approved provider is not
currently usable in the active local endpoint/network configuration; it does
not prove that the provider is invalid in a correctly licensed/egressed hosted
deployment.

## Decision

Keep the provider boundary strict:

- do not accept model-only or uncited prices;
- do not turn a timeout into a success or a partial failure into an analysis;
- keep provider/error endpoint attribution visible to Product and operators;
- resolve the production Web Search credential/endpoint/egress capability
  before claiming the real success gate.

The current local stack remains running on `http://127.0.0.1:3001` with Agent
Server `http://127.0.0.1:8123`. V2 remains `PARTIAL`; `Production Ready: NO`.
