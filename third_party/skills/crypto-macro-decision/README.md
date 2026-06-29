# Crypto Macro Decision Skill

`crypto-macro-decision` 是一个面向 Codex 的加密货币宏观与合约决策 skill。它默认聚焦 `BTC`、`ETH`、`SOL` 三个主流资产，用实时行情、衍生品结构、宏观事件、资金流、市场情绪和事件池来辅助生成更可执行的合约操作方案。

这个 skill 的核心目标不是预测一个“绝对正确答案”，也不是自动交易，而是把交易前必须检查的事实、风险和决策规则固定下来，减少临场只看单一新闻、只看价格涨跌、或者被上一轮判断锚定的问题。

> 状态：实验性研究流程。本项目不是投资建议、交易建议或自动交易系统。

## 适用范围

默认分析对象：

- `BTC-USDT-SWAP`
- `ETH-USDT-SWAP`
- `SOL-USDT-SWAP`

非核心资产、meme、解锁币、股票映射合约、特殊事件产品只在用户明确点名时进入分析。默认不主动分析 AVAX、SPCX、meme、股票映射币或其他小币，避免噪音污染 BTC/ETH/SOL 主线判断。

适合的问题类型：

- 当前 BTC / ETH / SOL 合约应该做多、做空、持有、平仓还是等待触发。
- 已经持有多单或空单时，判断继续持有、平仓、反手，还是设触发条件。
- FOMC、CPI、PPI、PCE、非农、期权交割、地缘事件前后，如何处理合约风险。
- 复盘用户提供的某次决策，但复盘记录不作为下一次实时判断的默认输入。
- 维护事件池，避免漏掉未来宏观、地缘、交易所、ETF、稳定币、期权和链上事件。

不适合的问题类型：

- 自动下单或托管交易。
- 保证收益、保证胜率、无止损重仓。
- 不刷新实时事实，只根据历史记录给当前交易结论。
- 用单一技术指标或单一新闻直接判断多空。

## 核心思想

这个 skill 的分析顺序是：

```text
先确认事实
再判断宏观与市场状态
再检查衍生品和拥挤度
再做主信号投票和评分
再经过事件、EV/R、持仓规则裁判
最后只能输出一个主操作
```

也就是说，结论不是先凭感觉说“看多/看空”，再找理由补上，而是从数据和事件逐层过滤。

### 1. 事实层优先

实时决策必须先刷新事实。事件池只能提示要检查哪些未完结事件，不提供当前行情结论。这个 skill 不维护决策池，也不读取历史交易观点作为实时判断输入。

必须优先刷新：

- 当前 last / mark / index price。
- BTC 1H / 4H 结构。
- 订单簿深度、spread、买卖墙。
- funding、下一次 funding 时间。
- OI 当前值和 1h / 4h / 24h 变化。
- long/short、taker flow、CVD。
- liquidation heatmap。
- basis / perp premium。
- BTC / ETH options：IV、skew、max pain、expiry OI。
- BTC / ETH ETF flows。
- stablecoin supply 和可用时的交易所 stablecoin reserve / netflow。
- VIX、DXY、美债收益率、实际收益率、油价、Nasdaq / QQQ。
- FedWatch / OIS / SOFR implied path。
- CPI、PPI、PCE、NFP、FOMC 等事件的 consensus、actual、market reaction。
- 地缘、油价、监管、交易所、链上事故等突发新闻。

如果关键事实缺失，不能把缺失当中性。必须写成 `unavailable` 或 `stale`，并降低主观概率上限。

### 2. 技术和量化只是护栏

技术指标不会替代事实层。EMA、VWAP、ATR、ADX、BB width、z-score、percentile、EV/R 等只用于确认执行质量、止损距离、波动状态和异常拥挤，不作为独立方向来源。

例如：

- BTC 结构、宏观桥、衍生品三者都偏空时，不能因为一个短周期 RSI 低就直接看多。
- funding/OI/order book 缺失时，不能用均线金叉代替衍生品事实。
- 方向偏空但当前价位离目标太近时，EV/R 可以阻止追空，转为 `trigger short`。

### 3. BTC 是方向锚

BTC 是默认方向锚。ETH 和 SOL 是高 beta 主流资产，只有在相对 BTC 有强度、并且衍生品不拥挤时，才优先交易 ETH 或 SOL。

基本规则：

- BTC 强且 funding 不拥挤，BTC 多单通常比弱 alt 多单更干净。
- BTC 弱时，默认不做 ETH/SOL 多，除非 ETH/BTC、SOL/BTC 明显独立走强。
- BTC 弱且 ETH/SOL 更弱时，做空要等待 BTC 结构确认，并检查空头是否已经过度拥挤。

### 4. 新闻不是方向，预期差才是方向来源之一

这个 skill 不把新闻标题直接当方向。任何宏观或地缘事件都要拆成：

- 市场原本预期什么。
- 实际发生什么。
- 与预期相比是鹰派、鸽派、通胀、衰退、风险偏好改善，还是风险偏好恶化。
- 美债收益率、DXY、VIX、油价、Nasdaq、BTC 是否确认这个方向。
- 市场是否已经提前定价。

例如，FOMC 不只是看“加息/降息/不变”，还要看 dot plot、Powell、通胀预测、失业率预测、FedWatch/OIS 变化，以及市场反应。

### 5. 根因链，不停在表面催化剂

这个 skill 现在强制使用 `root-cause chain`。原因是很多交易判断会停在表面标签，例如：

- ETF 流入，所以看多。
- ETF 流出，所以看空。
- 地缘缓和，所以看多。
- 极度恐慌，所以会反弹。
- OI 上升，所以要爆仓。

这些说法都不够。它们只是中间现象，不是根因。

根因链的标准格式是：

```text
可观察事实 -> 市场原本预期/仓位 -> 直接原因 -> 更深层驱动 -> 传导路径 -> 确认触发 -> 交易含义
```

举例，不能只写“ETF 流入利多”，而要写清楚：

```text
风险预算改善或资产配置需求上升
-> 机构/顾问创建 ETF 份额
-> AP/做市商需要买入现货或做对冲
-> BTC 现货承接改善
-> BTC 结构修复
-> ETH/SOL 只有在相对强度确认时才跟随
```

举例，也不能只写“地缘缓和利多”，而要写清楚：

```text
冲突风险溢价下降
-> 油价和通胀预期压力下降
-> 美债收益率/DXY/VIX 如果同步回落
-> 风险资产修复
-> BTC 如果重新站回关键结构位
-> 才能把地缘缓和计入多头理由
```

每条根因链必须回答：

- 这个催化剂为什么会发生。
- 它通过什么路径影响 BTC / ETH / SOL。
- 哪些数据先确认，哪些数据会证伪。
- 触发概率是多少。
- 如果触发，应该影响方向、仓位、止损还是复查时间。

实时答案不需要把所有可能原因都展开。只输出最影响主操作的 1-2 条根因链，再给出一条最强反方根因链。证据不足的故事必须标成未确认场景，不能为了让结论显得完整而硬凑宏观叙事。

根因链不会把某一次判断写成永久结论。它只规定分析方法：每次都从最新事实重新推导，不能因为上一次止损、上一次做对、或者用户主观看法，固定偏多或偏空。

### 6. 合约市场是半透明市场

合约交易必须看衍生品结构，而不是只看现货价格。

重点包括：

- funding 是否极端。
- OI 是新杠杆进入、空头回补、多头被困，还是去杠杆。
- long/short 是否单边。
- liquidation cluster 在价格上方还是下方。
- order book 是否薄，是否有明显买卖墙。
- mark price 和 last price 是否偏离。
- taker buy/sell、CVD 是否确认主动买盘或主动卖盘。
- basis / perp premium 是现货驱动还是杠杆追涨。

如果这些数据缺失，skill 会降低置信度，或者把直接开仓降级成 `trigger long` / `trigger short` / `no trade`。

## 主操作枚举

实时交易回答必须只输出一个主操作。`Main action` 必须严格等于以下之一：

```text
open long
open short
hold long
hold short
close long
close short
flip long to short
flip short to long
trigger long
trigger short
no trade
```

禁止把多个动作写在一个主操作里。例如：

- 不写 `open / hold ETH long`。
- 不写 `close existing longs / stay flat`。
- 不写 `take profit now / rebound short`。
- 不写 `switch product`。
- 不写 `reduce exposure`。

如果需要切换品种，主动作仍然只能是一个。比如用户持有 BTC 多单，但 ETH 空头机会更好，当前仓位的主动作应写 `close long`，ETH 空头只能写成另一个触发思路，不能混进同一个 `Main action`。

## `trigger long / trigger short` 是什么

`trigger long` 或 `trigger short` 表示现在不市价进场，只有在价格或事件触发后才执行或复查。

它有两种类型：

- `orderable`：止损、T1/T2、RR 都有效，可以设置条件单。
- `recheck-only`：需要触发后重新刷新事实，不能直接挂单。

举例：

```text
Main action: trigger short
Entry trigger: ETH 反弹到 1728-1738 后失败
Trigger type: recheck-only
Stop price: 1762
T1: 1680
T2: 1655
```

这不是“判断它一定会先涨”，而是“方向偏空，但当前价格追空 EV/R 不好，所以等更好的空头入场条件”。如果价格直接下跌到目标区，不追空；如果反弹站稳失效位，空头方案取消。

## 决策裁判层

这个 skill 的裁判层负责把复杂信息压成一个主动作。

### 主信号投票

三个主方向信号：

1. BTC structure and momentum。
2. Macro bridge：rates、DXY、VIX、oil、Nasdaq / QQQ、cross-asset。
3. Derivatives confirmation：funding、OI、long/short、liquidation、basis、taker flow。

规则：

- 三个都偏多，不能普通 `no trade`，除非硬阻断。
- 三个都偏空，不能普通 `no trade`，除非硬阻断。
- 2 个同向、1 个中性或缺失，跟随同向一侧，但降低置信度，优先 trigger 或小仓。
- 三个混乱，才允许 `no trade`，但要写清楚多空触发条件。

### 加权评分

评分只是辅助，不是替代事实门。

| 因子 | 分值范围 |
|---|---:|
| BTC structure and momentum | -4 to +4 |
| Macro bridge | -4 to +4 |
| Derivatives | -4 to +4 |
| Spot / ETF / stablecoin flows | -2 to +2 |
| Asset relative strength | -2 to +2 |
| Inflation / growth surprise | -2 to +2 |
| Technical confirmation / execution quality | -2 to +2 |
| Event risk / time compression | -3 to 0 |
| Priced-in adjustment | -3 to +1 |
| Crowding adjustment | -3 to +1 |
| Auxiliary sentiment / on-chain / options | -1 to +1 |

大致动作梯度：

- `>= +8`：偏 `open long` / `hold long`。
- `+4 to +7`：默认 `trigger long`。
- `-3 to +3`：新仓默认 `no trade`，已有仓位走持仓规则。
- `-4 to -7`：默认 `trigger short`。
- `<= -8`：偏 `open short` / `hold short` / `close long` / `flip long to short`。

### EV/R 执行门

方向对，不代表当前价位能交易。

新开仓通常要求：

- T1 RR >= 1.2。
- T2 RR >= 1.8。
- 或者是明确解释过的事件反应短线。

如果方向强但 RR 差，输出 `trigger long` 或 `trigger short`，等更好的价格，而不是追单。

已有仓位也要看 forward EV/R：

- `hold long` / `hold short` 需要剩余目标相对失效位仍有正向 EV/R。
- `close long` / `close short` 需要说明 thesis 失效、forward EV/R 变差、硬阻断、事件边界或目标已完成。
- `flip long to short` / `flip short to long` 必须同时满足原方向平仓条件和反向入场条件。

### 事件压缩

重大事件包括 FOMC、CPI、PPI、PCE、NFP、Powell、期权月度/季度交割、地缘突发、稳定币/交易所/链上重大事故。

事件窗口规则：

- 24-48h 内：降低置信度，缩短复查时间。
- 6-24h 内：优先 trigger 或持有到附近目标，减少新市价开仓。
- 6h 内：通常不新开市价仓，除非事件已经重新定价。
- 事件后：只交易 actual vs consensus 和市场反应，不交易标题本身。

### 硬阻断和软降级

硬阻断示例：

- 当前 last / mark / index 缺失。
- funding / OI 缺失。
- active event status 缺失。
- 主要催化剂只有社交媒体传闻。
- EV/R 为负。
- 稳定币脱锚、交易所提现异常、重大安全事故未确认。

软降级示例：

- liquidation / CVD / long-short 缺失，但价格、宏观和 exchange-native derivatives 同向。
- ETF / stablecoin 数据缺失，但没有把它作为支持理由。
- options 数据缺失且不在重大 expiry 窗口。
- 事件 6-24h 内，但 trigger 和 invalidation 明确。

## 输出模板

实时交易回答使用 `references/templates.md#Live Answer Template`。核心字段包括：

```text
Main action: <exact enum only>
Action validity check:
Instrument:
Horizon:
Last / mark / index price + timestamp/source/freshness:
1H / 4H candle timestamp:
Order book timestamp/depth:
Funding / OI timestamp:
Data quality:
Unavailable / stale data:
Derivatives confirmation:
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
Subjective probability:
Confidence cap reason:
Entry trigger:
Trigger type:
Stop price:
Targets:
Risk/reward:
Position size class:
Invalidation event/price:
Do-not-hold-through event:
Why this is the highest-probability path:
Why not the opposite:
Sources used:
What would change the decision:
Next review time:
```

最终回答不能以“多空都有机会”“谨慎关注关键位”这类平衡废话结尾。必须以 `What would change the decision` 和 `Next review time` 收束。

## 事件池

`references/event-pool.md` 是唯一保留的状态池。它维护：

- 未来 72h 内的 active decision window。
- 已发生但市场反应仍未结束的 active market reactions。
- CPI / PPI / PCE / NFP / FOMC / 期权交割等循环事件。
- 地缘、油价、交易所、监管、稳定币、链上事故等突发事件。

事件池规则：

- 过期事件不能继续标 `upcoming`。
- active / upcoming / breaking 事件必须有 expires、next recheck 或 resolution condition。
- 历史事件只能作为复盘记忆，不能作为当前事实。
- 不记录历史交易建议、旧仓位、旧止损、旧概率或旧方向判断。
- 用户如果要求复盘某次决策，需要在当前对话里提供记录；复盘结论只能沉淀为 `references/lessons.md` 的过程教训，不能变成默认方向偏见。

## 数据源路线

### 交易所和加密市场

默认优先级：

1. OKX public API：BTC/ETH/SOL swap 的 ticker、mark、index、funding、OI、candles、books。
2. Binance USD-M futures：ticker、premium index、funding、OI、klines、depth、global long/short、taker buy/sell。
3. Bybit V5 public market。
4. Deribit：BTC/ETH options。
5. CoinGlass / Coinalyze / Velo / Laevitas：all-market funding、OI、long-short、liquidation、options。
6. Coinbase / Kraken / CoinGecko / CoinMarketCap：只能做 spot sanity check，不能替代合约 mark/index。

如果聚合衍生品源不可用，exchange-native funding/OI 只是局部证据，不能标记为强衍生品确认。

### 资金流和情绪

- Farside BTC ETF flows。
- Farside ETH ETF flows。
- issuer official daily files。
- DefiLlama stablecoin supply。
- CryptoQuant / Glassnode / Nansen-like exchange reserves and netflow。
- Alternative.me Fear & Greed。
- MVRV、NUPL、SOPR 等周期/链上指标。

链上和周期指标用于中周期背景，不用于 15m / 1h 直接开仓理由。

### 宏观和新闻

- Federal Reserve FOMC calendar。
- Federal Reserve H.15 rates。
- BLS CPI / PPI / Employment Situation。
- BEA PCE。
- U.S. Treasury rates。
- FRED 10Y real yield。
- Cboe VIX。
- CME FedWatch。
- DXY、WTI、Brent、QQQ、NQ、ES、MOVE / credit proxies。
- Reuters、AP、Bloomberg、CNBC。
- OKX / Binance / Bybit / Deribit status pages。
- Solana status、Ethereum blog、Tether / USDC issuer announcements、SEC / CFTC releases。

地缘和油价事件至少用两个可靠来源确认。只有社交媒体的消息只能当风险，不能当事实。

## 脚本

### OKX 快照

```bash
python3 scripts/okx_snapshot.py
```

默认抓取：

- last price。
- mark price。
- index price。
- funding。
- OI。
- 1H / 4H candles。
- order book。

可选跳过：

```bash
python3 scripts/okx_snapshot.py --no-candles
python3 scripts/okx_snapshot.py --no-books
```

注意：脚本无法独立提供 all-market liquidation、long/short、CVD、basis 和 OI change，需要外部源补充。如果 API 失败，脚本会输出 error，后续决策必须把对应数据标成 unavailable。

### 追加事件

```bash
python3 scripts/append_event.py --title "Title" --status active --next-recheck "YYYY-MM-DD HH:mm TZ" --body "..."
```

active / upcoming / breaking / released / active market reaction 类事件必须带 `--expires-at` 或 `--next-recheck`，避免事件池残留过期风险。

## 安装和验证

安装到 Codex skills 目录：

```bash
mkdir -p ~/.codex/skills
git clone https://github.com/luguochang/crypto-macro-decision.git ~/.codex/skills/crypto-macro-decision
```

验证 skill 结构：

```bash
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py ~/.codex/skills/crypto-macro-decision
```

## 示例问题

```text
根据当前 BTC/ETH/SOL 实时价格、宏观事件和衍生品结构，给我一个本周合约胜率最高的主操作。
```

```text
我现在持有 BTC 多单，帮我重新检索事件池和最新宏观，判断继续持有、平仓还是反手。
```

```text
FOMC 前后 BTC 合约怎么处理？看一下 FedWatch、油价、VIX、美债收益率和资金费率。
```

```text
复盘我提供的某条历史决策，只提取过程教训，不把旧方向写进下一次实时判断。
```

## 当前限制

- 本项目不是自动交易系统，不会下单。
- 主观概率除非特别说明，否则不是回测概率。
- 交易所 API、聚合器、新闻和宏观数据可能失败、延迟或互相冲突。
- 当 mark/index/funding/OI/order book 缺失时，skill 会降低置信度，不应强行输出高置信市价开仓。
- 事件池需要维护；历史交易记录不会作为当前实时事实或默认判断依据。
- README 只是说明文档；实际执行规则以 `SKILL.md` 和 `references/` 为准。

## 文件结构

```text
crypto-macro-decision/
├── SKILL.md
├── README.md
├── agents/
│   └── openai.yaml
├── references/
│   ├── data-sources.md
│   ├── event-pool.md
│   ├── exchange-derivatives.md
│   ├── factors-and-sop.md
│   ├── indicator-sweep.md
│   ├── lessons.md
│   └── templates.md
└── scripts/
    ├── append_event.py
    └── okx_snapshot.py
```

## 风险说明

本仓库只用于研究、流程设计和决策记录，不提供金融、投资、法律、税务或交易建议。

加密货币合约属于高风险产品。即使中期方向判断正确，杠杆也可能因为短线波动导致快速爆仓。除非明确说明有经过验证的回测样本，本 skill 中的概率都只是基于事实层和规则层得出的主观概率。

用户需要自行负责交易决策、仓位大小、杠杆倍数、风险控制，以及遵守所在地法律法规。
