# Exchange Derivatives Checklist

Use this reference whenever the user trades futures/contracts or asks about long/short, liquidation, funding, OI, order book, or “庄家收割”.

## Core Data

Minimum tradable data pack for any leveraged call:

- Current last, mark, and index price with timestamp.
- BTC 1H/4H structure, even when trading ETH/SOL.
- Current order book depth/spread for market entries, high leverage, thin liquidity, or any instrument outside BTC/ETH/SOL.
- Funding rate and next funding time.
- OI and recent OI change.
- Macro bridge: DXY/yields/VIX/oil or explicit unavailable.
- At least one crowding source beyond a raw exchange ticker when making a leveraged directional call.
- Event calendar check for the next 24-48h.
- If trading ETH/SOL: ETH/BTC, SOL/BTC, and SOL/ETH relative strength.

If 2+ items in the minimum pack are unavailable or stale, first classify the missing facts:

- Core execution facts: current last/mark/index, 1H/4H candles, funding/OI for the traded instrument, and active event status during a 24-48h event window. If any core execution fact is unavailable, use `no trade` for new positions or `close long`/`close short` when an existing position is invalidated; do not use directional triggers until the facts refresh.
- Auxiliary facts: liquidation heatmap, long/short, taker flow/CVD, basis, options outside an expiry window, ETF/stablecoin data not used as support, or order book when not making a market/high-leverage entry. Missing auxiliary facts may allow `trigger long` or `trigger short` with a confidence cap.

Do not assign 60%+ directional confidence while minimum-pack gaps remain.

Before marking any derivatives bucket unavailable, exhaust the fallback ladder:

1. OKX/Binance/Bybit exchange APIs.
2. Deribit for BTC/ETH options.
3. CoinGlass / Coinalyze / Velo / Laevitas / Decentrader webpages or search snippets for funding, OI, long/short, liquidation heatmaps, options, and basis.
4. Market-data/web quote pages only for spot sanity checks.

If the fallback is webpage-derived or search-derived, state that explicitly. Web fallback can recover directional crowding context, but it does not fully replace fresh mark/index/order book for liquidation-sensitive entries.

Single-item hard caps:

- If last/mark/index is unavailable or stale, cap below 60% even if other facts align.
- If funding/OI is unavailable or stale, cap below 60% for leveraged directional calls.
- If active event status is unavailable during a 24-48h macro/geopolitical window, cap below 55%.
- If order book is unavailable for market entry or high leverage, do not recommend fresh market entry; use a trigger or require recheck.

For each traded instrument, collect:

- Last price.
- Mark price.
- Index price.
- 24h high/low.
- Funding rate and next funding time.
- Funding annualized estimate and 7d/30d percentile when available.
- Open interest in coin and USD/notional.
- OI 1h/4h/24h change.
- OI/volume or OI/market cap when available.
- 1H and 4H candles.
- Order book depth near price, spread, 1%/2% imbalance, and obvious buy/sell walls.
- Long/short ratio, taker buy/sell, CVD, and liquidation heatmap if available from external sources.
- Perp basis / premium vs spot, dated futures basis, and CME gap/OI when relevant.
- Spot volume vs perp volume, realized volatility, ATR/range expansion, and spot-perp divergence.
- Options max pain, put/call OI, ATM IV, 25-delta skew, and gamma zones near major expiry when available.

## Interpretation Rules

### Funding

- Mild positive: normal in an uptrend.
- Extreme positive: crowded longs; beware long squeeze.
- Mild negative while price rises: shorts may be paying; continuation can improve.
- Extreme negative: crowded shorts; beware squeeze up.

### Open Interest

- Price up + OI up: new leverage entering; trend can continue but watch crowding.
- Price up + OI down: short covering; less reliable continuation.
- Price down + OI up: new shorts or trapped longs; watch liquidation.
- Price down + OI down: deleveraging; may stabilize after flush.
- Use OI change windows. A 24h OI rise can hide a 1h unwind; do not mix horizons.
- Normalize OI units before comparing venues. Coin count, contract count, and USD notional are not interchangeable.

### Basis / Premium

- Perp premium rising with price and OI = leverage chase; check crowding before longing.
- Perp premium flat/negative while spot pushes price higher = healthier rally.
- Dated futures basis rising too fast can indicate crowded carry/leverage.
- Basis compression during a selloff can mean deleveraging is already happening.
- If basis/perp premium is unavailable, do not use spot-led vs leverage-led quality as a support reason; mark basis unavailable and apply the appropriate confidence cap when it matters to the thesis.

### Taker Delta / CVD

- Price up + positive taker delta + spot volume confirms demand.
- Price up + weak/negative CVD may be short covering or thin-book squeeze.
- Price down + negative taker delta + OI rising confirms aggressive selling.
- Divergence between CVD and price warns of absorption or spoof-prone conditions.

### Mark vs Last

- Mark price drives liquidation. Do not rely only on last price.
- If mark is below last for a long position, liquidation risk is worse than the screen may feel.
- For thin event products requested by the user, mark/index stability is central.

### Order Book And “Harvest” Risk

Crypto is semi-transparent:

- Liquidation clusters can be targeted.
- Stop zones near obvious levels can be swept.
- Thin order books amplify wicks.
- Events with high OI and extreme funding attract stop hunts.

Mitigation:

- Do not place stops exactly at obvious round numbers if the user has flexibility.
- Prefer structural invalidation zones over arbitrary tiny stops.
- Do not hold high leverage through major macro events unless explicitly intended.

### Liquidation Windows

- Use the window that matches the trade horizon: 1h/4h for intraday, 24h/7d for swing context.
- A dense liquidation cluster above price can create squeeze risk for shorts.
- A dense cluster below price can create flush risk for longs.
- Do not put invalidation exactly inside the largest obvious cluster if a structural alternative exists.

### Volume And Volatility

- Breakouts with spot volume confirmation have higher quality than perp-only breakouts.
- Low realized volatility before a major event means a tighter stop may be mechanically swept.
- ATR/range expansion after a data release can require wider invalidation or no trade.

## Product-Specific Notes

### BTC

BTC is the direction anchor. If funding is not crowded and macro is risk-on, BTC long is usually cleaner than weak altcoin long.

### ETH

ETH is a higher-beta major. Prefer ETH long only when ETH/BTC is stable or rising and funding is not crowded.

### SOL

SOL is a high-beta major. Prefer SOL long only when SOL/BTC and SOL/ETH show relative strength and derivatives are not crowded.

### Non-Core Assets

Analyze token unlocks, special product rules, premium/discount, or chain-specific events only when the user explicitly asks.

### Equity-Linked / Entity-Anchored Perps

Use this section only when the user explicitly names an equity-linked perp, tokenized equity product, stock-linked crypto contract, entity/index-anchored product, or SPCX-style instrument.

Product fact gate:

- Instrument, venue, contract type, settlement currency, funding schedule, and trading/session rules.
- Last, mark, and index/oracle price with timestamp and freshness.
- Underlying anchor: stock, ETF, private-company proxy, IPO reference, index basket, entity revenue/asset proxy, or venue-defined formula.
- Anchor source and freshness. If the anchor is a U.S. equity or IPO, record whether the cash session, premarket, or after-hours market is open.
- Premium/discount or basis between the perp/product quote and the underlying anchor when calculable.
- Order book depth, spread, slippage, obvious walls, and halt/suspension risk.
- Funding, OI, OI change, long/short ratio, taker flow/CVD, liquidation clusters, and venue concentration.

Confidence caps and blocks:

- If product mark/index/oracle is unavailable, stale, or unclear, treat it as a core execution hard block: use `no trade` for new positions or close invalidated existing positions; do not use directional triggers until it refreshes.
- If product execution facts are fresh but the underlying anchor source is unavailable, stale, or unclear, do not recommend fresh market entry; use `trigger long`, `trigger short`, or `no trade` and cap below 58%.
- If the product quote is live but the underlying equity/session anchor is closed or stale, treat premium/discount as uncertain and downgrade size/confidence.
- If order book depth is thin or halt/session rules are unclear, market entry is hard-blocked for high leverage.
- If equity-linked data is auxiliary context and not the execution vehicle, mark missing fields as unavailable and apply only a soft downgrade unless the thesis depends on them.

Interpretation:

- High positive funding or high long/short ratio is not an automatic short. A crowded long can keep trending during IPO-style price discovery if mark/index rises, OI expands with positive taker flow, and the underlying anchor confirms.
- "Do not chase long" is not the same as "open short". A short needs breakdown/failed acceptance, valid RR, and no evidence that shorts are trapped.
- A sharp drop after an IPO or entity-news squeeze may be either objective repricing or already-front-run deleveraging. Check whether OI/funding normalized, liquidation clusters below were cleared, and bad news still makes new lows.
- Underlying company quality, industry theme, or IPO emotion is only one input. Perp execution quality comes from mark/index stability, premium/discount, liquidity, funding/OI, and session status.

Hard invalidators:

- For shorts: acceptance above the short invalidation level with rising OI, positive taker flow, stable or widening premium, and no deterioration in the underlying anchor.
- For longs: loss of anchor/index support, widening discount, funding/OI unwind against price, or halt/session/news risk that blocks exit.

## Primary OKX API Targets

- Ticker: `https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT-SWAP`
- Funding: `https://www.okx.com/api/v5/public/funding-rate?instId=BTC-USDT-SWAP`
- OI: `https://www.okx.com/api/v5/public/open-interest?instId=BTC-USDT-SWAP`
- Candles: `https://www.okx.com/api/v5/market/candles?instId=BTC-USDT-SWAP&bar=1H&limit=48`
- Books: `https://www.okx.com/api/v5/market/books?instId=BTC-USDT-SWAP&sz=10`
- Mark: `https://www.okx.com/api/v5/public/mark-price?instType=SWAP&instId=BTC-USDT-SWAP`

## Fallback API Targets

Use these if OKX fails, rate-limits, returns stale timestamps, or conflicts with another source:

- Binance USD-M futures: ticker/book ticker, premium index, funding history, open interest, klines, depth, global long/short ratio, taker buy/sell volume.
- Bybit V5 market: tickers, funding history, open interest, kline, orderbook.
- Deribit public API: BTC/ETH options order book, book summary, IV/skew/open interest context.
- CoinGlass / Coinalyze / Velo / Laevitas: all-market funding, OI, long/short, liquidation heatmap, options, and exchange comparison.
- Coinbase/Kraken/CoinGecko/CoinMarketCap: spot price sanity checks only; do not use them as substitutes for derivatives data.

Mark each fallback result with source, timestamp, and whether it is exchange-native, aggregator, webpage-derived, or search-derived.

Required fallback search terms when APIs fail:

- `CoinGlass {asset} funding rate open interest long short liquidation`
- `CoinGlass currencies {asset} open interest 24h liquidated funding`
- `Coinalyze {asset} open interest funding liquidation`
- `Velo Data {asset} funding open interest`
- `Laevitas BTC ETH options max pain skew IV open interest`
- `Decentrader FOILS Bitcoin open interest long short ratio`
