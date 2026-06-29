# Durable Lessons

Compact lessons extracted from prior crypto macro decisions. Use this file as low-weight memory, not as market evidence.

## Read Policy

- Read only when a live decision needs historical error-pattern awareness.
- Do not treat any price, target, stop, macro fact, ETF flow, funding, OI, or event status here as current.
- If a lesson conflicts with fresh facts, fresh facts win.

## Lessons

### Fact Refresh Beats Continuity

Prior conclusions must not be preserved for consistency. Every live answer must rebuild price, macro, event, and derivatives facts before choosing an action.

### BTC Is Direction Anchor, Not Always Best Futures Vehicle

BTC often gives the cleanest market-direction signal, but high-beta majors or explicitly requested event products can have better expected move. Separate conservative direction anchor from trade-quality ranking.

### Asset Selection Error Matters

When the user recently discussed non-core products, keep them only as a temporary named watchlist if explicitly requested. Do not let them pollute the default BTC/ETH/SOL universe, but do compare expected move vs wick/liquidation risk when the user asks.

### Event Compression Changes Execution

Before FOMC, CPI, PPI, PCE, NFP, major options expiry, or geopolitical shocks, distinguish:

- can hold to nearby target;
- should not hold through event;
- trigger-only because fresh market entry has poor event-adjusted EV/R.

### Failed Rebound Is Different From Market Chase

`trigger short` or `trigger long` means the trade is valid only if the trigger condition appears. If price runs directly to target without trigger, do not chase. If invalidation is reclaimed, cancel the setup.

### Extreme Fear Is A Downgrade, Not Automatic Long

Extreme fear can raise squeeze/bounce risk and should reduce size or force trigger execution. It does not justify a long unless BTC structure, macro bridge, and derivatives confirm repair.

### Missing Derivatives Caps Confidence

If mark/index/funding/OI/order book/long-short/liquidation/CVD are unavailable, do not label a futures entry high confidence. Prefer `trigger`, smaller size, or `no trade` depending on EV/R and event risk.

### Catalyst Labels Need Root-Cause Chains

Do not treat ETF flow, geopolitical headlines, extreme fear, liquidation, or Fed repricing as complete reasoning. Trace each decision-changing catalyst through expectation, deeper driver, market transmission, confirmation trigger, and invalidation before assigning probability or action.

### Vague Operations Are Failure Modes

Avoid final actions such as reduce, watch, wait, cautious, switch, or open/hold. Convert every actionable result into exactly one enum action from `SKILL.md`.
