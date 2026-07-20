# 2026-07-18 Deterministic Availability and Web Market Fallback

> Provenance correction: this historical run used DDGS `backend="auto"`
> metasearch, not a guaranteed DuckDuckGo backend. Provider-identity claims in
> this note are superseded by
> `2026-07-18-readiness-provider-integrity-and-real-regression.md`; URLs,
> citations, timings and the recorded execution sequence remain valid.

## Scope

This slice closes a cross-layer correctness defect in the local Product flow.
It does not change the production-readiness verdict: `V2 = PARTIAL` and
`Production Ready = NO`.

## Original RED

The real browser run reached a contradictory state:

- the Product database contained eight verified Web Evidence records;
- the page displayed eight source cards and a latest ticker value;
- the model response still claimed `unavailable_data` for Web Search and
  market inputs;
- the later `research_events` stage failed, so no final analysis was produced.

The contradiction made it impossible for an operator to tell whether data was
available, whether it was merely unavailable to the model, or whether a later
stage had failed. A second defect was that the DuckDuckGo market fallback used
the News vertical for a current-price query, which timed out and was semantically
incorrect even when the research News path was useful.

## Decision

Availability is a typed application fact, not a model-owned assertion.

- The model remains responsible for analysis, reasoning and structured
  conclusions.
- Typed market snapshots, typed research bundles and persisted Evidence are
  the authority for whether a capability produced data.
- The canonical Graph overwrites model-provided `unavailable_data` with
  `derive_unavailable_data(...)` from those typed facts.
- Historical persisted Artifacts remain immutable; normalization only applies
  to the current Graph result before the Product terminal projection.
- Frontend view models map stable machine codes to readable labels, so raw
  provider capability codes never become user-facing copy.

The market fallback reuses the existing `WebSearchMarketCollector` and typed
extraction contract. Built-in Web Search, DuckDuckGo and Tavily all pass through
the same validation boundary. DuckDuckGo research keeps its News vertical;
DuckDuckGo market fallback explicitly uses Text results because a current-price
query is not a news query. A market value is accepted only when the model
returns an exact cited quote and source URL. Web-derived values are marked
`web_search_verified` and remain ineligible for execution authorization; opening
actions still require exchange-native data.

The extraction prompt is versioned as `web-market-extraction-v2`. It includes
fetched/published timestamps, permits selecting the most explicit current/as-of
cited price when sources differ, and prohibits averaging or reconciling
conflicting values.

## Changed Boundaries

- `backend/src/crypto_alert_v2/domain/evidence_policy.py`: deterministic
  capability derivation and stable labels.
- `backend/src/crypto_alert_v2/graph/graph.py`: current-result normalization
  before persistence/projection.
- `backend/src/crypto_alert_v2/agents/market_analysis.py`: prompt/version and
  model contract aligned with typed availability.
- `backend/src/crypto_alert_v2/providers/search.py`: provider-specific market
  fallback, DuckDuckGo Text selection and `href` parsing.
- `backend/src/crypto_alert_v2/providers/web_market.py`: shared typed market
  collection and exact quote/source validation.
- `backend/src/crypto_alert_v2/graph/runtime.py`: fallback assembly and
  provider-specific failure attribution.
- `frontend/src/features/analysis/analysis-view-model.ts`: stable machine-code
  to Chinese display mapping and explicit partial research state.

## Verification

Hermetic and local verification after this slice:

- Backend complete suite at the final verification of this slice:
  `848 passed, 164 skipped, 1 warning`.
- Frontend unit suite: `368 passed` in `30 files`.
- Frontend `typecheck`: passed.
- Frontend `lint`: passed.
- Isolated frontend production build: passed; `14` routes generated.
- Ruff check and format check: passed; `179` backend files formatted.
- Root migration/structure/deployment suite: `1184 passed`.

The skip counts remain unproved and are not included as production acceptance.

## Real Browser Evidence

The current local stack was exercised through the real Product UI. Direct OKX
requests timed out and the retry budget was exhausted. DuckDuckGo Text market
fallback then succeeded, persisted a typed market snapshot and eight Evidence
records, and rendered the latest ticker as `62,040.82` with the source provider
shown as `DuckDuckGo`. The independent `research_events` request subsequently
failed. The page therefore stayed failed and showed `后续研究检索未完成` and
`已保留 8 条来源，研究未完成`, while retaining all eight source cards.

This is a truthful partial-failure proof, not a successful final analysis. A
fresh successful end-to-end run using `market-analysis-v2` and
`web-market-extraction-v2` is still required when the provider/model path is
available.

## Open Gates

Approved production Web Search/Tavily selection and hosted egress, licensed
persistent Agent Server restart/checkpoint durability, hosted OIDC/HTTPS and
multi-user browser proof, hosted LangSmith/Langfuse correlation, real
notification receipts, DR/HA, production DB roles, SLO/load/alerting, signed
SBOM/release attestation, V1 parity/removal, Deep Research lifecycle work and
the dedicated real Playwright partial-state body remain open.
