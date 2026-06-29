# Data Sources

Use primary or near-primary sources where possible. For unstable market facts, always refresh by web search or API.

Only load this file for live trade calls, unstable data, or source disputes. For normal explanations, use the lighter factor checklist.

## Freshness Requirements

- Price/ticker/order book: ideally under 1-2 minutes old.
- Funding/OI: under 5-15 minutes if exchange data updates at that frequency; otherwise mark the native update interval.
- Candles: latest candle must align with the current 1H/4H period.
- Liquidation, long/short, taker flow, CVD: under 15-30 minutes for intraday use; older data is background only.
- ETF flows: mark `T+0 preliminary`, `T+1 final`, or `stale`.
- Macro market data such as VIX/yields/DXY/oil/QQQ: under 15 minutes during event windows when possible.
- Official macro actuals: include release timestamp.
- Breaking news: include publication time and confirmation status.

## Exchange And Crypto

OKX public APIs:

- Ticker: `https://www.okx.com/api/v5/market/ticker?instId={INST_ID}`
- Candles: `https://www.okx.com/api/v5/market/candles?instId={INST_ID}&bar=1H&limit=48`
- Funding: `https://www.okx.com/api/v5/public/funding-rate?instId={INST_ID}`
- Open interest: `https://www.okx.com/api/v5/public/open-interest?instId={INST_ID}`
- Mark price: `https://www.okx.com/api/v5/public/mark-price?instType=SWAP&instId={INST_ID}`
- Index ticker: `https://www.okx.com/api/v5/market/index-tickers?instId={INDEX_ID}`
- Books: `https://www.okx.com/api/v5/market/books?instId={INST_ID}&sz=10`

Index ID examples:

- `BTC-USDT-SWAP` -> `BTC-USDT`
- `ETH-USDT-SWAP` -> `ETH-USDT`
- `SOL-USDT-SWAP` -> `SOL-USDT`

Common instruments:

- `BTC-USDT-SWAP`
- `ETH-USDT-SWAP`
- `SOL-USDT-SWAP`

Only pull non-core instruments when the user explicitly asks for them.

Fallback exchange/API ladder:

- Primary: OKX public API for default BTC/ETH/SOL swaps.
- Fallback 1: Binance USD-M futures public API for ticker, premium index, funding history, open interest, klines, depth, global long/short ratio, and taker buy/sell volume.
- Fallback 2: Bybit V5 public market API for tickers, funding history, open interest, kline, and orderbook.
- Fallback 3: Deribit public API for BTC/ETH options book, IV/skew, and options open interest context.
- Fallback 4: CoinGlass / Coinalyze / Velo / Laevitas for all-market funding, OI, long/short, liquidation heatmaps, and options. If no API access, use webpage/search-derived values and mark them as delayed.
- Spot sanity check only: Coinbase, Kraken, CoinGecko, CoinMarketCap. These do not replace derivatives data.

If exchange APIs fail, do not stop at `unavailable`. Run the web fallback sweep below and report which derivative facts were recovered:

- `CoinGlass {BTC|ETH|SOL} funding rate open interest long short liquidation`
- `CoinGlass currencies {BTC|ETH|SOL} open interest volume liquidated funding`
- `Coinalyze {BTC|ETH|SOL} open interest funding liquidation`
- `Velo Data {BTC|ETH|SOL} funding open interest`
- `Laevitas {BTC|ETH} options max pain skew IV open interest`
- `Decentrader FOILS Bitcoin funding open interest long short`
- `CoinGlass crypto market liquidation heatmap BTC ETH`

Classify recovered values as:

- `exchange-native`: direct OKX/Binance/Bybit/Deribit API.
- `aggregator-api`: direct aggregator API/export.
- `web-derived`: visible webpage/snippet value from CoinGlass/Coinalyze/Velo/Laevitas/Decentrader.
- `search-derived`: search result snippet only.

Search-derived data can reduce uncertainty but cannot remove the confidence cap for precise futures execution. If mark/index/order book are still missing, no high-confidence market entry.

If CoinGlass, Coinalyze, Velo, or Laevitas are inaccessible, exchange-native funding/OI is local evidence only. Do not label derivatives confirmation as strong unless at least one non-exchange crowding, liquidation, long/short, taker-flow, or basis source is fresh.

Flows and derivatives:

- Farside BTC ETF flows: `https://farside.co.uk/btc/`
- Farside ETH ETF flows when ETH is traded or cited: `https://farside.co.uk/eth/`
- Issuer official daily files or fund pages when Farside is stale; mark preliminary/final/stale.
- CoinGlass: liquidation, long/short, options max pain.
- Alternative.me Fear & Greed API: `https://api.alternative.me/fng/`
- Deribit: options expiry policy and BTC/ETH options data.
- DefiLlama: stablecoin total supply, TVL, unlock references.
- CryptoQuant / Glassnode / Nansen-like sources when available: exchange stablecoin reserves, exchange stablecoin netflow, exchange BTC/ETH inflow/outflow. If unavailable, mark `exchange dry powder unavailable`; do not use total stablecoin supply as a short-term exchange-buying proxy.
- Tokenomist / TokenTrack / CoinMarketCal: token unlocks and events only for explicitly requested non-core tokens. Cross-check; do not trust one source.

Data-quality checks:

- API timestamps must be close to current time; otherwise mark `stale`.
- Mark/index/last deviations require a second source.
- OI units must be normalized to USD/notional before cross-venue comparison.
- Funding periods must be normalized before comparing venues.
- Candle timestamps must be aligned to UTC/exchange timezone and macro release time.
- HTTP errors, rate limits, empty arrays, missing fields, and contradictory sources are not neutral; record them under unavailable/stale data and apply confidence caps.

## Macro

Official:

- Federal Reserve FOMC calendar: `https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm`
- Federal Reserve H.15 rates: `https://www.federalreserve.gov/releases/h15/`
- BLS CPI: `https://www.bls.gov/news.release/cpi.nr0.htm`
- BLS PPI: `https://www.bls.gov/news.release/ppi.nr0.htm`
- BLS Employment Situation: `https://www.bls.gov/news.release/empsit.htm`
- BEA PCE and release schedule: `https://www.bea.gov/news/schedule`
- U.S. Treasury rates: `https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics`
- FRED 10Y real yield: `https://fred.stlouisfed.org/series/DFII10`

Market:

- Cboe VIX: `https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv`
- CME FedWatch: `https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html`
- DXY, WTI, Brent, Nasdaq/QQQ, NQ/ES futures, MOVE/credit proxies: use CME/Nasdaq/Yahoo Finance/MarketWatch/Stooq/TradingView-style market data and label delayed vs live.
- MacroMicro / Investing / Trading Economics / Econoday: consensus expectations when official sources provide release schedules but not market consensus. Cross-check if possible.
- OIS/SOFR futures: use CME/SOFR futures or professional-rate data when available. If unavailable, CME FedWatch is only a retail-implied proxy and must be labeled as such.

News:

- Reuters, AP, Bloomberg, CNBC for breaking geopolitical and macro news.
- For geopolitics, use at least two independent reputable sources before treating a claim as confirmed.
- Use recency and timestamps. News about war, oil, sanctions, central banks, and IPOs changes quickly.
- Crypto-native primary routes: OKX/Binance/Bybit status pages, Deribit status, Solana status, Ethereum blog, Bitcoin Core/project release notes when relevant, Tether/USDC issuer announcements, SEC/CFTC press releases, ETF issuer notices, and major security/exploit disclosures.

## Equity-Linked / Entity-Anchored Products

Use this section only when the user explicitly names an equity-linked perp, tokenized equity product, stock-linked crypto contract, entity/index-anchored product, or SPCX-style instrument.

Source priority:

- Product execution facts: exchange or venue API/page for last, mark, index/oracle, funding, OI, order book, contract rules, funding schedule, session rules, and settlement rules.
- Underlying U.S. equity/ETF facts: primary exchange or official market data where available; otherwise Nasdaq/NYSE/Cboe/finance pages labeled delayed. Record cash session, premarket, after-hours, or closed.
- Underlying company/entity facts: company investor relations, SEC EDGAR filings, IPO prospectus/S-1/424B, press releases, official website, or reputable financial news.
- Industry/peer facts: sector peers, QQQ/NQ/ES/SPY, VIX, DXY, yields, and relevant peer tickers or ETFs.
- Corporate-action and market-structure facts when relevant: lockups, unlocks, borrow availability, short-sale restrictions, halts, options chain/skew, and major insider/secondary offering filings.

Required search lanes:

- `{instrument} contract rules mark index funding open interest`
- `{instrument} USDT perp funding open interest long short liquidation`
- `{company_or_ticker} investor relations SEC filing IPO prospectus latest`
- `{company_or_ticker} stock premarket after hours halt news today`
- `{company_or_ticker} IPO lockup expiration secondary offering insider selling`
- `{industry_or_peer} stocks today Nasdaq QQQ risk appetite`
- `{instrument_or_company} premium discount basis tokenized equity perp`

Decision use:

- If product mark/index/oracle is missing, stale, or opaque, do not use underlying company news alone as support for a fresh perp entry.
- If the underlying stock/entity anchor is unavailable or the equity session is closed, label premium/discount uncertain and apply the confidence cap from `exchange-derivatives.md`.
- If product quote diverges from the underlying anchor, explain whether the divergence is premium/discount, funding/carry, liquidity gap, session mismatch, or likely stale data.
- Industry strength can support continuation only when the product's own liquidity, mark/index, and derivatives data confirm. Industry weakness can support shorts only when price structure and product derivatives confirm.

## Mandatory Live Search Sweep

For any live trade call, run a targeted sweep instead of relying on one search result. Use the relevant lanes below and prefer recency filters when available.

### Breaking Geopolitics / Oil

Use when there is war, ceasefire, sanctions, Strait of Hormuz, Israel/Iran, U.S./Iran, Russia/Ukraine, Red Sea, or oil-shipping risk.

- `Reuters {geopolitical_event} oil risk assets today`
- `AP {geopolitical_event} oil markets today`
- `Bloomberg {geopolitical_event} oil rates markets today`
- `CNBC oil prices {geopolitical_event} risk assets today`
- `WTI Brent crude today {geopolitical_event}`

Decision use:

- Confirmed ceasefire or shipping reopening usually reduces oil-risk premium.
- Lower oil reduces inflation fear, supports rate-cut expectations, and can support BTC/ETH/SOL if yields/DXY confirm.
- Failed ceasefire, sanctions, or shipping disruption raises oil and can pressure crypto through inflation and risk-off channels.

### Fed / Rates / Data Expectations

Use before CPI/PPI/PCE/NFP/FOMC or when yields move sharply.

- `CME FedWatch rate cut probability today`
- `{current_or_next_fomc_month_year} FOMC dot plot Powell preview consensus`
- `US CPI consensus forecast {next_release_date_or_month} core CPI`
- `US PPI consensus forecast {next_release_date_or_month}`
- `US PCE consensus forecast {next_release_date_or_month} core PCE`
- `US nonfarm payrolls consensus forecast {next_release_date_or_month} unemployment wage growth`
- `Treasury yield 2 year 10 year real yield today`

Decision use:

- Record consensus, prior value, actual value when released, and immediate market reaction.
- Trade the surprise versus consensus, not the headline alone.
- If actual data is not released yet, classify the market as pre-event positioning.

### Crypto Market Structure

Use for BTC/ETH/SOL futures decisions.

- `BTC ETF flows Farside latest`
- `Bitcoin Ethereum Solana funding open interest liquidation heatmap today`
- `BTC ETH SOL long short ratio CoinGlass today`
- `CoinGlass currencies BTC ETH SOL open interest funding liquidated 24h`
- `CoinGlass liquidation heatmap Bitcoin Ethereum Solana today`
- `Coinalyze BTC ETH SOL open interest funding rate today`
- `Velo BTC ETH SOL funding open interest today`
- `Decentrader FOILS Bitcoin futures open interest long short ratio`
- `Deribit BTC ETH options expiry max pain current week`
- `stablecoin supply crypto market DefiLlama latest`
- `crypto fear greed index API latest`
- `BTC MVRV NUPL SOPR latest`

### Crypto Infrastructure / Regulatory Incidents

Use when there are exchange outages, chain halts, stablecoin depegs, ETF issuer updates, hacks, SEC/CFTC action, or major wallet/exchange-flow rumors.

- `{exchange} status incident withdrawals deposits today`
- `{chain} status halt outage today`
- `Tether USDT Circle USDC announcement depeg reserves today`
- `SEC CFTC crypto enforcement ETF issuer announcement today`
- `{asset} exploit hack bridge incident today`

Decision use:

- Primary route beats social media. If only social media reports exist, mark as rumor risk.
- Exchange/chain outage can override normal technical signals through liquidity and liquidation risk.
- Stablecoin depeg or withdrawal stress is an all-direction hard-block risk until confirmed or resolved.

### Equity-Linked / Entity-Anchored Product Sweep

Use when the user explicitly asks about an equity-linked perp, stock-linked token, tokenized equity product, entity/index-anchored product, or SPCX-style instrument.

- `{instrument} mark index funding open interest long short liquidation today`
- `{instrument} order book spread premium discount basis today`
- `{instrument} contract rules oracle settlement funding schedule`
- `{company_or_ticker} SEC EDGAR IPO prospectus S-1 424B latest`
- `{company_or_ticker} investor relations press release today`
- `{company_or_ticker} stock price premarket after hours halt news today`
- `{company_or_ticker} lockup expiration insider sale secondary offering borrow options`
- `{industry_or_peer_group} stocks today QQQ Nasdaq VIX yields`

Decision use:

- The product's tradable price is primary for execution; the underlying entity or stock is the anchor for causality.
- Missing product execution facts hard-block fresh entry if this is the traded instrument.
- Missing underlying/entity facts cap confidence below 58% when the thesis depends on the anchor.
- Do not use broad BTC/ETH/SOL macro strength to override product-specific premium/discount, halt/session, or liquidity risk.

Decision use:

- BTC is the direction anchor.
- ETH/SOL longs require relative strength versus BTC plus non-crowded funding/OI.
- A crowded long setup can be bearish even with good news.

## Targeted Search Queries

Use targeted queries:

- `Reuters Bitcoin oil Iran FOMC today`
- `Reuters Bitcoin oil {geopolitical_event} FOMC today`
- `FOMC {current_month_year} dot plot Powell press conference`
- `BTC ETF flows Farside {current_date_or_month}`
- `ETH ETF flows Farside {current_date_or_month}` when ETH is traded or cited
- `CPI PPI PCE release date official`
- `{asset} token unlock date source Tokenomist DefiLlama` only when user asks for that asset.
- `{instrument_or_company} contract rules mark index funding premium discount` only when user asks for an equity-linked/entity-anchored product.

## Source Priority By Data Type

- Price, mark, index, funding, OI, candles, order book: exchange API first; OKX default, Binance/Bybit fallback.
- All-market funding/OI/long-short/liquidation: CoinGlass / Coinalyze / Velo / Laevitas; exchange-native data is local evidence only.
- Options: Deribit raw API first for BTC/ETH, then Laevitas / Amberdata / CoinGlass options.
- ETF flows: Farside, issuer official data, or Bloomberg-like market data; label preliminary/final/stale.
- Macro actuals: official BLS, BEA, Fed, Treasury, Cboe, FRED.
- Macro consensus: Trading Economics, Econoday, Investing, Bloomberg-like sources; label as non-official consensus.
- News: official statement > Reuters/AP/Bloomberg > CNBC/WSJ/FT > social media. Geopolitics needs at least two reputable sources.
- Equity/entity anchors: exchange/venue contract page and mark/index feed > official company/SEC/issuer sources > primary exchange market data > Reuters/AP/Bloomberg/CNBC/WSJ/FT > social media.
- On-chain/cycle: Glassnode, CryptoQuant, IntoTheBlock, LookIntoBitcoin; mark frequency and lag, and do not use as primary 15m/1h entry reason.
- Social media/CT/Telegram: sentiment and rumor only, never confirmed fact.
