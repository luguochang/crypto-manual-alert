# Indicator Sweep

Use this concise sweep before any live BTC/ETH/SOL futures decision. Do not explain every item in the final answer; surface only signals that change the action, probability, target, stop, or next check time.

## 15-Point Sweep

| Area | Indicator | Check | Trade Use |
|---|---|---|---|
| Price anchor | BTC 1H/4H structure | Reclaim/break key levels, higher high/lower low | Do not long ETH/SOL against weak BTC |
| Relative strength | ETH/BTC, SOL/BTC, SOL/ETH | Stronger or weaker than BTC | Choose BTC when majors lag |
| Derivatives | Funding rate | Cross-exchange level, annualized rate, 7d/30d percentile | Avoid crowded side; negative funding + rising price can squeeze shorts |
| Derivatives | Open interest | OI 1h/4h/24h change, OI/volume, OI/market cap | Detect fresh leverage, short covering, or trapped longs |
| Derivatives | Long/short + taker delta/CVD | Crowd leaning one way? Active buyers or sellers? | Penalize trades that chase a crowded side |
| Liquidation risk | Liquidation heatmap / obvious stop clusters | 1h/4h/24h/7d clusters above/below | Set invalidation away from obvious sweep zones |
| Microstructure | Order book + spread + depth | 1%/2% depth, imbalance, buy/sell walls | Avoid entries into thin books or obvious sweep zones |
| Basis | Perp premium / dated futures basis | Perp vs spot and CME/quarterly basis | Detect leverage chase vs spot-led demand |
| Volume/volatility | Spot/perp volume, ATR, realized vol | Breakout has volume? Range expanding? | Filter low-liquidity false breaks |
| Options | BTC/ETH max pain + expiry OI + IV/skew | Weekly/monthly expiry pressure, put/call skew | Beware pinning, gamma zones, or volatility release |
| Flows | BTC ETF total net flow | Total inflow/outflow, not one fund | Persistent inflow supports BTC; outflow weakens rallies |
| Liquidity | Stablecoin supply / exchange dry powder | Expanding/contracting, USDT/USDC peg, exchange stablecoin inflow | Expansion supports risk appetite; contraction lowers dip-buying power |
| Sentiment | Fear & Greed Index | Extreme fear/greed and change vs prior day/week | Contrarian input only; not a standalone signal |
| Cycle/on-chain | MVRV, NUPL, SOPR if available | Profit/loss regime and realized selling | Useful for cycle context, weaker for intraday entries |
| Macro bridge | FedWatch, 2Y/10Y, real yield, DXY, VIX, oil | Direction after latest data/news | Macro confirmation can override crypto-only signals |
| Cross-asset | QQQ/NQ, ES, credit, gold, USDCNH | Risk appetite and dollar-liquidity impulse | Crypto often follows global risk/liquidity in stress |

## Source Routes

- Day1Global BTC model is checklist inspiration only, not a live data source and not a file to read unless the user explicitly asks.
- OKX public API for BTC/ETH/SOL price, funding, OI, mark/index, candles, books.
- CoinGlass for funding heatmap, OI, liquidation heatmap, long/short, taker flow, options/max pain.
- Farside or equivalent for BTC ETF total net flows.
- DefiLlama for stablecoin supply and DeFi liquidity context.
- Alternative.me Fear & Greed API for sentiment.
- Glassnode/CryptoQuant/LookIntoBitcoin-style sources for MVRV/NUPL/SOPR when accessible.
- CME FedWatch, Treasury/FRED/Cboe and reputable market data for rate path, yields, VIX, DXY, oil.

## Minimal Final Signal Rule

After scanning, classify each bucket as `bullish / bearish / neutral / unavailable`. If 3+ high-quality buckets conflict, lower confidence and prefer `no trade` or tighter invalidation. If BTC structure, macro bridge, and derivatives all align, allow a clearer long/short call.

## Fact Gate Before Guardrails

The sweep has two layers:

1. Required fact layer: live price/mark/index, BTC structure, funding/OI, macro bridge, event status, and relevant flows/derivatives.
2. Guardrail layer: EV/R, ATR/volatility sizing, technical confirmation, z-score/percentile anomalies, and outside framework references.

Never use the guardrail layer to replace a missing required fact. If a required fact is missing, stale, or contradictory, mark it and apply the confidence cap before any technical/quant discussion.

## Confidence Downgrade Rules

Do not treat missing data as neutral. Mark it `unavailable` or `stale`, then cap confidence.

- If current last/mark/index price, 1H/4H candles, funding, OI, or major event status is missing for the traded instrument or active event window, treat it as a core execution hard block: use `no trade` for new positions, or `close long` / `close short` only when an existing position is invalidated. Do not use directional triggers until the core facts refresh.
- If liquidation, long/short, taker flow/CVD, or order book is unavailable, cap probability at 55%-58% unless price structure and macro are strongly aligned.
- If basis/perp premium is decision-relevant and unavailable, do not use spot-led vs leverage-led quality as support; cap confidence one tier if this distinction matters to the thesis.
- If FOMC/CPI/PPI/PCE/NFP or major geopolitical news is in the 24-48h window and consensus/actual/market reaction cannot be verified, cap probability at 52%-55% and avoid high-leverage hold-through.
- If ETF/stablecoin data is decision-relevant and unavailable/stale, cap confidence one tier and do not use flows in the primary signal vote or as support.
- If options data is missing within 24-48h of major weekly/monthly/quarterly expiry, lower confidence and shorten next review time.
- If news is unconfirmed or only social-media sourced, treat it as risk, not fact; it cannot be the main trade reason.
- If cross-source derivatives conflict, mark `mixed derivatives` and reduce confidence by 5-10 percentage points or convert to a trigger plan.
- Stale data is missing data. Use freshness rules in `data-sources.md`.

Confidence caps:

- Fresh critical data and aligned macro/structure/derivatives: 60%-68% is allowed; higher requires unusually clear evidence and must be labeled non-backtested.
- Structure + derivatives + macro align but some auxiliary data is missing: 58%-62%.
- Only price structure is strong while derivatives or macro are missing: 52%-56%.
- Major event nearby with incomplete data: 50%-55%.
- Core data conflict, core execution facts missing, or unconfirmed news as main catalyst: no directional main call; use `no trade` or close invalidated existing positions until facts refresh.
