# Templates

## Event Entry Template

```markdown
### YYYY-MM-DD HH:mm TZ - Event Name

- Category:
- Status: upcoming / active / past / breaking / resolved
- Source:
- Confidence: high / medium / low
- Assets affected:
- Why it matters:
- Consensus / expected:
- Actual / confirmed:
- Surprise vs expected:
- Bullish path:
- Bearish path:
- What to monitor:
- Next update time:
```

## Live Answer Template

```text
Main action: <exact enum only: open long / open short / hold long / hold short / close long / close short / flip long to short / flip short to long / trigger long / trigger short / no trade>
Action validity check: single enum / no slash / no conditional main action
Instrument:
Horizon:
Last / mark / index price + timestamp/source/freshness:
1H / 4H candle timestamp:
Order book timestamp/depth:
Funding / OI timestamp:
Data quality:
Unavailable / stale data:
Derivatives confirmation:
- Funding:
- OI 1h/4h/24h:
- Long/short:
- Liquidation:
- Taker/CVD:
- Basis:
- Options if relevant:
Cross-exchange conflicts:
Primary signal vote:
Decision ladder result:
No-trade / trigger boundary:
Event compression matrix:
Existing-position rule:
Hard blocks:
Soft downgrades:
EV / RR gate:
Scorecard:
Scorecard total:
Event risk:
Priced-in audit:
Crowding audit:
Root-cause chains:
- Scope: top 1-2 only.
- Bullish chain:
- Bearish chain:
- Trigger likelihood: qualitative only; do not add a second numeric probability
- Directional impact if triggered:
- Evidence required:
Subjective probability:
Confidence cap reason:
Entry trigger:
Trigger type: orderable / recheck-only / not applicable
Stop price:
Targets:
- T1:
- T2:
Risk/reward:
Position size class:
Invalidation event/price:
Do-not-hold-through event:
Why this is the highest-probability path:
Why not the opposite:
- For long: why not short.
- For short: why not long.
- For no trade: why not long / why not short / closer trigger.
- For close: why not hold / why not flip.
- For hold: why not close / why not flip.
Strongest opposite root-cause chain:
Forward scenario fork: <conditional; include only when a named future event/data release/expiry/geopolitical path can change the Main action before Next review time; otherwise omit>
- Current action lock: <repeat the single Main action; this block is not a second conclusion>
- Base path until review:
- Bullish fork trigger:
- Bearish fork trigger:
- Required confirmation:
- Confidence effect: none / soft downgrade / hard block
- If fork triggers: update only under What would change the decision
Equity-linked product check: <conditional; include only when the traded instrument, cited hedge, or execution vehicle is an ETF/ETP, ETF option, equity proxy, tokenized equity, or equity-linked/entity-anchored perp; otherwise omit>
- Product / venue / session:
- Underlying linkage:
- Product quote + timestamp/freshness:
- NAV / premium-discount / basis if relevant:
- Liquidity / spread / halt / market-session status:
- Borrow / options / corporate-action risk if relevant:
- Crypto-reference mismatch:
- Verdict for Main action: supports / downgrades / hard-blocks
Sources used:
What would change the decision:
Next review time:
```

For `no trade`, fill both:

```text
Trigger long:
Trigger short:
```

For `trigger long` or `trigger short`, `Entry trigger` is the actionable trigger. `Trigger type` must be `orderable` only when stop, T1/T2, and RR are valid; otherwise use `recheck-only` and list the data that must refresh before execution. Put the opposite-side trigger or invalidation under `What would change the decision`.

For `no trade` caused by missing critical facts, `Trigger long` and `Trigger short` may be `unavailable until [specific missing facts] refresh`; include the next review time.

Conditional blocks must not introduce a second trade conclusion, second subjective probability, or alternate `Main action`. They may only explain what keeps the current `Main action` valid, what downgrades it, or what would change the decision later.

The live answer must not end with balanced commentary. Put sources before the final two fields, then end with `What would change the decision` and `Next review time`.
