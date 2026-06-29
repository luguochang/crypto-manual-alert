# Configuration Reference

配置来源：

1. `config/default.yaml`
2. `config/prod.yaml`
3. 环境变量

环境变量优先级最高。

## app

- `mode`: `OFF`、`SHADOW`、`MANUAL_ALERT`。默认 `SHADOW`。
- `timezone`: 日志和提醒显示时区，默认 `Asia/Shanghai`。
- `data_dir`: SQLite 和业务数据目录。
- `log_level`: 日志等级。

## trading

- `auto_order_enabled`: 首版必须是 `false`。
- `manual_execution_required`: 首版必须是 `true`。
- `allowed_symbols`: 允许生成计划的标的。
- `max_risk_per_trade_pct`: 单笔最大风险，默认 `0.25`。
- `max_leverage`: 最大杠杆，默认 `2`。
- `daily_loss_stop_pct`: 单日亏损停止线。
- `stop_after_consecutive_losses`: 连续亏损停止线。
- `plan_ttl_seconds`: 计划有效期，默认 `90` 秒。

## market_data

- `provider`: `fixture` 或 `okx_public`。首次部署建议 `fixture`。
- `okx_base_url`: OKX API 地址。
- `request_timeout_seconds`: 单接口超时。
- `aggregate_timeout_seconds`: 聚合行情总预算。
- `stale_market_data_seconds`: 行情过期阈值。
- `order_book_depth`: 盘口深度。
- `candle_bar`: K 线周期。
- `candle_limit`: K 线数量。

## decision

- `engine`: `fixture`、`command` 或 `openai_compatible`。
- `skill_path`: vendored skill 路径。
- `command`: `engine=command` 时执行的命令。命令从 stdin 接收 JSON prompt packet，从 stdout 输出严格 JSON plan。
- `timeout_seconds`: 决策引擎总超时。
- `fixture_plan_path`: fixture 决策文件。
- `openai_base_url`: OpenAI 兼容接口地址，不包含 `/v1`。
- `openai_api_key_env`: API Key 环境变量名，默认 `OPENAI_API_KEY`。
- `openai_model`: 模型名。
- `openai_temperature`: 温度。
- `openai_max_tokens`: 最大输出 token。

## notification

- `provider`: 首版 `bark`。
- `enabled`: 是否发送通知。
- `bark_base_url`: Bark 服务地址。
- `bark_device_key_env`: Bark key 的环境变量名。
- `timeout_seconds`: 推送超时。
- `retry_count`: 推送重试次数。
- `max_body_chars`: Bark 正文最大长度。
- `send_failure_alerts`: 是否发送失败提醒。

## scheduler

- `enabled`: 是否启用调度。CLI 当前由 `scheduler` 命令启动。
- `interval_seconds`: 调度间隔。
- `run_on_start`: 启动后是否立即跑一轮。
- `lock_ttl_seconds`: job lock TTL。
- `job_timeout_seconds`: 单次任务预算。
- `max_iterations`: 测试用，`0` 表示无限循环。

## security

- `forbid_trade_keys`: 首版必须 `true`。
- `secret_env_names`: 需要脱敏的环境变量名。
- `forbidden_env_names`: 如果这些环境变量存在，服务直接拒绝启动。

默认禁止：

- `OKX_TRADE_API_KEY`
- `OKX_WITHDRAW_API_KEY`

## 推荐上线流程

1. `APP_MODE=SHADOW`
2. `market_data.provider=fixture`
3. 跑通 Docker 和 Bark 测试。
4. 改为 `market_data.provider=okx_public`。
5. 观察 24 小时。
6. 再改 `APP_MODE=MANUAL_ALERT`。
