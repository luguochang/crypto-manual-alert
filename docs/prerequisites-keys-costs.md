# Prerequisites, Keys And Costs

> 首版只做“操作计划 + 手动提醒”，不做自动交易。因此前置条件比自动交易少很多：不需要 OKX Trade Key，不需要确认页下单，不需要自动订单执行服务。

## 1. 首版需要准备什么

必须准备：

- OKX/欧易账户，用户自己手动操作。
- Bark iPhone App 和 Bark device key。
- 模型调用能力，例如当前 Codex 工作流或 OpenAI API Key。
- 运行脚本的电脑或 VPS。
- 手动记录日志的位置，例如 Markdown、CSV、SQLite。

可选准备：

- OKX 只读 API Key，用于读取账户余额、仓位和订单，不用于交易。
- VPS，用于定时生成计划和推送 Bark。
- 域名或私有网络，不是首版必需。

首版不需要：

- OKX Trade 权限。
- OKX Withdraw 权限。
- 自动下单程序。
- 自动确认页面。
- 订单状态回查服务。
- 自动止损/平仓服务。

## 2. OKX Key 是否和个人账户关联

是的，OKX API Key 和创建它的账户或子账户绑定。

但首版不需要交易权限。建议：

- 能不用 OKX API Key 就先不用。
- 如果要读取账户仓位，只创建 `Read` 权限 Key。
- 不开 `Trade`。
- 绝对不开 `Withdraw`。
- 不把 Key 发给 LLM。
- 不把 Key 写入文档或 Git。

如果使用只读 Key：

- 它能读取账户信息，但不能下单。
- 仍建议绑定 IP 白名单。
- 模拟盘和实盘分开。
- 用子账户更安全。
- 泄露后仍应立即删除，因为仓位和资产信息也属于敏感信息。

## 3. 用户手动操作责任

首版系统只提供计划，不负责实际交易结果。

每次收到提醒后，用户必须自己：

- 打开 OKX App。
- 核对交易对。
- 核对产品类型。
- 核对方向。
- 核对当前价格。
- 核对止损。
- 核对止盈。
- 核对仓位。
- 核对杠杆。
- 判断计划是否过期。
- 自己决定是否执行。

如果当前价格、仓位或市场状态和计划不一致，应放弃操作并重新生成计划。

## 4. Bark 准备

需要：

- iPhone 安装 Bark App。
- 打开 App 获取 device key 或推送 URL。
- 把 Bark key 配置到本地环境变量或 VPS 环境变量。

Bark 的角色：

- 推送操作计划。
- 推送强提醒。
- 推送复查时间。

Bark 不做：

- 身份认证。
- 下单授权。
- 自动交易触发。
- 保存 OKX Key。

可靠性注意：

- Bark 可能延迟。
- iPhone 勿扰、离线、没电时可能收不到。
- 超过计划有效期后，不要按旧通知操作。
- Bark key 泄露后别人可能给你推送消息，但不能下单；仍建议更换 key。

## 5. 模型/API 准备

可选方式：

- 继续用当前 Codex 工作流手动触发分析。
- 使用 OpenAI API Key 让脚本自动生成计划。
- 使用其他兼容模型服务，但需要重新验证质量。

注意：

- 模型 API Key 和 OKX API Key 不是一回事。
- 模型 API Key 可能按 token 收费。
- LLM 不应该接触 OKX Secret、Passphrase 或任何可交易 Key。
- LLM 输出必须被格式化成操作计划，不能直接变成订单。

## 6. VPS 是否必须

首版不必须。

可以选：

- 本地电脑手动运行：成本低，但不能 24 小时稳定提醒。
- VPS 定时运行：更稳定，适合固定时间分析和 Bark 推送。

如果使用 VPS：

- 固定 IP 更好，但首版不下单，所以不是硬要求。
- 仍要保护 Bark key、模型 API Key、只读 OKX Key。
- VPS 不能用于绕过 OKX 地区限制或服务限制。
- 如果后续接 Trade 权限，必须重新做安全设计。

## 7. 合规和地区限制

首版虽然不自动下单，但用户仍然在 OKX 手动交易，所以必须确认：

- 自己所在地区允许使用 OKX 对应产品。
- 账户已经满足 KYC 和产品权限。
- 永续合约、杠杆等衍生品符合当地规则。
- 不使用 VPS 或任何工具绕过地区限制。
- 自己保留交易记录用于税务和复盘。

如果地区、账户或产品权限不确定，只做模拟盘或纸面记录。

## 8. 费用和收费点

| 项目 | 首版是否需要 | 是否收费 | 说明 |
| --- | --- | --- | --- |
| OKX API Key | 可选只读 | 通常免费 | 首版不需要 Trade Key；只读 Key 用于读取仓位时才需要。 |
| OKX 手动交易 | 用户决定 | 有成本 | 手续费、资金费率、滑点、点差、强平风险都由用户手动交易产生。 |
| Bark | 必须 | 通常免费 | 用于 iPhone 推送提醒；自建 Bark Server 会占用 VPS 资源。 |
| OpenAI/模型 API | 可选 | 按量收费 | 如果用 API 自动生成计划，会按模型和 token 计费。 |
| Codex 当前工作流 | 可选 | 取决于账号/套餐 | 如果继续人工触发分析，费用按当前使用方式计算。 |
| VPS | 可选 | 收费 | 用于定时运行和推送，不是首版必需。 |
| 域名/HTTPS | 非必需 | 可选收费 | 首版没有确认页下单，不强制需要公网域名。 |
| 数据源 | 可选 | 可能收费 | 交易所公开行情通常免费；清算热图、精确 CVD、期权数据、专业资金流可能收费。 |
| 税务/记录工具 | 可选 | 可能收费 | 高频手动交易需要保留记录，可能使用第三方报税或记账工具。 |

费用建模要考虑：

- maker/taker 手续费不同。
- 永续资金费率会影响持仓成本。
- 市价单滑点可能比手续费更大。
- 高频调用模型会增加 API 成本。
- 付费数据源不一定提升胜率，首版不建议先购买。

## 9. 数据拿不到时怎么处理

首版必须承认数据缺口。

常见拿不到或不稳定的数据：

- 实时清算热图。
- 精确 CVD/taker delta。
- 期权详细 IV/skew/OI。
- ETF 最终流数据。
- 部分第三方网页动态数据。

处理原则：

- 拿不到就写 `unavailable`。
- 网页推断就写 `web-derived`。
- 数据过期就写 `stale`。
- 缺关键数据时降低胜率或输出 `no trade`。
- 不编造数据。

## 10. 手动安全清单

每次实际操作前：

- 确认不是旧通知。
- 确认交易对正确。
- 确认产品正确。
- 确认方向正确。
- 确认杠杆不超过 `2x`。
- 确认止损已经设置。
- 确认仓位不会让单笔亏损超过账户权益 `0.25%`。
- 确认当日亏损没有超过 `1%`。
- 确认没有连续 2 次亏损后继续冲动交易。
- 确认自己看得懂这次操作的失效条件。

任何一项不确定，默认不操作。

## 11. 推荐实施顺序

1. 安装 Bark 并拿到 device key。
2. 先不创建 OKX API Key。
3. 用当前 Codex 流程生成 7 到 14 天手动计划。
4. 每次计划后手动记录是否执行和结果。
5. 如果需要自动读取仓位，再创建 OKX 只读 Key。
6. 如果需要定时提醒，再部署到 VPS。
7. 累计至少 50 次计划样本后，再评估是否值得做半自动。

## 12. 当前推荐配置

```env
APP_MODE=MANUAL_ALERT
AUTO_ORDER_ENABLED=false
OKX_TRADE_KEY_REQUIRED=false
OKX_READ_KEY_OPTIONAL=true
BARK_DEVICE_KEY=...
MAX_RISK_PER_TRADE_PCT=0.25
MAX_LEVERAGE=2
PLAN_TTL_SECONDS=90
STALE_MARKET_DATA_SECONDS=120
DAILY_LOSS_STOP_PCT=1
STOP_AFTER_CONSECUTIVE_LOSSES=2
```

不要把真实 Key 写入文档或提交到 Git。首版如果不接 OKX 只读 Key，就只需要 Bark key 和模型/API 配置。

## 13. 参考来源

- OKX API 文档：https://www.okx.com/docs-v5/
- OKX API FAQ：https://www.okx.com/help/api-faq
- OKX 费用说明：https://www.okx.com/fees
- OKX Trading Fee Rules FAQ：https://www.okx.com/help/trading-fee-rules-faq
- OKX U.S. Risk And Compliance Disclosures：https://www.okx.com/help/us-risk-and-compliance-disclosures
- OKX U.S. Terms：https://www.okx.com/help/terms-of-service-us
- Bark GitHub：https://github.com/Finb/Bark
- OpenAI API Pricing：https://openai.com/api/pricing/

