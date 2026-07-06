# Checkpoint 7 - Liquidity Exchange-Native Provider

## Context

`liquidity_order_book` already had fixture `fact_refs` for
`mark/index/order_book`, but `skill_providers.liquidity_order_book=exchange_native`
still failed closed. Phase two requires a real exchange-native boundary while
keeping provider enablement explicit and preserving the no-raw-order-book API
contract.

## Changes

- Added `OkxPublicOrderBookProvider`.
- The provider calls OKX public mark price and order book endpoints only when
  explicitly configured.
- It validates mark, index, asks, and bids exist before returning refs.
- It validates OKX timestamps against `market_data.stale_market_data_seconds`
  before returning refs.
- It returns only `OrderBookFactRefs`; raw asks/bids, prices, and original OKX
  payloads are not exposed in the skill result.
- `build_skill_registry_from_config()` now wires
  `liquidity_order_book=exchange_native` to the OKX public provider.
- `responses_web_search` remains fail-closed until a real web-search provider
  is implemented with explicit key and redaction policy.

## Verification

```powershell
python -m pytest tests/skills/test_liquidity_order_book_provider.py::test_okx_public_order_book_provider_returns_refs_without_raw_order_book_payload -q
python -m pytest tests/skills/test_liquidity_order_book_provider.py::test_okx_public_order_book_provider_rejects_stale_exchange_native_facts -q
python -m pytest tests/skills/test_skill_registry.py::test_skill_registry_from_config_wires_explicit_exchange_native_liquidity_provider tests/skills/test_skill_registry.py::test_skill_registry_from_config_fails_closed_for_unimplemented_real_providers -q
python -m pytest tests/skills/test_liquidity_order_book_provider.py tests/skills/test_skill_registry.py tests/skills/test_skill_executor.py -q
```

## Boundary Notes

- Default config still does not enable `exchange_native`.
- The adapter uses public OKX endpoints and does not require trade keys.
- Unit tests use an injected fake HTTP getter to avoid external network
  dependency.
- Stale exchange data is rejected before refs are produced.
