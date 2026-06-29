# Production Rebuild Implementation Plan

> 本计划用于本轮一体化重构。目标架构一次定型，代码按可验证切片合入。分切片不是临时乱改，而是保证每个合入点都能运行、能测试、能回滚。

## Goal

把现有 Python CLI 管线升级为“Python FastAPI Agent 后端 + Next.js TypeScript 工作台”的生产级公开仓库基线，同时保留现有 CLI、SQLite、Bark 和 65 个测试的兼容性。

## Architecture

首版不引入 Redis、队列、Temporal、独立 TypeScript BFF、向量库或外部 LLMOps 服务。Next.js 直接调用 Python FastAPI；Python 继续持有 workflow、skill、LLM、行情、Bark、Trace/Eval 责任；SQLite 默认存储。

## Why Not One Giant Commit

最终结构一次确定：

```text
frontend/                       TypeScript 工作台
src/jiami_crypto_alert/api/      FastAPI API
src/jiami_crypto_alert/context/  DecisionRequest / session 语义
src/jiami_crypto_alert/workflow/ RunExecutor / facade
src/jiami_crypto_alert/storage/  查询仓储边界
```

但实现必须按切片合入：

- 每个切片有独立测试。
- 每个切片不破坏现有 CLI。
- 每个切片都能回滚。
- 多 agent 只做互不冲突的审查或实现范围，避免同时改同一文件。

这不是阶段性临时方案，而是用最终架构做可验证增量。

## Task 1: Public Repository Safety Baseline

**Files:**

- Modify: `.gitignore`
- Modify: `.dockerignore`
- Modify: `.env.example`
- Create or modify: `README.md`
- Create: `docs/migration/000-public-repo-baseline.md`

**Requirements:**

- data DB、日志、真实 env 不可提交。
- `.env.example` 不包含真实 key 语义。
- README 明确项目定位：manual alert，不是自动交易。
- 记录测试基线：`65 passed`。

**Tests / Checks:**

```powershell
python -m pytest
Select-String -Path .env.example, README.md -Pattern 'sk-[A-Za-z0-9]{20,}|BARK_DEVICE_KEY=[A-Za-z0-9]{20,}|OKX_API_SECRET=.+|OKX_API_PASSPHRASE=.+'
```

## Task 2: Python API Foundation

**Files:**

- Create: `src/jiami_crypto_alert/api/__init__.py`
- Create: `src/jiami_crypto_alert/api/schemas.py`
- Create: `src/jiami_crypto_alert/api/app.py`
- Create: `src/jiami_crypto_alert/api/routes_runs.py`
- Create: `tests/test_api_runs.py`
- Modify: `pyproject.toml`

**Requirements:**

- 增加 FastAPI 依赖。
- `GET /api/system/health`
- `POST /api/runs/manual`
- `GET /api/runs`
- `GET /api/runs/{trace_id}`
- API 返回统一 envelope：`ok/data/error/trace_id`。
- API 不直接写复杂业务，调用 `PlanRunner` 或 `RunExecutor`。
- 公共 schema 和路由函数加中文 docstring。

**TDD:**

1. 先写 `tests/test_api_runs.py`。
2. 运行失败，确认 FastAPI app/routes 不存在。
3. 实现最小 API。
4. 运行目标测试和全量 pytest。

**Verification:**

```powershell
python -m pytest tests/test_api_runs.py
python -m pytest
```

## Task 3: DecisionRequest And RunExecutor Facade

**Files:**

- Create: `src/jiami_crypto_alert/context/__init__.py`
- Create: `src/jiami_crypto_alert/context/request.py`
- Create: `src/jiami_crypto_alert/workflow/__init__.py`
- Create: `src/jiami_crypto_alert/workflow/run_executor.py`
- Create: `tests/test_decision_request.py`
- Create: `tests/test_run_executor.py`
- Modify: `src/jiami_crypto_alert/runner.py`

**Requirements:**

- 引入 `DecisionRequest`，但不强行替换所有旧入口。
- `PlanRunner.run_once(symbol)` 继续可用。
- 新增 `PlanRunner.run_request(request)` 或 `RunExecutor.run(request)`。
- trace `run_type` 从 request 来，修正 scheduler/manual/eval/replay 语义的基础。
- 未知持仓先只记录，不在本切片改变交易输出。

**Verification:**

```powershell
python -m pytest tests/test_decision_request.py tests/test_run_executor.py
python -m pytest tests/test_runner_cli.py tests/test_journal_scheduler.py
python -m pytest
```

## Task 4: Journal Query Repository For UI

**Files:**

- Create: `src/jiami_crypto_alert/storage/__init__.py`
- Create: `src/jiami_crypto_alert/storage/query_repository.py`
- Create: `tests/test_query_repository.py`
- Modify: `src/jiami_crypto_alert/api/routes_runs.py`

**Requirements:**

- 前端查询不直接依赖 Journal 内部 row 格式。
- Repository 提供：
  - `list_runs(limit)`
  - `get_run_detail(trace_id)`
  - `get_run_spans(trace_id)`
- 默认不返回 raw_decision、request_json、response_json。

**Verification:**

```powershell
python -m pytest tests/test_query_repository.py tests/test_api_runs.py
python -m pytest
```

## Task 5: Next.js TypeScript Workbench Skeleton

**Files:**

- Create: `frontend/package.json`
- Create: `frontend/next.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/src/app/layout.tsx`
- Create: `frontend/src/app/page.tsx`
- Create: `frontend/src/app/manual-run/page.tsx`
- Create: `frontend/src/app/runs/page.tsx`
- Create: `frontend/src/lib/api/client.ts`
- Create: `frontend/src/lib/schemas/runs.ts`
- Create: `frontend/src/components/app-shell.tsx`
- Create: `frontend/src/features/runs/*`

**Requirements:**

- TypeScript 严格模式。
- 不引入 BFF。
- 前端调用 `NEXT_PUBLIC_API_BASE_URL`。
- Dashboard、Manual Run、Runs 三个页面可用。
- 关键 API client 和 schema 加中文注释。
- UI 是管理后台风格，不做营销页。

**Verification:**

```powershell
cd frontend
npm install
npm run typecheck
npm run build
```

## Task 6: Schedules API And UI Placeholder

**Files:**

- Create: `src/jiami_crypto_alert/api/routes_schedules.py`
- Create: `tests/test_api_schedules.py`
- Create: `frontend/src/app/schedules/page.tsx`
- Create: `frontend/src/lib/schemas/schedules.ts`

**Requirements:**

- 首版可以先读写 SQLite 中 schedules 表，或返回配置派生的只读计划。
- 页面能展示定时任务列表和启停状态。
- 不引入队列。

**Verification:**

```powershell
python -m pytest tests/test_api_schedules.py
cd frontend
npm run typecheck
npm run build
```

## Task 7: Documentation And Self-Test Record

**Files:**

- Modify: `README.md`
- Create: `docs/migration/001-fastapi-and-nextjs-foundation.md`

**Requirements:**

- 记录本轮实现文件。
- 记录测试命令和输出摘要。
- README 写本地启动方式。
- README 写公开仓库安全边界。

**Verification:**

```powershell
python -m pytest
cd frontend
npm run typecheck
npm run build
```

## Current Turn Scope

本轮优先完成 Task 1-5。Task 6-7 视上下文和工具状态继续推进。若 npm 环境不可用，必须说明原因并保证 Python 部分完整通过。
