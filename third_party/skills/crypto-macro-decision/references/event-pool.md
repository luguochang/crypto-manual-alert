# Event Pool

This is a living event pool. Update it when a new macro, geopolitical, exchange, token, or product event could affect crypto decisions.

## Read Policy

For live decisions, read only the active decision window and unresolved active market reactions. Do not read archived notes unless reviewing history or looking for a named analog.

Historical event notes are memory, not current evidence. Every active event must have `expires at`, `next recheck`, or a resolution condition.

Before using this pool for a live decision, refresh the active table against the current date. Past events cannot remain `upcoming`; move them to `released`, `active market reaction`, `resolved`, or archive notes before they affect scoring.

## Event State Model

- Active Decision Window: events inside the next 72h or unresolved breaking events.
- Scheduled Calendar: recurring macro/crypto events with the next date only; expand into active window when within 72h.
- Active Market Reactions: past events whose transmission is still unresolved, with expiry/recheck time.
- Archived Event Notes: compressed lessons only; no stale price levels unless explicitly needed for review.

## Current High-Priority Event Watch

Last reviewed: 2026-06-19 Asia/Shanghai. Refresh before every live decision.

| Date/Time | Event | Status | Expires/Recheck | Why It Matters | Confidence | Sources To Recheck |
|---|---|---|---|---|---|---|
| 2026-06-18 onward | FOMC hawkish repricing after June SEP | Active market reaction | Recheck every live decision until yields/DXY/VIX/BTC reaction resolves | Biggest near-term BTC repricing event; affects rates, real yields, DXY, risk assets | High for Fed facts, Medium for market path | Federal Reserve calendar, CME FedWatch, Treasury yields, DXY, VIX |
| 2026-06-15 to 2026-06-19 | U.S.-Iran initial agreement / ceasefire extension / Strait of Hormuz reopening watch | Active breaking risk | Recheck oil/geopolitical headlines before every live decision; archive after implementation/failure confirmed | Oil-risk premium, inflation expectations, rate-cut odds, and risk appetite can reprice quickly | High for announcement, Medium for implementation | AP, Reuters, Guardian, Bloomberg, WTI/Brent |
| 2026-06-19 | U.S. Juneteenth holiday | Active liquidity risk | Expires after 2026-06-19 U.S. session | Thinner liquidity around holiday can increase wicks | High | U.S. market calendar |
| 2026-06-25 08:30 ET | May PCE / Personal Income and Outlays | Upcoming | Expand/update within 72h; recheck consensus before release | Fed-preferred inflation gauge | High | BEA, consensus sources |
| 2026-06-26 08:00 UTC | BTC/ETH options monthly/quarterly expiry | Upcoming | Expand/update within 72h; recheck Deribit/CoinGlass positioning | Can pin price or release volatility | Medium | Deribit/CoinGlass |
| 2026-07-02 08:30 ET | U.S. June Employment Situation / NFP | Scheduled calendar | Expand only inside 72h window | Reprices Fed path and recession risk | High | BLS |
| 2026-07-14 08:30 ET | U.S. June CPI | Scheduled calendar | Expand only inside 72h window | Inflation reset | High | BLS |
| 2026-07-15 08:30 ET | U.S. June PPI | Scheduled calendar | Expand only inside 72h window | Upstream inflation reset | High | BLS |

## Event Categories To Maintain

### Macro Scheduled

- FOMC, minutes, SEP/dot plot.
- CPI, PPI, PCE.
- NFP, initial claims, unemployment.
- Treasury refunding/auction pressure.
- BOJ/ECB/PBOC decisions when they affect global liquidity.

### Macro Breaking

- War, ceasefire, sanctions.
- Oil supply shock.
- Banking/credit stress.
- Major fiscal/debt-ceiling events.
- Sudden central-bank intervention.

### Crypto Scheduled

- BTC/ETH options expiry.
- ETF approval/flow reporting.
- Token unlocks.
- Network upgrades.
- Exchange listing/delisting.

### Crypto Breaking

- Hacks/exploits.
- Stablecoin depeg.
- Exchange insolvency/outage.
- Major regulatory action.
- Whale/treasury movement to exchanges.

### Product-Specific

- BTC: ETF flows, dominance, mining/treasury news, options expiry, macro sensitivity.
- ETH: ETH/BTC trend, ETF/staking/regulatory news, L2/on-chain activity.
- SOL: SOL/BTC and SOL/ETH relative strength, ecosystem flows, chain stability, major unlocks when relevant.
- Non-core assets and special products: track only if the user explicitly asks.

## Update Rules

When adding an event, include:

- Absolute date/time with timezone.
- Source and confidence.
- Expected direction if positive/negative.
- What would confirm it matters.
- What would invalidate it.

Never let old events remain as “upcoming” after they pass; move them to `Past Event Notes`.

Active events older than their release time must be changed to `released`, `active market reaction`, `resolved`, or `archived` on the next use. Keep active events to 5-8 items, prioritizing the next 72h plus unresolved shocks. Monthly recurring CPI/PPI/PCE/NFP/FOMC-style events should live as calendar rules and be expanded only inside the active window.

## Past Event Notes

### 2026-06-23 11:20 Beijing - PCE And BTC/ETH Options Expiry Enter Active Window

- Category: macro scheduled / crypto options.
- Status: upcoming.
- Source: BEA release calendar; Deribit options summary; Farside/market data route to recheck.
- Confidence: high for schedule, medium for market path.
- Assets affected: BTC, ETH, SOL, high-beta crypto.
- Why it matters: May PCE is due 2026-06-25 08:30 ET and BTC/ETH month/quarter options expire 2026-06-26 08:00 UTC, compressing fresh leverage decisions and increasing pin/wick risk near large strikes.
- Consensus / expected: Core PCE YoY consensus around 3.3% from public economic-calendar sources; recheck immediately before release.
- Actual / confirmed: Not released.
- Surprise vs expected: Pending.
- Bullish path: PCE cools vs consensus, yields/DXY fade, BTC reclaims 64.6K/65.1K with non-crowded funding.
- Bearish path: PCE hot or rates stay firm, BTC loses 63.8K support, ETH/SOL underperform, options hedging accelerates downside.
- What to monitor: BEA actual, 2Y/10Y yields, DXY, VIX, BTC 63.8K/64.6K/65.1K, Deribit OI/skew, funding/OI.
- Next update time: 2026-06-23 20:00 Beijing or immediately if BTC loses 63,760 / reclaims 64,650.

### 2026-06-23 11:20 Beijing - U.S.-Iran 60-Day Oil Sanctions Waiver Extends Geopolitical Relief

- Category: macro breaking / geopolitics / oil.
- Status: active market reaction.
- Source: AP, MarketWatch oil settlement report.
- Confidence: high for reported waiver/talks, medium for implementation and market transmission.
- Assets affected: BTC, ETH, SOL, oil, DXY, yields, Nasdaq.
- Why it matters: Lower oil risk can ease inflation fear, but the crypto impulse only becomes bullish if yields/DXY/VIX confirm and BTC reclaims structure.
- Consensus / expected: Peace talks and Hormuz reopening should reduce oil-risk premium.
- Actual / confirmed: AP reported high-level talks created a foundation for a final deal; MarketWatch reported WTI settled below $74 after a 60-day Iranian oil sanctions waiver.
- Surprise vs expected: Oil relief is confirmed, but crypto has not produced a clean risk-on breakout.
- Bullish path: Oil stays lower, VIX falls, yields/DXY stop rising, ETF inflows persist, BTC reclaims 64.6K/65.1K.
- Bearish path: Talks stall, tanker traffic remains below normal, yields/DXY dominate, BTC loses 63.8K.
- What to monitor: WTI/Brent, AP/Reuters geopolitical updates, Hormuz tanker traffic, 2Y/10Y yields, DXY, BTC 63.8K/65.1K.
- Next update time: 2026-06-23 20:00 Beijing or on a confirmed escalation/headline failure.

### 2026-06-15 U.S.-Iran Initial Agreement / Hormuz Reopening Watch

- AP reported an initial U.S.-Iran agreement to end the war, extend a shaky ceasefire, and open the Strait of Hormuz; implementation was reported as dependent on a Friday signing.
- Market path: confirmed implementation can lower oil, ease inflation fears, support rate-cut expectations, and improve BTC/ETH/SOL risk appetite.
- Failure path: delayed signing, renewed strikes, shipping/insurance constraints, or nuclear/sanctions disputes can bring back oil-risk premium and risk-off pressure.
- Lesson: for geopolitics, do not treat a headline as completed implementation; track oil price, yields, DXY, VIX, and official follow-through.

### 2026-06-12 SPCX / SpaceX Listing

- SpaceX/SPCX listing and OKX SPCX-USDT transition created event-volatility.
- Lesson: distinguish stock price from OKX perpetual price; compute premium and watch mark/index.

### 2026-06-10/11 CPI/PPI Shock

- CPI/PPI showed energy/headline pressure and upstream inflation concerns.
- Lesson: headline hot but core details and oil reversal determine whether risk assets recover.


### 2026-06-18 07:58 Beijing - FOMC Hawkish Repricing After June SEP

- Category: macro scheduled / Fed / rates.
- Status: past but active market reaction.
- Source: Federal Reserve statement and Summary of Economic Projections; AP market reaction; CME/FedWatch route to recheck implied path.
- Confidence: high for Fed facts, medium for market path.
- Assets affected: BTC, ETH, SOL, AVAX and high-beta crypto; Nasdaq/growth equities; dollar/yields.
- Why it matters: Crypto was not surprised by a hold; it was surprised by a more hawkish projected path and inflation assumptions, which lifted yields and pressured risk assets.
- Consensus / expected: FOMC hold at 3.50%-3.75%.
- Actual / confirmed: Fed held 3.50%-3.75%; June SEP raised 2026 median fed funds path and inflation estimates versus March.
- Surprise vs expected: hawkish path repricing, not the hold itself.
- Bullish path: yields/DXY fade, Nasdaq repairs, BTC reclaims 65.6K, ETH reclaims 1,780; market treats the hawkish SEP as peak-policy noise.
- Bearish path: yields/DXY stay firm, Nasdaq continues lower, BTC loses 64K, ETH fails below 1,744, causing high-beta crypto deleveraging.
- What to monitor: 2Y/10Y yields, DXY, VIX, Nasdaq, BTC 64K/65.6K, ETH 1,744/1,780, funding/OI, BTC ETF total flows.
- Next update time: 2026-06-18 10:30 Beijing or at BTC 64K/65.6K / ETH 1,720-1,728 or 1,772-1,780.


### 2026-06-18 19:10 Beijing - US-Iran MoU Lowers Oil Risk But Crypto Fails To Catch Bid

- Category: macro breaking / geopolitics / oil.
- Status: active market reaction.
- Source: AP, Reuters-syndicated Business Standard, CoinDesk market reaction.
- Confidence: medium-high for oil relief, medium for crypto transmission.
- Assets affected: BTC, ETH, SOL, oil, Nasdaq, inflation expectations.
- Why it matters: The US-Iran interim agreement and Hormuz reopening path lower oil-risk premium and should normally support risk assets through lower inflation pressure; however crypto is currently trading more on hawkish Fed repricing and ETF outflows than on geopolitical relief.
- Consensus / expected: Oil relief should support risk sentiment if yields/DXY confirm.
- Actual / confirmed: Oil fell after the MoU; CoinDesk reported stocks/futures lifted by the Iran deal while crypto still slid after the hawkish Fed.
- Surprise vs expected: Crypto did not catch the oil/geopolitical relief bid.
- Bullish path: oil keeps falling, yields/DXY fade, BTC holds 63.8K-64K and reclaims 65K, ETF flows return positive.
- Bearish path: Fed hike odds/ETF outflows dominate, BTC loses 63.8K-64K, ETH fails below 1,744, weekend $62K put hedges pull BTC lower.
- What to monitor: Brent/WTI, DXY above/below 100, 10Y yield around 4.5%, BTC 63.8K/65K, ETH 1,720/1,765, ETF flows, Jun 21 BTC $62K put positioning.
- Next update time: 2026-06-18 21:20 Beijing before U.S. equity cash-session impulse or immediately if BTC loses 63,800.
