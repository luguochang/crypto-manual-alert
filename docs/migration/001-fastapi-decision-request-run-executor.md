# 001-fastapi-decision-request-run-executor

## 目标

在不破坏旧 CLI/Runner 的前提下，补齐 Next.js 工作台需要的 Python API 基础、请求语义对象和受控执行入口。

## 改动文件

- `pyproject.toml`
- `src/crypto_manual_alert/api/*`
- `src/crypto_manual_alert/context/*`
- `src/crypto_manual_alert/workflow/*`
- `src/crypto_manual_alert/storage/*`
- `tests/test_api_runs.py`
- `tests/test_decision_request.py`
- `tests/test_workflow_run_executor.py`
- `tests/test_query_repository.py`

## 新增接口

- `GET /api/system/health`
- `POST /api/runs/manual`
- `GET /api/runs`
- `GET /api/runs/{trace_id}`

## 行为变化

- API 统一返回 `{ ok, data, error, trace_id }`。
- 手动运行通过 `DecisionRequest` 归一化请求，再由 `RunExecutor` 调用旧 `PlanRunner`。
- `JournalQueryRepository` 负责 UI/API 查询边界，默认不暴露 `raw_decision`、`request_json`、`response_json`。
- eval/replay/postmortem 暂不允许从 `RunExecutor` 生产入口执行，避免误触发 Bark 或生产 plan 写入。

## 安全影响

- 没有新增自动交易能力。
- 没有新增下单、撤单、提现工具。
- API 默认隐藏 LLM 原始 payload。

## 测试命令

```powershell
python -m pytest tests/test_api_runs.py tests/test_decision_request.py tests/test_workflow_run_executor.py tests/test_query_repository.py
python -m pytest
```

## 测试结果

- 新增/目标测试：`12 passed`
- 全量 Python 测试：`77 passed`
- FastAPI TestClient E2E：`health 200 True`，`manual 200 trigger long True`，`detail 200 7`

## 回滚方式

- 移除新增 `api/`、`context/`、`workflow/`、`storage/` 文件。
- 从 `pyproject.toml` 移除 `fastapi`。
- 移除新增测试文件。
- 旧 CLI/Runner 未改签名，回滚风险较低。
