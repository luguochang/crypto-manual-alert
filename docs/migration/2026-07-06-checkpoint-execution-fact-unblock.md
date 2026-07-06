# Checkpoint: 解开 facts_gate 开仓阻断陷阱（execution fact + active_event_status）

日期：2026-07-06
对应：`docs/formal/37-真实多Agent对抗审查与交付方向裁决.md` §5.2 H1（交付生死线）
计划：`.tmp/optimization-plan.md` Phase 0.1

## 问题

`facts_gate` 在产出可执行开仓动作（opening/trigger/flip）前要求两类事实齐备，但默认配置下两者都不满足，导致即使 `prod.yaml` 接了真实 LLM，`trigger long` 等开仓动作仍被 `production_control_gate` 以 `candidate.action_not_allowed` 阻断：

1. **执行事实** `mark`/`index`/`order_book`：必须 exchange_native。默认 `market_data.provider=fixture` 的 source 为 `fixture`，不满足。
2. **事件事实** `active_event_status`：必须 event_pool/official 源。代码库无任何 provider 提供该点，永远缺失。

`evidence.py:249` `blocked_action_classes = ["opening","trigger","flip"]` 当 `missing` 或 `missing_event` 非空时触发。`test_runs_routes.py:55` 断言默认运行 `allowed=False`。

## 解法

不耦合 audit swarm 与 gate（swarm 的 `tool_call_artifact_refs` 不喂 facts_gate——执行事实来自行情层，设计如此）。改为：

1. **执行事实**：`market_data.provider=okx_public` 已存在，`OkxPublicMarketDataProvider` 拉 mark/index/order_book（source `okx_public` → `exchange_native`）。给该 provider 加 `http_get` 注入，使其在 CI 可测（不依赖真实网络）。
2. **事件事实**：新增 `market/event_status.py`，`macro_event.provider` config 控制：
   - `disabled`（默认）：不提供 active_event_status（安全，开仓阻断）。
   - `no_active_event`：操作员断言无活跃宏观事件，写入 source=`event_pool` 的事件状态点（满足 `_can_satisfy_event_fact`），放行开仓。断言记入审计轨迹。
3. **接线**：`LegacyDecisionWorkflow` 从 config 构建 `event_status_provider`，传给 `load_market_context_step`，由 `enrich_snapshot_with_event_status` 把 active_event_status 注入 snapshot。
4. **交付配置**：新增 `config/staging.yaml`（`okx_public` + `no_active_event` 覆盖层）。

## 改动文件

- `src/crypto_manual_alert/market/providers.py`：`OkxPublicMarketDataProvider` 加 `http_get` 注入。
- `src/crypto_manual_alert/market/event_status.py`（新）：`EventStatusProvider` protocol、`DisabledEventStatusProvider`、`NoActiveEventStatusProvider`、`build_event_status_provider`、`enrich_snapshot_with_event_status`。
- `src/crypto_manual_alert/config/models.py`：新增 `MacroEventConfig`（`provider: str = "disabled"`），挂到 `Config` + `safe_dict`。
- `src/crypto_manual_alert/config/loader.py`：`_build_config` 加 `macro_event` 段；`_validate` 校验 provider 取值；`MACRO_EVENT_PROVIDER` env 覆盖；导入 `MacroEventConfig`。
- `src/crypto_manual_alert/workflow/legacy_plan_runner.py`：`build_market_provider` 透传 `http_get`。
- `src/crypto_manual_alert/workflow/legacy_decision_workflow.py`：`__init__` 构建 `event_status_provider`，`run` 传给 `load_market_context_step`。
- `src/crypto_manual_alert/workflow/market_context_step.py`：`load_market_context_step` 接受 `event_status_provider`，调 `enrich_snapshot_with_event_status`。
- `config/default.yaml`：新增 `macro_event.provider: disabled`。
- `config/staging.yaml`（新）：`okx_public` + `no_active_event` 覆盖层。
- `.env.example`：`SCHEDULER_ENABLED=false`（与 default.yaml 一致），新增 `MACRO_EVENT_PROVIDER=disabled`。
- `docs/deployment.md`：新增"风控门禁与可执行提醒"章节。
- `tests/workflow/test_execution_fact_unblock.py`（新）：3 个测试（okx_public 放行、fixture 阻断、staging 配置端到端放行）。

## 验收

```powershell
python -m pytest tests/workflow/test_execution_fact_unblock.py tests/workflow/test_controlled_adapter.py tests/config tests/api/test_runs_routes.py tests/market tests/workflow/test_market_context_step.py -q
```

全部通过（45+ 测试）。关键断言：

- `test_okx_public_market_data_unblocks_opening_action_gate`：okx_public（mock HTTP）+ no_active_event → `verdict.allowed=True`、`production_control_gate.allowed=True`、`missing_execution_facts=[]`。
- `test_fixture_market_data_blocks_opening_action_by_default`：默认 fixture → `allowed=False`、命中 `action_not_allowed`（安全默认不变）。
- `test_staging_config_loads_and_unblocks_gate`：`default+staging` 配置端到端放行。

## 不变约束维持

- 默认 `macro_event.provider=disabled`（不默认放行开仓）。
- 默认 `market_data.provider=fixture`（default.yaml；不默认接真实网络）。
- 不切 `final_input_mode`、不开自动交易、`manual_execution_required=true`。
- swarm 仍是 audit-only，`tool_call_artifact_refs` 不喂 facts_gate（执行事实来自行情层）。

## 运行时验收（需真实 OKX + Bark）

```powershell
$env:MARKET_DATA_PROVIDER='okx_public'; $env:MACRO_EVENT_PROVIDER='no_active_event'
$env:NOTIFICATION_ENABLED='true'; $env:BARK_DEVICE_KEY='你的key'
crypto-alert --config config/default.yaml --config config/prod.yaml run-once --symbol ETH-USDT-SWAP
```

预期：产出 `trigger long`（或真实 LLM 决策）且 `allowed=True`、symbol 一致、Bark 收到含 entry/stop/target 的提醒。

## 剩余

- 真实 OKX 网络连通性 + Bark 端到端：需运行时环境验证（CI 用 mock HTTP 已覆盖逻辑）。
- Phase 0.2：修绿 6 个失败测试。
- 真实宏观事件日历 provider（替换 `no_active_event` 操作员断言）：Phase 3。
