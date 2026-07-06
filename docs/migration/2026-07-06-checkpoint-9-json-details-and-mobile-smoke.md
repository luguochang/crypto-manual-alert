# Checkpoint 9 - Run Detail JSON Details And Mobile Smoke

日期：2026-07-06

## 目标

补齐 Run Detail 驾驶舱剩余前端验收项：JSON payload 只能作为辅助展开信息，不再作为主表达；用真实 trace 验证桌面和移动端没有 body 级横向溢出或明显文本重叠。

## 变更

- `frontend/src/app/runs/[traceId]/page.tsx`
  - 新增 `JsonDetails` 折叠组件。
  - `Analysis` 中的 `Data Gaps`、`Risk Rule Hits` JSON 改为默认折叠。
  - `Badcases And Replay` 与 `Structured Result` 的 JSON 改为默认折叠。
  - `Span Timeline` 和 `LLM Requests And Responses` 不再默认展开正常项，仅非 `ok` 项自动展开。
- `frontend/src/app/styles.css`
  - 为 `.json-details > .code-box` 增加稳定边距。
- `tests/structure/test_frontend_route_boundaries.py`
  - 新增结构测试，防止 Run Detail 重新出现裸露 JSON 主表达。
- `docs/formal/35-剩余主缺口对抗审查与执行清单.md`
  - Phase 3 checklist 标记 JSON 辅助展开与移动端 smoke 完成。

## 验证

RED：

```powershell
python -m pytest tests/structure/test_frontend_route_boundaries.py::test_run_detail_json_payloads_are_collapsed_auxiliary_details -q
```

失败点：Run Detail 尚无 `JsonDetails`，且仍存在裸露 `<pre>` JSON。

GREEN：

```powershell
python -m pytest tests/structure/test_frontend_route_boundaries.py -q
npm run typecheck
```

注意：`npm run typecheck` 需在 `frontend/` 目录运行。

页面 smoke：

```powershell
$env:DATA_DIR = "$env:TEMP/jiami-phase3-ui-smoke"
$env:SHADOW_WORKER_MODE = "llm_tool_shadow"
$env:WORKFLOW_EXECUTION_MODE = "production_candidate_swarm"
python -m uvicorn crypto_manual_alert.api.app:app --host 127.0.0.1 --port 8011

$env:NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8011"
npm run dev -- --hostname 127.0.0.1 --port 3011
```

生成 trace：

`production-candidate-swarm-run_14e6160b06c14222b6c768c7e0ff64de`

Playwright 检查结果：

- 1440x1100：关键模块存在，4 个 `details.json-details` 默认折叠，body/doc scroll width 等于 viewport width。
- 390x844：关键模块存在，4 个 `details.json-details` 默认折叠，body/doc scroll width 等于 viewport width。
- 截图：
  - `%TEMP%/jiami-phase3-ui-smoke/run-detail-desktop.png`
  - `%TEMP%/jiami-phase3-ui-smoke/run-detail-mobile.png`

## 安全边界

- 本 checkpoint 只调整 Run Detail 展示层，不修改后端决策、provider、gate 或默认配置。
- trace 仍为 `production_candidate_swarm` audit-only，`production_final_input=false`。
- 临时 API/Next 服务已在 smoke 后停止。

## 剩余缺口

- Phase 4 仍需完成金融质量 outcome/eval 闭环。
- Phase 5 仍需外显 Harness policy。
- Phase 6 仍需继续拆分大文件与兼容层。
