# Operation Guide

首版服务只生成操作计划和 Bark 提醒，不自动交易。用户收到提醒后必须打开 OKX App 手动核对并决定是否执行。

## 本地自测

```powershell
cd E:\file\project\selfproject\project\jiami
pytest -q
jiami-alert show-config
jiami-alert run-once --symbol ETH-USDT-SWAP
```

默认配置使用 fixture 行情和 fixture 决策，不会调用模型，不会发送 Bark。

## 手动生成一次计划

```bash
jiami-alert --config config/default.yaml run-once --symbol ETH-USDT-SWAP
```

输出里会包含：

- `plan_id`
- `instrument`
- `main_action`
- `allowed`
- `reasons`
- `warnings`
- `expires_at`
- `manual_execution_required`

只要 `allowed=false`，不要按计划操作。

## 记录手动结果

```bash
jiami-alert record-outcome --plan-id <plan_id> --outcome executed --notes "manual OKX entry 3510 stop 3435"
```

常用 outcome：

- `executed`
- `rejected`
- `expired`
- `modified`
- `stopped`
- `take_profit`

## Bark 测试

```bash
BARK_DEVICE_KEY=xxx jiami-alert --config config/default.yaml --config config/prod.yaml test-bark
```

Bark 只做提醒，不做授权。没有收到 Bark 时不要补按旧计划操作。

## 手动执行检查

每次在 OKX App 操作前，必须核对：

- 交易对是否正确。
- 产品是否为永续合约。
- 方向是否正确。
- 当前价格是否仍接近计划价格。
- 止损是否已设置。
- 仓位风险是否不超过配置。
- 杠杆是否不超过 2x。
- 计划是否已过期。

任一项不确定，默认不操作，重新生成计划。

