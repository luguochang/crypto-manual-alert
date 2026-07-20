# 2026-07-18 Model Versus Web Capability Separation

## Real Probe

The configured endpoint was exercised with the repository's real model probe:

```text
REAL_MODEL_TESTS=1
test_real_model_analysis: passed
test_configured_model_capability_probe: failed only on builtin_web_search
```

The probe proved the configured model supports:

- tool calling;
- Structured Output;
- streaming;
- usage reporting.

It did not prove the built-in Web Search tool. The capability result was
`builtin_web_search_invoked=false`, `citation_count=0`, with a normalized
`ResearchUnavailable` failure. This matches the real Product RED at
`collect_market_snapshot`; it does not justify calling the model endpoint
generically unavailable.

## Production Decision

The current endpoint cannot be used as the approved built-in Web Search
provider until its Responses `web_search` capability returns a real HTTPS
citation. Production must either:

1. use a compatible endpoint that passes the built-in capability probe; or
2. configure and verify the approved Tavily provider.

The code must continue to fail closed when neither capability is verified.
The ordinary model path remains usable independently of the Web Search gate.

V2 remains `PARTIAL`; `Production Ready: NO`.

