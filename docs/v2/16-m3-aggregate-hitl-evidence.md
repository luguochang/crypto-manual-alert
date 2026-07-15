# M3 Aggregate HITL And Queue Convergence Evidence

> authority_class: informative
>
> 审计时点：2026-07-15（Asia/Shanghai）
>
> 代码基线：`0bc995f` 之后的当前 M3 工作树；提交前必须以最终 commit SHA 替换本说明中的工作树边界。

本文记录 M3 本地开发 Runtime 的实施与验证事实。它不修改
`13-v2-final-rebuild-spec.md` 或 `14-v2-final-implementation-plan.md` 的要求，
也不把本地 `langgraph dev`、QA fixture 或单机 PostgreSQL 解释为生产发布证明。

## 1. 本轮完成范围

- 使用官方 LangGraph Thread/Run/Checkpoint/`Command(resume=...)`，没有新增第二套
  Runtime、checkpointer 或 HITL 状态机。
- 新增 `InterruptPause` aggregate authority。一个 Task 最多一个 active pause；
  pause 包含 1-64 个成员，Product API 只公开稳定业务字段，不公开 namespace、
  checkpoint、checkpoint map 或 projection ID。
- 新增 Alembic `0007_interrupt_pauses`，覆盖 fresh upgrade、downgrade、legacy
  single/multi backfill、失败前不残留 DDL、混合/缺失 official lineage fail-fast 和
  active pause partial unique index。
- Product `respond-all` 在一个事务中接受完整成员集合，创建一个 Product resume Run
  和一个 durable `respond` TaskCommand；worker 只创建一个 official resume Run。
- Runtime adapter 从官方 current ThreadState 收集同一 superstep 的 root/nested
  interrupts，忽略已消费成员，使用 current-head resume，并对 malformed lineage
  fail closed。
- Work UI 支持多卡唯一 accessible name、键盘选择、整组确认、草稿离页保护、
  popstate 重载、焦点恢复、polite live region 和桌面/移动端深滚动检查。
- Inbox 从“每 member 一项”收敛为“每 pause 一项”，公开 `pause_id`、
  `pause_version` 和 `member_count`。

## 2. 状态机裁决

Product DB 是 Task/Run/Artifact/Interrupt 查询权威，官方 Checkpoint 只负责执行恢复：

| 阶段 | Product Task | Product resume Run | Pause / Members |
|---|---|---|---|
| 等待决定 | `waiting_human` | 不存在 | `pending` / `pending` |
| 决定已持久化 | `waiting_human` | `queued` 或 `running` | `responding` / `responding` |
| 恢复成功 | `succeeded` 或 `blocked` | 对应终态 | `resolved` / `resolved` |
| 用户恢复耗尽 | `failed` | `failed` | `resume_failed` / 保留已接受响应 |
| 自动过期恢复中 | `running` | `queued` 或 `running` | `expired` / `expired` |

公开 Task DTO 只要仍存在唯一 active pause，就固定投影为 `waiting_human`。这避免了
`running + responding pause` 这种前端严格 schema 无法解析、轮询会停止的跨层矛盾。

## 3. 两天死循环的直接根因与修复

真实开发库发现一条历史自动 expiry `respond` command 的 `attempt=8018`。根因有两项：

1. `pending` command 的 `lease_expires_at` 被写成未来时间后，`claim_next()` 仍忽略
   该时间立即重新领取，reconciliation backoff 实际无效。
2. 自动 expiry rejection 使用无限重试，旧 official Thread 已不存在时永不收敛；
   oldest-first 排序使所有 fresh command 饥饿。

修复后：

- `pending` command 只有在 `lease_expires_at IS NULL OR <= now` 时可领取。
- 用户 resume 使用 `max_attempts`；自动 expiry 使用更大的
  `max_cancel_attempts`，但两者都必须收敛到持久失败。
- 回归测试覆盖 backoff 不可提前领取、自动 expiry 可重试同一不可变 response map、
  retry budget 耗尽、pause/run/task/command 原子失败和 fresh queue 不再被热循环占满。

## 4. 真实 Runtime 证据

测试拓扑为本地 official Agent Server 0.11.0 + Product API + worker + PostgreSQL +
production Next.js。Playwright 没有 mock Agent 写请求；multi fixture 由官方 Runtime
真实生成同一 superstep 的 root/nested interrupt。

| 视口 | Product Task | Official Thread | Source Run | Resume Run |
|---|---|---|---|---|
| Desktop `1440x1000` | `754557c4-a0aa-4659-a70b-08f4d2b55cd1` | `4ac2b279-ac1b-47ed-b0ef-d3ece7ab8e9b` | `019f6599-e176-7253-8537-dc7cfd7d2b06` | `019f659a-68c9-7c81-b499-b1d76c7c7950` |
| Pixel 7 `412x915` | `36e94124-fd2d-41b5-9325-d02ae80d8651` | `0ec861ba-252b-460f-8172-eb731bbaab48` | `019f6599-e486-7ac0-8fcd-aee0d751e4c6` | `019f659a-7cf5-7083-ad4c-efe5fd97435e` |

每条任务的独立 Product DB 与官方 Runs API 核验结果相同：

- Task `succeeded`，Artifact `committed`。
- 一个 pause `resolved`，两个成员均 `resolved`。
- 两个 Product Run：一个 source、一个 `resume_of_run_id` 非空的 resume Run。
- 一个 `respond` TaskCommand，终态 `dispatched`。
- 两个 official Run：source + resume，均为 `success`；没有第二个 resume create。

## 5. Fresh 验证结果

| 门禁 | 结果 |
|---|---|
| Backend hermetic `uv run pytest -q` | `493 passed, 95 skipped, 1 warning` |
| PostgreSQL integration | `110 passed` |
| Dispatcher PostgreSQL | `49 passed` |
| Migration PostgreSQL | `10 passed`（M3 migration 切片） |
| Frontend unit | `212 passed` |
| Frontend lint / typecheck / production build | 全部退出 0 |
| Fixture Playwright | `32 passed, 12 skipped` |
| Real Inbox Desktop + Pixel 7 | `2 passed` |
| Real aggregate HITL Desktop + Pixel 7 | `2 passed` |

Hermetic suite 中的 95 个 skip 和 fixture suite 中的 12 个 skip 均按“未证明”处理；
它们不能计入生产门禁通过数。

## 6. 明确未完成

- canonical provider Graph 仍需把真实 nested/subagent interrupt 接入同一 aggregate
  contract；本证据的 multi graph 是 QA fixture，不重新证明 OKX/search/model 前半链。
- 本地 in-memory Agent Server 不证明 licensed durable Runtime、进程重启 checkpoint
  恢复、HA、RTO/RPO 或 hosted deployment。
- hosted OIDC、DB membership authority、跨用户/跨租户/撤权、operator audit 未闭环。
- LangSmith/Langfuse 真实双端 correlation、出口脱敏、平台宕机降级未闭环。
- Notification Outbox、真实投递回执、reconciler、Library/Settings、feedback、
  retry/fork、性能/安全/DR/release attestation 未完成。

因此 M3 只证明 aggregate HITL 本地纵向切片与队列收敛已经可运行、可查询、可回归；
V2 整体仍不是 production ready。
