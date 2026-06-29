# Factors And SOP

## Purpose

This reference defines the broad factor map and standard operating procedure for objective crypto futures decisions. Use it to avoid one-factor analysis and to force a full scan before recommending long, short, hold, close, switch, or no trade.

## Factor Map

Default asset universe:

- Core: BTC, ETH, SOL.
- Non-core tokens, equity-linked perps, meme coins, unlock trades, and special products only when the user explicitly asks.

### 1. Macro Liquidity

Track:

- Fed policy path: FOMC, dot plot, Powell press conference, Fed speakers.
- FedWatch/OIS/SOFR futures: market-implied rate path, next-meeting hike/cut/hold odds, and year-end implied policy rate.
- U.S. 2Y/10Y yields and 10Y real yield.
- DXY: dollar strength.
- Treasury issuance, TGA, RRP, bank reserves, QT/QE when relevant.

Interpretation:

- Falling real yields + falling DXY + easing Fed expectations = supportive for BTC.
- Rising real yields + stronger DXY + more hawkish Fed path = pressure on crypto, especially altcoins.
- Rate-cut odds rising because inflation cools is generally bullish; rate-cut odds rising because recession/credit stress is not automatically bullish.

### 2. Inflation And Growth

Track:

- CPI and core CPI.
- PPI and core/final demand components.
- PCE and core PCE.
- NFP, unemployment rate, initial claims.
- Oil, gasoline, shipping/geopolitical energy risk.
- Consensus expectations, prior values, actual values, and revisions.

Interpretation:

- Headline inflation from energy can fade if oil reverses.
- Core inflation persistence matters more for Fed policy.
- Strong employment can delay cuts; very weak employment can create recession risk.
- The market trades the surprise: actual vs consensus plus the reaction in yields, DXY, VIX, and Nasdaq.

### 3. Expectations And Surprise

Track before each scheduled data event:

- Release time and timezone.
- Consensus estimate.
- Prior reading and revisions.
- Whisper/market positioning if reputable.
- FedWatch/OIS change before and after the release.
- Immediate reaction in 2Y yield, 10Y yield, real yield, DXY, VIX, Nasdaq, BTC.

Interpretation:

- Hot inflation + yields up + DXY up = bearish for BTC/ETH/SOL.
- Cool inflation + yields down + DXY down = supportive.
- Weak growth data can be bullish only if it increases easing expectations without triggering recession/liquidity stress.
- If data is known in advance as consensus, the trade setup comes from positioning and surprise, not the existence of the event.

### 4. Risk Appetite

Track:

- VIX and, if available, MOVE.
- Nasdaq/QQQ, S&P 500, high-beta growth, AI/tech.
- Credit spreads.
- Market breadth.
- Cross-asset reactions after major news.

Interpretation:

- VIX under 20 and falling supports risk repair, but does not guarantee altcoin strength.
- VIX above 25 with rising yields is a warning for liquidation pressure.

### 5. Crypto Funding And Flow

Track:

- BTC ETF total net flows, not one-fund flows.
- Stablecoin supply.
- Exchange inflow/outflow, especially after unlocks.
- BTC dominance and total altcoin market cap.
- Spot volume and order-book depth.

Interpretation:

- ETF total inflow supports BTC only if large enough and persistent.
- Stablecoin expansion suggests more dry powder.
- Exchange inflow after unlocks can convert potential supply into actual sell pressure.

### 6. Derivatives Positioning

Track:

- Funding rate, annualized funding, and 7d/30d funding percentile when available.
- Open interest, OI 1h/4h/24h change, and OI/notional vs volume or market cap when available.
- Long/short ratio if available.
- Liquidation heatmaps by 1h/4h/24h/7d windows.
- Mark price vs last price.
- Index price vs last price.
- Perp basis / premium vs spot and dated futures basis when available.
- Taker buy/sell imbalance, CVD, or active buy/sell volume.
- Order-book depth, spread, bid/ask gaps, 1%/2% book imbalance, and obvious buy/sell walls.
- Perp volume vs spot volume, realized volatility, ATR/range expansion, and spot-perp divergence.

Interpretation:

- Price up + funding negative/flat = healthier long continuation; shorts may be trapped.
- Price up + funding extreme positive + OI rising = crowded long risk.
- Price down + OI rising + funding positive = trapped longs; potential cascade.
- Price up on perp OI expansion but weak spot volume = lower-quality rally and higher wick risk.
- Price down with OI falling and funding normalizing = deleveraging may be closer to exhaustion.
- Basis expanding too quickly can indicate leverage chase; basis compressing during a rally can indicate healthier spot demand.

### 6B. Priced-In And Crowding Audit

News is not direction; news is a volatility catalyst. A trade direction requires confirmation from macro, price structure, flows, derivatives, and risk/reward, and must be discounted if the market already priced it in.

Every actionable call must answer:

1. What is the new information?
   - Macro actual vs consensus.
   - Policy or FedWatch/OIS surprise.
   - ETF/stablecoin/spot-flow surprise.
   - Derivatives unwind or leverage rebuild.
   - Technical breakout/breakdown.
   - Breaking geopolitical, exchange, or regulatory event.
2. Is it already priced in?
   - Check price move before the event, funding extremity, OI change, long/short ratio, liquidation clusters, spot volume, BTC dominance, ETH/BTC, SOL/BTC, DXY/yields/VIX reaction.
3. Is the trade crowded?
   - Classify as `not crowded`, `mildly crowded`, `crowded but trending`, or `dangerously crowded`.
4. Apply adjustment:
   - If bullish news is already priced in and longs are crowded, reduce long score by 2-4.
   - If bearish news is already priced in and shorts are crowded, reduce short score by 2-4.
   - If price rises while funding is flat/negative and OI is not euphoric, increase long score by 1-3.
   - If price falls while funding remains positive and OI rises, increase short/cascade score by 1-3.
   - If bad news no longer makes new lows, do not add fresh short score from that news.
   - If good news no longer makes new highs, do not add fresh long score from that news.

### 6C. Root-Cause Chain Method

Every decision-changing catalyst must be traced beyond the headline. Do not stop at `ETF inflow`, `ETF outflow`, `ceasefire`, `oil risk`, `extreme fear`, `liquidation`, `Fed hawkish`, or `Fed dovish`. These are intermediate observations, not root causes.

Use this ladder:

```text
observable fact -> prior expectation / positioning -> immediate cause -> deeper driver -> market transmission -> confirmation trigger -> trade implication
```

Definitions:

- Observable fact: verified live data or confirmed news.
- Prior expectation / positioning: what consensus, options, funding, OI, ETF flow, price trend, or cross-asset market had already priced.
- Immediate cause: the direct reason the market is moving now.
- Deeper driver: the durable force behind the immediate cause.
- Market transmission: how that driver reaches BTC/ETH/SOL.
- Confirmation trigger: what must appear in price, rates, DXY, VIX, ETF/stablecoin flow, funding/OI, or order book before trading it.
- Trade implication: main action, trigger, invalidation, and probability change.

Durable root drivers:

- USD liquidity and policy path: Fed expectations, OIS/SOFR, QT/QE, Treasury issuance, TGA, RRP, reserves.
- Real yields and dollar: 2Y/10Y, real yield, DXY, USDCNH, global dollar funding.
- Risk appetite and volatility: VIX, MOVE, credit spreads, QQQ/NQ/ES, market breadth.
- Balance-sheet and stablecoin liquidity: stablecoin supply, exchange reserves, ETF primary-market creations/redemptions, dealer inventory.
- Forced positioning: funding, OI, liquidation clusters, basis, options gamma/skew/max pain, crowded long/short ratios.
- Supply and issuance: miner/treasury selling, unlocks for named non-core assets, exchange inflow, staking/unstaking, protocol supply changes.
- Venue and regulatory risk: exchange outages, withdrawal stress, ETF/regulatory actions, stablecoin issuer announcements.
- Geopolitical energy shock: oil, shipping chokepoints, inflation expectations, safe-haven dollar demand, risk-premium compression or expansion.
- Crypto-native adoption/security: ETF demand, chain activity, fees, TVL, bridge/security incidents, network outages.

Common causal chains:

- ETF inflow:
  `risk budget improves or allocation demand rises -> advisors/institutions create ETF shares -> APs/market makers source spot or futures hedge -> BTC spot absorption improves -> BTC structure firms -> ETH/SOL beta can follow only if relative strength confirms`.
  Confirmation: Farside total net inflow, issuer/official data, Coinbase premium or spot CVD, ETF volume vs average, BTC reclaim/hold levels, funding not euphoric.

- ETF outflow:
  `rates/real yields or risk stress raise hurdle rate -> allocators redeem or rebalance -> APs/market makers reduce exposure -> spot sell pressure or hedge unwind -> BTC rallies fail -> ETH/SOL underperform if beta appetite fades`.
  Confirmation: total net outflow, not just one fund; DXY/yields/VIX reaction; BTC failure at repair level; spot volume on sell moves; derivatives not already fully deleveraged.

- Stablecoin expansion:
  `dollar liquidity or offshore crypto demand improves -> USDT/USDC supply or exchange stablecoin balances rise -> market makers and spot buyers have more dry powder -> dips get absorbed`.
  Confirmation: stablecoin supply, exchange reserve/netflow, spot bid depth, lower slippage, rising spot share of volume.

- Stablecoin contraction:
  `risk reduction, redemption demand, regulation, or high T-bill opportunity cost drains stablecoins -> exchange buying power shrinks -> rallies lack follow-through`.
  Confirmation: supply decline, exchange reserve drop, thinner order books, lower spot volume, failed breakouts.

- Fed hawkish repricing:
  `inflation/growth data or Fed guidance pushes rate path higher -> real yields/DXY rise -> risk-asset discount rate rises and dollar liquidity tightens -> BTC multiple compresses -> ETH/SOL beta sells harder`.
  Confirmation: FedWatch/OIS shift, 2Y/10Y/real yield up, DXY up, QQQ/VIX response, BTC failing to reclaim structure.

- Fed dovish repricing:
  `inflation cools without recession stress or Fed guidance lowers path -> yields/DXY fall -> liquidity/risk appetite improves -> BTC demand improves -> ETH/SOL can outperform if funding is not crowded`.
  Confirmation: actual vs consensus, yields/DXY down, VIX down, QQQ/NQ strength, ETF/stablecoin/spot flow support.

- Recession-style cut expectations:
  `growth deteriorates or credit stress rises -> cuts are priced because risk is worsening -> VIX/credit stress rise and liquidity preference increases -> crypto can fall despite higher cut odds`.
  Confirmation: VIX/MOVE/credit up, equities weak, yields down for bad reasons, ETF outflows or stablecoin risk-off.

- Geopolitical escalation:
  `conflict raises energy/shipping risk -> oil and inflation expectations rise or safe-haven dollar demand rises -> yields/DXY/VIX pressure risk assets -> crypto sells if liquidity shock dominates`.
  Confirmation: oil spike, DXY/VIX up, yields reaction, equity weakness, BTC/ETH not absorbing.

- Geopolitical relief:
  `risk premium compresses -> oil/inflation pressure fades -> yields/DXY/VIX may fall -> risk assets repair -> crypto follows only if spot flow and BTC structure confirm`.
  Confirmation: oil down, VIX down, yields/DXY not rising, QQQ/NQ risk-on, BTC reclaim, ETF/stablecoin support.

- Extreme fear:
  `recent forced selling and negative sentiment reduce marginal sellers or trap shorts -> bounce/squeeze probability rises`; but also
  `ongoing redemptions, rising OI into decline, or thin liquidity can mean forced selling continues`.
  Confirmation for bounce: bad news no longer makes new lows, funding flat/negative, OI falling or shorts crowded, liquidation clusters above, spot bid absorption.
  Confirmation for cascade: price down with OI rising, funding still positive, exchange inflows, thin book, support break.

- Liquidation cascade:
  `leveraged longs/shorts cluster near obvious levels -> price sweeps stops/liquidations -> forced market orders accelerate move -> overshoot occurs until OI/funding normalize or spot absorbs`.
  Confirmation: liquidation heatmap clusters, OI/funding behavior, mark/index dislocation, order-book gaps, fast taker imbalance.

Root-cause output rule:

- For actionable calls, include only the top 1-2 root-cause chains ranked by decision impact, plus one compact opposite chain if material.
- Each chain must end with a practical trigger or invalidation.
- Do not add score for a chain unless the confirmation evidence is fresh enough for the trade horizon.
- If a catalyst is plausible but unconfirmed, put it in scenario risk and do not use it as the main reason.
- If the move is mostly microstructure/noise and no reliable deeper chain is confirmed, say so; do not invent a coherent macro story.

### 6D. Forward Scenario Fork Method

Use this only when the user asks for bold prediction, future event paths, COT/TOT/tree-style analysis, pre/post event branching, or when a named future event can change the trade before the next review time.

Forward scenario forks are trade-planning branches, not evidence and not a second decision engine. Run them after the live fact gate and root-cause chain work, before the final decision ladder, EV/R gate, and probability calibration. A fork may adjust the score only when the required confirmation is already fresh or the trade is explicitly a trigger waiting for that confirmation.

Separate labels:

- `known fact`: verified source with timestamp/freshness.
- `consensus`: market or economic expectation from a cited source.
- `inference`: derived from known facts, consensus, positioning, and market reaction.
- `scenario`: future path, not evidence.
- `rumor/whisper`: unconfirmed risk only; social media cannot be a main directional reason.

Branch rules:

- Use at most three branches: base path, bullish fork, bearish fork. Add a tail-risk fork only if it can hard-block execution before the next review.
- The base path must map to exactly one canonical `Main action`.
- Alternative forks define what would change the decision later; they must not create alternate `Main action` lines or a second subjective probability.
- Each fork must include: starting fact, prior expectation/positioning, root driver, transmission path, confirmation trigger, invalidation, priced-in/crowding effect, and trade implication.
- If a fork depends on an unverified catalyst, stale data, or missing funding/OI/mark/index/session data, mark it `unconfirmed scenario` and do not score it as a directional reason.
- Do not let "bold" mean unsupported conviction. A bold call requires fresh facts, clear trigger, valid stop, crowding audit, and falsifiable invalidation.

Falsification checklist:

- Price: what level/acceptance/breakdown proves the base path wrong.
- Event: what actual data, policy statement, or news confirmation invalidates it.
- Derivatives: what funding/OI/long-short/taker/liquidation shift invalidates it.
- Time: when the setup expires if confirmation does not arrive.

Probability discipline:

- Final answers provide one subjective probability for the main action only unless a historical sample exists.
- Branch likelihoods are qualitative only. If the user explicitly asks for branch odds, use relative labels such as `base stronger`, `upside weaker`, or `tail risk`; do not add numeric branch probabilities to the live answer.
- Scenario-only conclusions should stay in trigger territory; do not use them to force 60%+ confidence without price, macro bridge, and derivatives confirmation.

### 7. Asset-Specific Events

Track:

- BTC: ETF flows, dominance, miner/treasury flows, options expiry, macro sensitivity.
- ETH: ETF/staking/regulatory developments, ETH/BTC trend, on-chain fees, L2 activity.
- SOL: SOL/BTC and SOL/ETH relative strength, ecosystem flows, chain stability, major unlocks only if relevant.
- Non-core assets: unlocks, upgrades, listings, chain outages, TVL/stablecoin/DEX volume only when explicitly requested.
- Equity-linked/entity-anchored perps and tokenized equity products: verify product rules, mark/index/oracle, session status, premium/discount or basis, liquidity/spread, and the underlying entity/equity catalyst only when explicitly requested.

Interpretation:

- Single-token events rarely overpower macro risk-off.
- Good news in weak liquidity can become exit liquidity.
- Special event products require premium/discount and rule analysis, not simple narrative trading.
- Do not confuse the value of the underlying company, stock, IPO story, or industry theme with the executable perp price. The product's mark/index, liquidity, funding/OI, session state, and premium/discount can dominate trade quality.

## Standard Operating Procedure

1. State current user position.
2. Pull live exchange data for BTC/ETH/SOL, plus user-held instrument.
3. Pull macro, consensus expectations, FedWatch/rate path, and breaking-event data.
4. Read active event pool only; do not read historical trade-decision logs for live direction.
5. Classify regime: risk-on, risk-off, event-compressed, or surprise repricing.
6. Confirm the fact gate:
   - If required facts are fresh, continue.
   - If required facts are unavailable/stale/conflicting, mark them and apply the confidence cap before any scoring.
   - Do not let technical indicators, EV/R, ATR, or outside frameworks fill missing facts.
7. Build root-cause chains for the top bullish and bearish catalysts.
8. If the user asks for future-event branching or a named future event can change the trade before review, run the forward scenario fork method as an audit layer.
9. For explicitly requested equity-linked/entity-anchored products, verify product mark/index/session/premium-discount and underlying entity/equity facts before scoring.
10. Score BTC first, then ETH/SOL or user-held asset.
11. Run the primary signal vote: BTC structure, macro bridge, derivatives.
12. Compare asset strength:
   - BTC vs ETH/SOL.
   - ETH/BTC and SOL/BTC.
   - User-requested non-core asset vs BTC/ETH/SOL only when needed.
13. Audit priced-in/crowding and run why-not-opposite.
14. Apply the decision priority order, including decision ladder, hard-block/soft-downgrade rules, event matrix, EV/R gate, and existing-position rules.
15. Decide exactly one action:
   - Open long.
   - Open short.
   - Hold existing long.
   - Hold existing short.
   - Close long.
   - Close short.
   - Flip long to short.
   - Flip short to long.
   - Trigger long.
   - Trigger short.
   - No trade with explicit long and short triggers.
16. Give entry/trigger, stop, T1/T2, invalidation event, do-not-hold-through event, and next review time.
17. If a new event matters, update the event pool; do not append trade decisions to a local decision pool.

## Hard Decision Heuristics

- If BTC is strong and funding is not crowded, prefer BTC long over weaker assets.
- If BTC is weak, avoid ETH/SOL longs unless they show clear independent relative strength.
- If BTC is weak and ETH/SOL are weaker, short only after BTC structure confirms weakness and derivatives are not already extremely crowded.
- If a major event is within 24 hours, distinguish `can hold into target` from `should not hold through event`.
- If funding is extreme positive and OI is rising, do not chase longs blindly.
- If funding is negative while price rises, shorts may be trapped; continuation probability improves.
- If ETF flows are cited, verify the total column, not only IBIT/one-fund flows.
- If consensus macro data is cited, compare actual vs expected and market reaction; the surprise matters more than the headline alone.
- If a ceasefire/oil/geopolitical claim is cited, verify with at least two reputable sources or mark it as unconfirmed.
- Price near support plus crowded shorts means do not chase shorts without breakdown confirmation.
- Price near resistance plus crowded longs means do not chase longs without acceptance above resistance.

## Why-Not-Opposite Check

Before finalizing the main action, explicitly test the opposite trade.

For a proposed long, answer:

- Why not short here?
- What bearish evidence is strongest?
- What is the bearish root-cause chain?
- Why is that evidence not enough to override the long?
- What exact price/event would prove the short thesis is taking control?

For a proposed short, answer:

- Why not long here?
- What bullish evidence is strongest?
- What is the bullish root-cause chain?
- Why is that evidence not enough to override the short?
- What exact price/event would prove the long thesis is taking control?

For no trade, answer:

- Why not long?
- Why not short?
- Which side has the closer trigger?

## Scoring Guide

Use subjective scoring unless a backtest exists.

Before choosing an action, produce a compact scorecard. This is a decision aid, not a substitute for the fact gate. Use weighted score ranges below; do not keep a second threshold system.

| Factor | Score |
|---|---:|
| BTC structure and momentum | -4 to +4 |
| Macro bridge: rates, DXY, VIX, oil, cross-asset | -4 to +4 |
| Derivatives: funding, OI, liquidations, basis | -4 to +4 |
| Spot/ETF/stablecoin flows | -2 to +2 |
| Asset relative strength vs BTC | -2 to +2 |
| Inflation/growth surprise vs consensus | -2 to +2 |
| Technical confirmation / execution quality | -2 to +2 |
| Event risk / time compression | -3 to 0 |
| Priced-in adjustment | -3 to +1 |
| Crowding adjustment | -3 to +1 |
| Auxiliary sentiment/on-chain/options | -1 to +1 |

Quick scoring summary:

- Direction is led by BTC structure, macro bridge, and derivatives.
- Flows, relative strength, and inflation/growth surprise confirm or weaken the direction.
- Technical confirmation is execution quality, not a direction replacement.
- Event risk, priced-in, and crowding mostly downgrade confidence, size, or action class.
- Missing required facts apply confidence caps before scoring.

Technical confirmation is a low-weight guardrail. It can use EMA20/50/200, 4H/1D structure, ADX/trend strength, VWAP/anchored VWAP, ATR/BB width/squeeze, and spot/perp volume confirmation. It cannot override two opposing primary signals or missing required facts.

## Decision Priority Order

Apply decision gates in this order:

1. Fact gate and data freshness.
2. All-direction hard blocks: unverified main catalyst, missing critical facts, or negative EV/R after levels are defined.
3. Event compression matrix.
4. Existing-position rules if the user has a position.
5. Primary signal vote.
6. Weighted score ladder.
7. No-trade / trigger boundary.
8. Priced-in and crowding downgrade.
9. EV/R execution gate.
10. Probability calibration.

If rules conflict, the earlier gate wins. Probability calibration never overrides fact gate, hard blocks, event compression, existing-position rules, or EV/R.

Threshold roles:

- Score ladder determines directional bias and default action class.
- Event matrix changes whether that bias can be traded now, held through, or only expressed as a trigger.
- EV/R gate decides whether the execution level is tradable.
- Confidence caps limit probability and size when facts are missing, stale, or conflicting.
- Probability calibration communicates confidence only; it does not select the action by itself.
- Scorecard priced-in/crowding rows are preliminary adjustments included in the weighted total. The later priced-in/crowding gate may only downgrade action class or size when new evidence appears after scoring, and must not double-count the same evidence.

## Primary Signal Vote

The three primary direction signals are:

1. BTC structure and momentum.
2. Macro bridge: rates, DXY, VIX, oil, Nasdaq/QQQ/cross-asset.
3. Derivatives confirmation: funding, OI, long/short, liquidation, basis, taker flow.

Rules:

- If all three are bullish, final action cannot be plain `no trade`; choose `open long` or `trigger long` unless a hard block exists.
- If all three are bearish, final action cannot be plain `no trade`; choose `open short`, `trigger short`, `hold short`, `close long`, or `flip long to short` unless a hard block exists.
- For an existing long, all three bearish means `close long` or `flip long to short` if the short trigger and EV/R are valid.
- For an existing short, all three bullish means `close short` or `flip short to long` if the long trigger and EV/R are valid.
- For an existing long, all three bullish means `hold long` unless the position has already reached target or forward EV/R is negative.
- For an existing short, all three bearish means `hold short` unless the position has already reached target or forward EV/R is negative.
- If 2 of 3 align and the third is neutral/unavailable, follow the aligned side with a confidence cap and prefer trigger/smaller size.
- If 2 of 3 align and the third strongly opposes, use trigger order unless price already confirmed breakout/breakdown with valid EV/R.
- If all three conflict or are mixed, `no trade` is allowed, but name the closer trigger.

## Decision Ladder

Use the weighted total after fact-gate and confidence-cap rules:

- `>= +8`: main action must be `open long` or `hold long`, unless hard-blocked by event, RR, data quality, or dangerous long crowding.
- `+4 to +7`: main action defaults to `trigger long`; allow small `open long` only if price has accepted above trigger and RR is valid.
- `-3 to +3`: new position defaults to `no trade` only if neither trigger is active; existing position follows existing-position rules.
- `-4 to -7`: main action defaults to `trigger short`; allow small `open short` only if breakdown is confirmed and RR is valid.
- `<= -8`: main action must be `open short`, `hold short`, `close long`, or `flip long to short`, unless hard-blocked by event, RR, data quality, or dangerous short crowding.

If the user already has a position, use the ladder to determine directional bias, then map it through `Existing Position Rules`. Existing-position actions override generic open/hold ladder actions.

Medium scores should become `trigger long` or `trigger short`, not vague commentary. `No trade` is reserved for genuinely mixed/blocked setups.

## No-Trade / Trigger Boundary

Trigger semantics:

- `trigger long` or `trigger short` means no market entry now.
- Enter only if the trigger price/event occurs and hard blocks remain absent at trigger time.
- A conditional order is appropriate only when stop, target, and RR are already valid; otherwise the trigger means recheck before execution.

Use `no trade` only after primary vote and ladder checks fail to produce a side:

- Weighted score is between -3 and +3.
- Primary signals are mixed, unavailable, or 1 bullish / 1 bearish / 1 neutral.
- Neither long trigger nor short trigger is currently active.
- Distance to both triggers is meaningful or RR before trigger is poor.
- User has no existing position, or existing position is already invalidated/closed.

Event-window definitions:

- 24-48h before a major event: event watch/downgrade. Apply confidence cap if consensus, actual path, or market reaction is unclear.
- 6-24h before a major event: trigger/size-cap zone. Prefer triggers or hold-to-nearby-target over fresh market entry.
- Under 6h before a major event: no fresh market entry unless post-event repricing already occurred.

Under 6h mapping:

- Empty account: use `trigger long`, `trigger short`, or `no trade`; do not use fresh `open long` or `open short` unless the event already repriced.
- Existing profitable position: `hold long` / `hold short` only to a nearby target with protected stop; otherwise `close long` / `close short`.
- Existing losing or invalidated position: `close long` / `close short`; do not average down.

Use `trigger long` when:

- Score is +4 to +7, or primary signals are 2-of-3 bullish.
- Price has not yet accepted above the execution level.
- Event/crowding/RR risk blocks immediate market long.
- Short thesis invalidation is explicit.

Use `trigger short` when:

- Score is -4 to -7, or primary signals are 2-of-3 bearish.
- Price has not yet broken/accepted below the execution level.
- Support/liquidation-sweep/RR risk blocks immediate market short.
- Long thesis invalidation is explicit.

If `no trade` is selected, state which trigger is closer. If the distance from current price to one trigger is at least 0.5 ATR smaller than the distance to the opposite trigger, convert `no trade` into that side's trigger unless blocked by RR or event risk. If primary signals are 2-of-3 for one side, do not enter `no trade`; use that side's trigger.

## Hard Blocks And Soft Downgrades

All-direction hard blocks prevent directional trade calls beyond close/no-trade. They also block `trigger long` and `trigger short` because a directional trigger still depends on a directional thesis:

- Critical current price, candles, funding, OI, or active event status is missing.
- Unverified breaking news is the main catalyst.
- EV is negative or RR is below the minimum gate after stop and target are defined.

Fresh-entry hard blocks prevent new market entry but still allow triggers, close, or hold because core execution facts are present:

- Core primary signals are fully mixed.
- Dangerous crowding in the same direction plus price at support/resistance without acceptance/breakdown.

Soft downgrades allow trigger or smaller size:

- Liquidation/order book/CVD unavailable while price + macro + exchange-native derivatives align.
- ETF/stablecoin data unavailable but not used as a support reason.
- Options data unavailable outside a major expiry window.
- Major event is 6-24h away but trigger and invalidation are explicit.

## Event Compression Action Matrix

- 24-48h before a major event: classify as event watch/downgrade. Do not let technical breakouts alone raise confidence; shorten next review time.
- Major event more than 24h away: directional action is allowed if score threshold is met; reduce size one class if the event risk is unresolved.
- Major event 6-24h away: strong score uses trigger or hold-to-nearby-target; avoid fresh market entry unless price already confirmed and RR >= 1.5.
- Major event under 6h away: no fresh market entry unless post-event repricing already occurred; close invalidated positions; do not average down.
- After event: trade the surprise only after actual vs consensus and reaction in yields/DXY/VIX/BTC are verified.

## EV / RR Gate

EV/R is an execution gate, not a direction source.

- Fresh market entry requires expected T1 RR >= 1.2 and T2 RR >= 1.8, or a clearly explained event-reaction scalp.
- If direction score is strong but RR is poor, output `trigger long` or `trigger short` at a better level.
- If both direction and RR are poor, output `no trade`.
- `hold long` or `hold short` requires forward EV/R from the current price to remaining target vs invalidation, or a clear reason that closing now has worse expected value.
- `close long` or `close short` requires thesis invalidation, negative/poor forward EV/R, hard block, event boundary, or target completion.
- `flip long to short` or `flip short to long` must satisfy both sides: the existing position has a close condition and the opposite side has a valid trigger/open condition with EV/R.
- EV proxy: `EV = p_win * weighted_reward - (1 - p_win) * risk - fees/slippage - event_or_liquidation_penalty`.
- If exact values are unavailable, label `EV qualitative` as positive / neutral / negative. Negative means expected reward is smaller than risk after fees/slippage/event penalties, or RR is below the minimum gate.
- EV must account for stop distance, target distance, fees/slippage, and event/liquidation risk qualitatively when exact values are unavailable.

## Existing Position Rules

Existing long:

- Score >= +4 and invalidation not hit: `hold long`.
- Score +1 to +3: `hold long` only if price remains above stop and event risk is not under 6h; otherwise `close long` at market or on the next predefined exit trigger.
- Score -1 to -3: `close long` unless target is very near and stop is protected.
- Score <= -4: `close long`; `flip long to short` only if short trigger is active or BTC breakdown confirmed.
- Score <= -8 with confirmed breakdown: `flip long to short`.

Existing short:

- Score <= -4 and invalidation not hit: `hold short`.
- Score -1 to -3: hold only if price remains below stop and event risk is not under 6h.
- Score +1 to +3: `close short` unless target is very near.
- Score >= +4: `close short`; `flip short to long` only if long trigger is active or BTC reclaim confirmed.
- Score >= +8 with confirmed reclaim: `flip short to long`.

## Probability Calibration

- 52%-55%: trigger only; no fresh market entry.
- 56%-59%: trigger action or small-size hold; avoid fresh market entry unless already confirmed.
- 60%-68%: market action allowed if trigger is active, RR valid, and no hard block exists.
- Above 70%: avoid unless backed by very clear evidence.

Final answers should provide one subjective probability for the main action only. Alternative paths may appear in `Why not the opposite` or `What would change the decision` as qualitative conditions, not as competing numeric probabilities or main conclusions.

Probability calibrates confidence only. It cannot override the fact gate, event matrix, hard blocks, existing-position rules, decision ladder, or EV/R gate. Always label as subjective probability unless backtested.
