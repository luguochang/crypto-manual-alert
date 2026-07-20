# Proxied Zero-Mock Product Mainline

Date: 2026-07-18

Phase: `G0.2` local zero-mock mainline

> Provenance correction: this note originally called the configured provider
> DuckDuckGo. A later audit proved `ddgs==9.14.3` used `backend="auto"` automatic
> metasearch. The real URLs/citations remain valid, but every provider identity
> claim in this note is superseded by `ddgs_metasearch`; see
> `2026-07-18-readiness-provider-integrity-and-real-regression.md`.

## Retained RED

The current-source Desktop and Pixel 7 real-provider profile first ran with
`SEARCH_PROVIDER=builtin_web_search` and no explicit local egress proxy. Both
runs crossed the Product API, PostgreSQL, Worker, official LangGraph development
Runtime, and real UI, then failed after three `APITimeoutError` attempts at
`builtin_web_search/collect_market_snapshot`. No Artifact or uncited market
value was accepted.

Direct probes then proved that both OKX and DDGS automatic metasearch timed out before
connection establishment. A local HTTP proxy was listening at
`127.0.0.1:7890`; through that proxy, the real OKX ticker returned HTTP 200 with
`code=0`, and DDGS automatic metasearch returned a real search response.

## Reproducible Local Decision

The local stack was restarted with:

- `SEARCH_PROVIDER=ddgs_metasearch`
- `MARKET_DATA_HTTP_PROXY=http://127.0.0.1:7890`
- `SEARCH_HTTP_PROXY=http://127.0.0.1:7890`

No Product route, exchange payload, Web Evidence, or model response was mocked.
DDGS automatic metasearch remained an explicit local provider decision and did not become a
silent fallback for the approved built-in provider.

The repository now includes `backend/.env.example`. Compose explicitly forwards
`SEARCH_PROVIDER`, `MARKET_DATA_HTTP_PROXY`, and `SEARCH_HTTP_PROXY` only to the
official Agent Server container. The template explains the different proxy
address needed by a host-run stack and Docker Desktop.

## Fresh Green

The real Product Playwright profile passed:

- Desktop: `1 passed` in approximately `1.2m`.
- Pixel 7: `1 passed` in approximately `52.9s`.
- Combined: `2 passed (2.2m)`.

Both runs exercised real OKX, real DDGS automatic metasearch, model Structured
Output, PostgreSQL, the durable Worker, the official LangGraph development
Runtime, and the rendered frontend. The test required committed/actionable
analysis, at least one matched cited source, no unmatched source, model audit
entries, Chinese rationale, HTTPS source links, evidence/risk/provenance panels,
and an OKX source marker.

The same test also passed the raw JSON, DOM overflow, clipped control, unnamed
control, axe, browser console, page error, failed request, and failed Product or
Agent response gates. PostgreSQL recorded two new succeeded Tasks, two Artifacts,
and sixteen Web Evidence records during the fresh run window.

## Boundary

This closes the current local G0.2 zero-mock Product mainline under the recorded
proxy and explicit DDGS metasearch provider conditions. It does not approve
DDGS metasearch as the production provider, prove the user's OpenAI-compatible
endpoint supports Responses Web Search, or close licensed Agent Server restart,
hosted OIDC/HTTPS, hosted egress, notification receipts, SLO, or release
attestation.

No commit, stage, or push was performed.
