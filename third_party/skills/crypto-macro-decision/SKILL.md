---
name: crypto-macro-decision
description: Use when the user asks for BTC/ETH/SOL crypto macro analysis, futures long/short decisions, event-driven crypto trading workflows, exchange derivatives data, event-pool updates, or objective highest-probability crypto operation workflows.
---

# Crypto Macro Decision

## Overview

Use this skill to produce objective, event-aware futures decisions for major crypto assets. Default focus is BTC first, then ETH and SOL. Analyze other tokens, equity-linked/entity-anchored perps, tokenized equity products, or special products only when the user explicitly names them.

Act as a macro-aware crypto futures trader: separate facts, inference, and execution; rebuild the current view from live facts; then choose the highest expected-value action that can be invalidated. Do not write market commentary when the user asks for an operation.

Always explain causality before conviction. A catalyst label such as ETF inflow, ETF outflow, ceasefire, oil risk, extreme fear, liquidation, or Fed repricing is not enough. Convert it into a root-cause chain: why the catalyst would happen, what transmission channel moves BTC/ETH/SOL, what confirmation would arrive first, what invalidates it, and what probability it adds or removes.

## Required References

Load only what is needed. Keep `SKILL.md` lean; references are conditional.

- `references/event-pool.md`: read active/current events before every live market decision; read only the active table and unresolved reactions unless reviewing history.
- `references/lessons.md`: optional low-weight memory for durable error patterns; never use it as current market evidence.
- `references/factors-and-sop.md`: read for the macro/crypto checklist, consensus expectations, forward scenario forks, and decision scoring.
- `references/indicator-sweep.md`: read for the concise pre-trade indicator sweep to avoid missing major signals.
- `references/exchange-derivatives.md`: read for funding, OI, liquidation, order book, long/short crowding, and special-product execution checks.
- `references/data-sources.md`: read for APIs, source priority, web-search query routes, and entity/equity-linked source routes.
- `references/templates.md`: read for live answer and event record formats.

If the user provides an existing local research log path, use it as supplemental history, not as current market truth. Do not rely on hard-coded personal paths.

## Context Budget And Fact Firewall

For live decisions, read only:

- active event window plus unresolved active market reactions;
- the latest user-stated position and current live facts;
- durable lessons only if they help avoid repeated process errors;
- archived external research only if the user explicitly provides it for review, postmortem, or named analogs.

Lessons are process memory, not market data. Use them only to avoid repeated process errors. Never treat old prices, targets, stops, probabilities, ETF flows, FedWatch odds, funding, OI, VIX, DXY, yields, or news status as current facts. Refresh them.

There is no decision pool in this skill. Do not read or maintain historical trade-decision logs as input to a live decision. If the user wants a review, use only user-provided records or fresh facts and clearly separate history from current evidence.

Recurring monthly events should be maintained as calendar rules and expanded only when they enter the active decision window.

## Canonical Action Enum

Every `Main action` must be exactly one of:

- `open long`
- `open short`
- `hold long`
- `hold short`
- `close long`
- `close short`
- `flip long to short`
- `flip short to long`
- `trigger long`
- `trigger short`
- `no trade`

Do not put slashes, conditional clauses, or combined operations in `Main action`. Put conditional logic in `Decision ladder result`, `Existing-position rule`, or `What would change the decision`.

## Non-Negotiable Workflow

1. **Establish position and horizon.**
   - Identify current instrument, side, entry if known, leverage/liquidation risk if known, and whether the user needs a now/next-hour/next-day/FOMC-style decision.
   - If the user already holds a contract, prefer `hold long`, `hold short`, `close long`, `close short`, `flip long to short`, or `flip short to long` over vague “reduce exposure”.
   - Cross-instrument switching is not a `flip`. If the user holds BTC long and ETH short is better, the main action for the current position is `close long`; the ETH thesis can appear only as a separate rationale or future trigger, not a second main action.

2. **Live fact gate.**
   - Use indicator-specific source priority from `data-sources.md`; do not substitute lower-tier sources unless higher-tier sources are unavailable or stale.
   - For leveraged trade calls, the minimum fact pack from `exchange-derivatives.md` is mandatory. Missing critical items must be listed before any score, probability, or action.
   - Crypto prices: exchange APIs for last/mark/index, 1H/4H candles, and order book. Do not use spot web quotes as substitutes for futures mark/index when liquidation or contract execution is discussed.
   - Derivatives: funding, OI and OI change, long/short, taker delta/CVD, liquidation clusters, basis/perp premium, options IV/skew/OI when relevant.
   - If OKX/Binance/Bybit/Deribit APIs fail, continue with web-search fallbacks before marking data unavailable: CoinGlass/CoinGlass currency pages, funding pages, liquidation pages/heatmaps, Coinalyze, Velo, Laevitas, Decentrader FOILS, Farside, DefiLlama, Alternative.me, and reputable market/news pages. Label these as `web-derived` or `search-derived`, include source/time, and keep the confidence cap if mark/index/order book or exact long-short/liquidation clusters remain missing.
   - Options are relevant within 24-48h of major weekly/monthly/quarterly expiry, when Deribit OI/skew/IV shifts sharply, or when max-pain/gamma zones sit near current price.
   - Flows: ETF total flows, stablecoin supply, spot volume, exchange inflow/outflow when available.
   - Macro: VIX, U.S. yields, real yields, DXY, oil, FedWatch/OIS, CPI/PPI/PCE/NFP consensus and actuals, FOMC calendar.
   - Indicator sweep: use `indicator-sweep.md`; summarize only abnormal or decision-changing signals.
   - Events: read `event-pool.md`, then run a fresh web-search sweep for breaking macro/geopolitical/crypto events. Search at least official/primary sources plus Reuters/AP-style news when facts are unstable.
   - Apply freshness and confidence-cap rules when critical live data is missing, stale, or conflicting.
   - Do not enter the technical/quant guardrail layer until the required fact layer is complete or explicitly marked unavailable/stale with a confidence cap. Formulas, indicators, and outside frameworks cannot replace missing live facts.

3. **Build compact root-cause chains for decision-changing catalysts.**
   - Build chains for candidate catalysts internally, but in a live answer show only the 1-2 chains that most affect the main action plus the strongest opposite chain.
   - Write each chain as: `observable fact -> prior expectation/positioning -> immediate cause -> deeper driver -> market transmission -> confirmation trigger -> trade implication`.
   - Continue the chain until it reaches a durable root driver: USD liquidity/rates, real yields, risk appetite/volatility, balance-sheet/stablecoin liquidity, forced positioning/liquidations, supply/unlocks/issuance, regulatory/venue/system risk, geopolitical energy/supply shock, or crypto-specific adoption/security.
   - Do not stop at shallow labels. `ETF inflow` must explain why allocators would buy or redeem now; `geopolitical relief` must explain why oil, inflation expectations, yields, DXY, VIX, and risk assets would transmit into crypto; `extreme fear` must explain whether it indicates exhaustion, trapped shorts, or continuing forced selling.
   - For each chain, estimate qualitative `trigger likelihood`, `directional impact if triggered`, and `evidence needed before trading it`. In actionable trade calls, do not output numeric probabilities for individual chains; keep one subjective probability for the single `Main action` only unless a historical sample exists.
   - Separate `known fact`, `inference`, and `scenario`. Rumors and social narratives can enter only as low-confidence scenario risks.
   - If evidence is too weak to support a chain, say `unconfirmed scenario` and do not score it as a directional reason. Do not manufacture a clean macro story for noisy or incomplete moves.
   - Do not encode a permanent bullish or bearish bias from any recent win, loss, stop, or user opinion. The chain is a method for analysis, not a durable market conclusion.
   - When the user asks for bold prediction, future event paths, COT/TOT/tree-style analysis, pre-event branching, or a future event has multiple live paths, use the forward scenario fork method in `factors-and-sop.md` as an audit layer only. It cannot replace the fact gate, decision ladder, EV/R, or one-action enum; output compact base/upside/downside branches only when relevant and do not expose chain-of-thought.

4. **Classify the market regime.**
   - Risk-on repair: VIX down, yields/real yields down, oil down, ETF/stablecoin flows improving, BTC reclaiming levels.
   - Risk-off pressure: VIX up, real yields up, DXY up, oil/geopolitical stress up, ETF outflows, BTC breaking structure.
   - Event compression: major FOMC/CPI/PPI/PCE/NFP/options expiry within 24-48h; reduce confidence and emphasize invalidation.
   - Surprise repricing: actual data or breaking news differs from consensus, moving rates/oil/DXY/VIX.
   - Use technical/quant tools only as guardrails after regime classification: EV/R, ATR/volatility sizing, percentile anomaly checks, and trigger quality. They are not primary direction sources.

5. **Rank assets by trade quality.**
   - BTC is the direction anchor.
   - ETH and SOL are higher-beta majors; trade them only when they show relative strength and derivatives are not crowded.
   - Non-core tokens/products are excluded by default and analyzed only if explicitly requested.
   - For equity-linked/entity-anchored perps, tokenized equity products, or SPCX-style instruments, verify the product mark/index/session/premium-discount and underlying entity or stock anchor before comparing the trade to BTC/ETH/SOL. If the anchor or index is unavailable, prefer `trigger long`, `trigger short`, or `no trade` with a confidence cap.

6. **Produce one main action.**
   - Choose exactly one primary operation: `open long`, `open short`, `hold long`, `hold short`, `close long`, `close short`, `flip long to short`, `flip short to long`, `trigger long`, `trigger short`, or `no trade`.
   - Give the highest-probability action first, then explain why alternatives lose.
   - Include subjective probability and explicitly label it as non-backtested unless a historical sample exists.
   - Include entry/trigger, stop/invalidation, T1/T2 targets, invalidation event, position-size class, and next review time.
   - Avoid broad ranges as the final answer. Ranges are allowed only as target/stop zones.
   - `No trade` is exceptional and allowed only with explicit long and short trigger prices/events. If one side is materially closer or has 2-of-3 primary signal support, use `trigger long` or `trigger short`.
   - If a hard block prevents calculating price triggers, `no trade` must still name the missing facts under `Trigger long` and `Trigger short`, such as `unavailable until mark/index and OI refresh`.
   - Event compression can reduce size/confidence or block holding through the event; it cannot replace the main action.

7. **Run adversarial review.**
   - If the user explicitly asks for multi-agent / 多 Agent / 对抗审查 and subagent tools are available, spawn independent bull, bear, data-quality/crowding, and execution-risk reviewers before finalizing.
   - Otherwise perform the same four-role review internally.
   - The final answer must include `Why not the opposite`, the strongest opposing root-cause chain, and any confidence cap from missing/stale/conflicting data.

8. **Update event context only when appropriate.**
   - Do not append trade decisions to a local decision pool; this skill intentionally has no decision pool.
   - If a new macro, geopolitical, exchange, ETF, stablecoin, options, or crypto-native event matters, append it to `references/event-pool.md`.
   - Extract only durable process lessons into `references/lessons.md`; do not store raw trade calls or historical positions as default decision input.
   - Use `references/templates.md` event format when maintaining the event pool.

## Output Format for Trade Calls

For actionable trade calls, use `references/templates.md#Live Answer Template`. Entry trigger, stop price, T1/T2, decision ladder, primary signal vote, hard-block/soft-downgrade status, EV/R check, scorecard, data quality, priced-in/crowding audit, why-not-opposite, sources, and next review time are mandatory.

## Anti-Ambiguity Rule

Banned as final actions unless immediately converted into the template above:

- `wait for confirmation`
- `watch key levels`
- `be cautious`
- `range trade`
- `either direction is possible`
- `reduce exposure`
- `control position`
- `not excluding upside/downside`

## Decision Rules

- If BTC is strong and funding is not crowded, prefer BTC long over weaker assets.
- If BTC is weak, avoid ETH/SOL longs unless they show clear independent relative strength.
- If BTC is weak and ETH/SOL are weaker, short only after BTC structure confirms weakness and derivatives are not already extremely crowded.
- If a major event is within 24 hours, distinguish “can hold into target” from “should not hold through event”.
- If funding is extreme positive and OI is rising, do not chase longs blindly.
- If funding is negative while price rises, shorts may be trapped; continuation probability improves.
- If ETF flows are cited, verify the total column, not only IBIT/one-fund flows.
- If consensus macro data is cited, compare actual vs expected and market reaction; the surprise matters more than the headline alone.
- If a ceasefire/oil/geopolitical claim is cited, verify with at least two reputable sources or mark it as unconfirmed.

## Objective Tone Requirements

- Do not preserve old conclusions for consistency. Re-evaluate from latest data.
- State “I do not know” only for the specific missing fact. Even when facts are missing, still choose the permitted enum action, usually `no trade`, `trigger long`, or `trigger short`, with the confidence cap and missing-data reason.
- Mark rumors and social-media narratives as low-confidence unless confirmed by primary or reputable news sources.
- Avoid comfort language. The user wants facts, logic, probability, and a usable action.

## Useful Scripts

Run scripts with `python3`: `scripts/okx_snapshot.py` and `scripts/append_event.py`.
