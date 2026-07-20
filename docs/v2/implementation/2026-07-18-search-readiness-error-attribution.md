# 2026-07-18 Search Readiness Error Attribution

## Change

Strict search provider selection now includes the normalized capability failure
type in its startup error. When the configured model cannot invoke built-in Web
Search, the error distinguishes:

```text
built-in web search was not invoked (APITimeoutError); Tavily is not configured
```

The error contains provider capability metadata only; it does not include API
keys, request bodies, URLs with credentials or raw provider responses.

## Verification

- Search capability and runtime readiness contracts: `51 passed, 1 warning`.
- Ruff check: passed.
- Ruff format check: passed.

The selection remains fail-closed. This improves production diagnosis only; it
does not make an unsupported Web Search endpoint ready. V2 remains `PARTIAL`;
`Production Ready: NO`.

