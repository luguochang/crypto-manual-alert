# 002-nextjs-workbench-foundation

## 目标

新增 TypeScript / Next.js 工作台骨架，并让它对齐当前 Python FastAPI 契约，而不是做通用任务壳。

## 改动文件

- `frontend/package.json`
- `frontend/package-lock.json`
- `frontend/next.config.ts`
- `frontend/tsconfig.json`
- `frontend/next-env.d.ts`
- `frontend/src/app/layout.tsx`
- `frontend/src/app/styles.css`
- `frontend/src/app/page.tsx`
- `frontend/src/app/manual-run/page.tsx`
- `frontend/src/app/manual-run/run-form.tsx`
- `frontend/src/app/runs/page.tsx`
- `frontend/src/app/runs/[traceId]/page.tsx`
- `frontend/src/app/shared/status-badge.tsx`
- `frontend/src/lib/api/client.ts`
- `frontend/src/lib/api/runs.ts`
- `frontend/src/lib/api/system.ts`
- `frontend/src/lib/schemas/api.ts`
- `frontend/src/lib/schemas/runs.ts`
- `frontend/src/lib/schemas/manual-run.ts`
- `.gitignore`

## 新增页面

- `Dashboard`：展示最近运行、允许提醒、风控阻断和 LLM 交互摘要。
- `Manual Run`：提交 `symbol/query/horizon/position/risk_mode`，调用 `POST /api/runs/manual`。
- `Runs`：查看最近 trace 列表。
- `Trace Detail`：查看 trace 基本信息、计划摘要、span 时间线和 LLM 交互摘要。

## 行为变化

- 前端直接调用 `NEXT_PUBLIC_API_BASE_URL` 指向的 Python FastAPI。
- 不新增 Next API routes，不新增 middleware，不读取 secret。
- API client 统一解析 `{ ok, data, error, trace_id }`。
- Zod schema 与当前 FastAPI 字段对齐：`/api/runs`、`/api/runs/{trace_id}`、`/api/runs/manual`。
- `.gitignore` 增加 `frontend/tsconfig.tsbuildinfo`。

## 安全影响

- 前端不接触 OpenAI/Bark/OKX secret。
- Trace detail 默认展示 LLM hash 与摘要字段，不展示 `request_json/response_json`。
- 页面只用于人工提醒和观测，不提供交易按钮。

## 测试命令

```powershell
cd frontend
npm run typecheck
npm run build
```

## 测试结果

- `npm run typecheck`：通过。
- `npm run build`：通过。

## 已知风险

- 当前没有 Playwright 视觉回归和组件单测。
- Schedules/Eval/Candidates 页面尚未实现。
- Next.js 构建会生成 `.next/`，已通过 `.gitignore` 排除。
